"""Deterministic checks on a proposal. Zero tokens.

Anything a machine can verify on its own is never asked of an AI judge: it
is cheaper, it never fails by chance, and its verdict is not up for debate.
The judge is reserved for what genuinely needs judgment (was this the best
possible choice? does this reason actually say something?).

If any of these fail, it is a bug in the engine, not an opinion.
"""
from __future__ import annotations

from dataclasses import dataclass

from ancla.profile.model import Profile, Proposal
from ancla.text import normalize


@dataclass(frozen=True)
class Check:
    nombre: str
    correcta: bool
    detalle: str = ""


def check(propuesta: Proposal, perfil: Profile, n_exp: int, n_skills: int) -> list[Check]:
    return [
        _everything_from_catalog(propuesta, perfil),
        _no_duplicates(propuesta),
        _counts(propuesta, perfil, n_exp, n_skills),
        _everything_has_a_reason(propuesta),
        _about_me_has_no_gaps(propuesta),
        _groups_dont_overlap(propuesta),
        _gaps_not_in_profile(propuesta, perfil),
    ]


def _everything_from_catalog(propuesta: Proposal, perfil: Profile) -> Check:
    """Product rule number one. The engine already filters, but this checks
    it end-to-end with real data, which is a different thing."""
    inventados = [
        exp.id for exp in propuesta.experiences if perfil.experience(exp.id) is None
    ] + [id_ for id_ in propuesta.skills if perfil.skill(id_) is None]
    return Check(
        "todo_del_catalogo",
        not inventados,
        "" if not inventados else f"fuera del perfil: {', '.join(inventados)}",
    )


def _no_duplicates(propuesta: Proposal) -> Check:
    ids = [exp.id for exp in propuesta.experiences] + propuesta.skills
    repetidos = {id_ for id_ in ids if ids.count(id_) > 1}
    return Check(
        "sin_repetidos", not repetidos, ", ".join(sorted(repetidos))
    )


def _counts(
    propuesta: Proposal, perfil: Profile, n_exp: int, n_skills: int
) -> Check:
    """As many as requested are expected, or all there are if there are fewer."""
    esperadas = min(n_exp, len(perfil.experiences))
    esperadas_skills = min(n_skills, len(perfil.skills))
    fallos = []
    if len(propuesta.experiences) != esperadas:
        fallos.append(f"{len(propuesta.experiences)} experiencias (esperadas {esperadas})")
    if len(propuesta.skills) != esperadas_skills:
        fallos.append(f"{len(propuesta.skills)} skills (esperadas {esperadas_skills})")
    return Check("cantidades", not fallos, "; ".join(fallos))


def _everything_has_a_reason(propuesta: Proposal) -> Check:
    """Rule 3: without a reason, the user cannot judge the proposal."""
    sin_motivo = [exp.id for exp in propuesta.experiences if not exp.reason.strip()]
    if not propuesta.skills_reason.strip():
        sin_motivo.append("(conjunto de skills)")
    if not propuesta.about_me.reason.strip():
        sin_motivo.append("(sobre mí)")
    return Check("todo_lleva_motivo", not sin_motivo, ", ".join(sin_motivo))


def _about_me_has_no_gaps(propuesta: Proposal) -> Check:
    """An unfilled `{GROUP_A_1}` would be copied into the CV as-is."""
    hay_hueco = "{GROUP_" in propuesta.about_me.text
    return Check(
        "sobre_mi_sin_huecos",
        not hay_hueco,
        "quedan huecos sin rellenar en el texto" if hay_hueco else "",
    )


def _groups_dont_overlap(propuesta: Proposal) -> Check:
    a = {normalize(x) for x in propuesta.about_me.group_a}
    b = {normalize(x) for x in propuesta.about_me.group_b}
    comunes = a & b
    return Check("grupos_sin_solaparse", not comunes, ", ".join(sorted(comunes)))


def _gaps_not_in_profile(propuesta: Proposal, perfil: Profile) -> Check:
    """A gap that is actually in the profile is a false positive: it would
    tell the user they are missing something they already have documented."""
    nombres = {
        normalize(skill.name[propuesta.language]) for skill in perfil.skills
    } | {normalize(palabra) for skill in perfil.skills for palabra in skill.keywords}
    falsos = [hueco for hueco in propuesta.gaps if normalize(hueco) in nombres]
    return Check(
        "huecos_no_estan_en_el_perfil", not falsos, ", ".join(falsos)
    )
