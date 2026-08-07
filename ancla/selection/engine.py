"""The core: choosing what to show from the profile for a specific job posting.

This is the piece that sets the product apart. It does not draft a CV: it
**selects** among facts the user has already verified, orders them by
relevance, and explains why each one was chosen.

Hard rules, inherited from the personal skill `/cv-adaptativo`:

1. Never propose an experience or skill that does not exist in the profile.
   If the posting asks for something the user does not have, it goes to
   `gaps`, not the CV.
2. Never rewrite the user's bullets: they are shown exactly as written.
3. Every choice carries a reason. Without a reason the user cannot judge the
   proposal, and judging it is exactly what we are asking them to do.

How those rules hold up here: the model only ever returns profile *ids* and
reasons, and this module discards any id that does not exist. Rule 2 comes
for free because `Proposal` stores references, not text — the engine never
actually touches a bullet. The one exception is "About me", where text is
genuinely composed, and there the gaps are only ever filled with names of
skills that already exist in the profile.

One model call per adaptation. Everything else is deterministic, and if the
model falls short it is topped up from the profile, never by inventing.
"""
from __future__ import annotations

import json
from typing import Any

from flask_babel import gettext as _

from ancla.ai.client import AIClient, AIError
from ancla.profile.model import (
    N_ABOUT_ME_GROUP,
    N_EXPERIENCES,
    N_SKILLS,
    Bilingual,
    Experience,
    Language,
    Profile,
    Proposal,
    SelectedAboutMe,
    SelectedExperience,
    Skill,
)
from ancla.selection.prompt import build_messages
from ancla.text import to_text, json_block, normalize

# Text the user sees when the model leaves something half-done. Stated
# plainly instead of glossed over: the proposal is there to be reviewed,
# not signed off on blindly.
MOTIVO_AUSENTE = "El modelo no explicó esta elección, revísala antes de usarla."
AVISO_SOBRE_MI_INCOMPLETO = (
    "Tu perfil no tiene suficientes skills para rellenar el «Sobre mí». Hacen "
    f"falta {N_ABOUT_ME_GROUP} por grupo. El texto se queda con sus huecos a la "
    "vista hasta que añadas más."
)


def adapt(
    perfil: Profile,
    vacante: str,
    idioma: Language,
    cliente: AIClient,
    n_experiencias: int = N_EXPERIENCES,
    n_skills: int = N_SKILLS,
) -> Proposal:
    """Adapts the profile to the job posting. A single model call.

    If the profile has fewer items than requested, returns whatever there
    is: filling the gap by inventing is exactly what this product does not do.

    Raises `ErrorIA` if the provider fails, and `ValueError` if the profile
    is empty or has no "About me" template.
    """
    if perfil.is_empty():
        raise ValueError(
            _("Tu perfil está vacío: añade experiencias y skills antes de adaptar el CV.")
        )
    if perfil.about_me is None:
        raise ValueError(
            _("Tu perfil no tiene plantilla de «Sobre mí»: créala antes de adaptar el CV.")
        )
    if not vacante.strip():
        raise ValueError(_("Pega el texto de la vacante antes de generar la propuesta."))

    sistema, usuario = build_messages(
        perfil, vacante, idioma, n_experiencias, n_skills
    )
    datos = _parse(cliente.complete(sistema, usuario))

    skills, motivo_skills = _choose_skills(datos, perfil, vacante, n_skills)
    return Proposal(
        language=idioma,
        about_me=_compose_about_me(datos, perfil, skills, idioma),
        skills=skills,
        experiences=_choose_experiences(datos, perfil, vacante, n_experiencias),
        skills_reason=motivo_skills,
        gaps=_filter_gaps(datos, perfil),
    )


# --------------------------------------------------------------------------
# Model response
# --------------------------------------------------------------------------


def _parse(respuesta: str) -> dict[str, Any]:
    """Pulls the JSON object out of the response, however it comes.

    Never retried: one adaptation is one call. If the response cannot be
    understood, the user hits generate again knowing what that costs.
    """
    bloque = json_block(respuesta or "")
    if bloque is None:
        raise AIError(
            _(
                "El modelo no ha devuelto una respuesta que se pueda interpretar. "
                "Vuelve a generar la propuesta."
            )
        )
    try:
        datos = json.loads(bloque)
    except json.JSONDecodeError as exc:
        raise AIError(
            _(
                "El modelo ha devuelto una respuesta mal formada. "
                "Vuelve a generar la propuesta."
            )
        ) from exc
    if not isinstance(datos, dict):
        raise AIError(
            _(
                "El modelo ha devuelto algo que no es una propuesta. "
                "Vuelve a generar la propuesta."
            )
        )
    return datos


def _as_list(valor: Any) -> list[Any]:
    return valor if isinstance(valor, list) else []


# --------------------------------------------------------------------------
# Selection: what the model chose, filtered against the profile
# --------------------------------------------------------------------------


def _choose_experiences(
    datos: dict[str, Any], perfil: Profile, vacante: str, cuantas: int
) -> list[SelectedExperience]:
    elegidas: list[SelectedExperience] = []
    vistas: set[str] = set()

    for elemento in _as_list(datos.get("experiencias")):
        if len(elegidas) >= cuantas:
            break
        id_exp, motivo = _id_and_reason(elemento)
        # This is where any invented experience dies: if it is not in the
        # profile, it never reaches the CV.
        if not id_exp or id_exp in vistas or perfil.experience(id_exp) is None:
            continue
        vistas.add(id_exp)
        elegidas.append(
            SelectedExperience(id=id_exp, reason=motivo or MOTIVO_AUSENTE)
        )

    for exp in _by_relevance(perfil.experiences, vacante):
        if len(elegidas) >= cuantas:
            break
        if exp.id in vistas:
            continue
        vistas.add(exp.id)
        elegidas.append(
            SelectedExperience(id=exp.id, reason=_filler_reason(exp, vacante))
        )
    return elegidas


def _choose_skills(
    datos: dict[str, Any], perfil: Profile, vacante: str, cuantas: int
) -> tuple[list[str], str]:
    elegidas: list[str] = []
    for elemento in _as_list(datos.get("skills")):
        if len(elegidas) >= cuantas:
            break
        id_skill, _ = _id_and_reason(elemento)
        if not id_skill or id_skill in elegidas or perfil.skill(id_skill) is None:
            continue
        elegidas.append(id_skill)

    motivo = to_text(datos.get("motivo_skills")) or MOTIVO_AUSENTE
    completadas = [
        skill.id
        for skill in _by_relevance(perfil.skills, vacante)
        if skill.id not in elegidas
    ][: max(0, cuantas - len(elegidas))]
    if completadas:
        motivo += (
            " El modelo devolvió menos skills de las que caben, así que el sistema ha"
            " completado la lista con las del perfil que más coinciden con la vacante;"
            " revisa las últimas."
        )
    elegidas.extend(completadas)
    return elegidas, motivo


def _id_and_reason(elemento: Any) -> tuple[str, str]:
    """Accepts both `"id"` and `{"id": ..., "motivo": ...}`."""
    if isinstance(elemento, str):
        return elemento.strip(), ""
    if isinstance(elemento, dict):
        return to_text(elemento.get("id")), to_text(elemento.get("motivo"))
    return "", ""


def _by_relevance(elementos: list[Any], vacante: str) -> list[Any]:
    """Deterministic ordering by keyword overlap with the job posting.

    Only used to top up whatever the model did not choose. Not meant to be
    clever: meant to be explainable and to not spend another call.
    """
    texto = normalize(vacante)
    ordenados = sorted(
        enumerate(elementos),
        key=lambda par: (-len(_matches(par[1], texto)), par[0]),
    )
    return [elemento for _, elemento in ordenados]


def _matches(
    elemento: Experience | Skill, vacante_normalizada: str
) -> list[str]:
    return [
        palabra
        for palabra in elemento.keywords
        if normalize(palabra) and normalize(palabra) in vacante_normalizada
    ]


def _filler_reason(elemento: Experience | Skill, vacante: str) -> str:
    coincidencias = _matches(elemento, normalize(vacante))
    if coincidencias:
        return (
            "Elegida por el sistema, no por el modelo: coincide con la vacante en "
            + ", ".join(coincidencias[:3])
            + "."
        )
    return (
        "Elegida por el sistema para completar la sección; no se le ha encontrado "
        "coincidencia clara con la vacante. Cámbiala si no encaja."
    )


# --------------------------------------------------------------------------
# About me: the only part where the system composes text
# --------------------------------------------------------------------------


def _compose_about_me(
    datos: dict[str, Any], perfil: Profile, skills: list[str], idioma: Language
) -> SelectedAboutMe:
    bruto = datos.get("sobre_mi")
    bruto = bruto if isinstance(bruto, dict) else {}

    # The model's two proposed groups are recorded first, and only then
    # topped up. The other way round, filling group A could take a skill
    # the model had specifically asked for in group B.
    reparto = _AboutMeAllocation(perfil, skills)
    propuestas_a = reparto.proposals(bruto.get("grupo_a"))
    propuestas_b = reparto.proposals(bruto.get("grupo_b"))
    grupo_a = _names(reparto.complete(propuestas_a), idioma)
    grupo_b = _names(reparto.complete(propuestas_b), idioma)

    motivo = to_text(bruto.get("motivo")) or MOTIVO_AUSENTE
    if len(grupo_a) == N_ABOUT_ME_GROUP and len(grupo_b) == N_ABOUT_ME_GROUP:
        texto = perfil.about_me.render(grupo_a, grupo_b, idioma)
    else:
        # Without enough skills there is nothing honest to put in the gaps,
        # so the template is left as-is and the reason says why.
        texto = perfil.about_me.template[idioma]
        motivo = f"{motivo} {AVISO_SOBRE_MI_INCOMPLETO}"
    return SelectedAboutMe(
        group_a=grupo_a, group_b=grupo_b, text=texto, reason=motivo
    )


class _AboutMeAllocation:
    """Splits skills between the two "About me" groups without repeating any.

    Carries state — which skills are already placed — and keeps it inside
    on purpose. It used to travel from parameter to parameter as a `set`:
    it worked, but it hid the fact that call order matters, which is
    exactly what someone reorders by accident six months from now.
    """

    def __init__(self, perfil: Profile, skills: list[str]) -> None:
        self._perfil = perfil
        self._usadas: set[str] = set()
        # Topping up draws first from the skills already shown on the CV:
        # "About me" has to stay consistent with the list underneath it.
        # After that, from the rest of the profile.
        seleccionadas = [perfil.skill(id_skill) for id_skill in skills]
        self._reserva = [s for s in seleccionadas if s is not None] + perfil.skills

    def proposals(self, valores: Any) -> list[Skill]:
        """The skills the model proposed that genuinely exist in the profile.

        Whatever does not resolve against a real skill is dropped: rule 1
        applied to the one section where the system composes text.
        """
        return self._take([], (to_text(valor) for valor in _as_list(valores)))

    def complete(self, elegidas: list[Skill]) -> list[Skill]:
        """Tops up the group from the reserve, without mutating the list it receives."""
        return self._take(elegidas, (skill.id for skill in self._reserva))

    def _take(self, elegidas: list[Skill], candidatos) -> list[Skill]:
        grupo = list(elegidas)
        for candidato in candidatos:
            if len(grupo) >= N_ABOUT_ME_GROUP:
                break
            skill = _skill_by_name(candidato, self._perfil)
            if skill is None or skill.id in self._usadas:
                continue
            self._usadas.add(skill.id)
            grupo.append(skill)
        return grupo


def _names(skills: list[Skill], idioma: Language) -> list[str]:
    """The name in the CV's language, not whatever the model wrote.

    If it asks for "Machine learning" for a Spanish CV and the profile's
    skill is called "Aprendizaje automático", the profile's version wins.
    """
    return [skill.name[idioma] for skill in skills]


def _skill_by_name(valor: str, perfil: Profile) -> Skill | None:
    """Looks up a skill by id, or by its name in either language."""
    if not valor:
        return None
    por_id = perfil.skill(valor)
    if por_id is not None:
        return por_id
    buscado = normalize(valor)
    return next(
        (
            skill
            for skill in perfil.skills
            if buscado
            in (normalize(skill.name["es"]), normalize(skill.name["en"]))
        ),
        None,
    )


# --------------------------------------------------------------------------
# Gaps: what the posting asks for that the profile does not have
# --------------------------------------------------------------------------


def _filter_gaps(datos: dict[str, Any], perfil: Profile) -> list[str]:
    """Cleans up the gap list and drops anything the profile actually has.

    A gap that turns out to be something the user has is just noise: it
    makes them doubt a proposal that was actually correct.
    """
    huecos: list[str] = []
    vistos: set[str] = set()
    for valor in _as_list(datos.get("huecos")):
        hueco = to_text(valor)
        clave = normalize(hueco)
        if not clave or clave in vistos or _gap_covered(hueco, perfil):
            continue
        vistos.add(clave)
        huecos.append(hueco)
    return huecos


def _gap_covered(hueco: str, perfil: Profile) -> bool:
    """True if the reported gap is already covered by something in the
    profile — technical skills, personal skills, or languages — even if
    worded differently.

    The model never sees `personal_skills` or `languages` (they are not
    sent to it: that is what guarantees they can never sneak into "About
    me" nor the technical skills), so it will almost always report them as
    a gap. This filter is the only thing that can prevent that, and that is
    why it is looser than `_skill_por_nombre` (which requires an exact
    match and is used to *identify* a skill when building "About me"): a
    gap is worded as prose — "advanced level of English" — almost never as
    a skill's exact name, so requiring an exact match here would let almost
    every false positive through.
    """
    clave = normalize(hueco)
    if not clave:
        return False
    candidatos = (*perfil.skills, *perfil.personal_skills, *perfil.languages)
    return any(_name_or_keyword_in(clave, item.name, item.keywords) for item in candidatos)


def _name_or_keyword_in(clave: str, nombre: Bilingual[str], keywords: list[str]) -> bool:
    nombres = (normalize(nombre["es"]), normalize(nombre["en"]))
    if any(n and (n in clave or clave in n) for n in nombres):
        return True
    return any(kw.strip() and normalize(kw) in clave for kw in keywords)
