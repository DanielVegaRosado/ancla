"""Analyses a CV's text and proposes candidates for the profile's five
sections: experience, technical skills, personal skills, languages, and
education.

Different from `migrador.py`: that one converts a rigid, purpose-built
format (`TITULO_ES:`, `BULLETS_ES:`...) with regular expressions, no AI,
because there is no ambiguity to resolve. An arbitrary CV is free-form prose
— everyone writes it differently — so here a model needs to understand the
text, not a regex.

The text it analyses always comes from `extraccion.py` (deterministic) or
from what the user pasted by hand: never from the model itself "reading" a
PDF, which could mistranscribe a word without anyone noticing.

**Nothing is saved here.** This module only proposes `Experience`/`Skill`/
`SpokenLanguage`/`Education` objects with a provisional id; the web layer saves them —
or not — after the user reviews and confirms them one by one, the same as
with the suggested keywords in `keywords.py`. It never raises a network or
format exception: a failure here turns into an empty candidate list and a
warning, so it never breaks the upload screen.

**Personal skills and languages use a separate catalog from technical
skills** (same as in `Profile`, see `modelo.py`): the model is told them
apart in the prompt itself (rules 7 and 8), not by a filter applied
afterwards — that way "Teamwork" can never sneak in among the technical
skills through a classification mistake.

**Does not repeat what is already in the profile** (product decision,
2026-07-23): importing a second CV — e.g. the English version of one
already imported in Spanish — must not duplicate every experience and skill
already saved the first time, only what is new. This is NOT asked of the
model through the prompt: each candidate is compared against `perfil` after
the response comes back (`normalizar()`, case- and accent-insensitive, same
as the rest of the project compares names), and whichever already exists
under that name in Spanish or English is discarded. Same philosophy as the
selection engine's ids — a guarantee enforced by code, not by instructing
the model, because a prompt can be ignored and a filter applied afterwards
cannot.

**Analyses in one language only.** The model used to be asked for every
field in Spanish *and* English at once, and that response is what filled the
per-minute quota: output runs at roughly one token per character of CV, so
asking for both languages halved how much of a CV fitted in a single call
and the rest was cut off with nothing on screen to say so. The CV's own
language is detected here and can be corrected by the user before the call
— a wrong guess that cannot be fixed is worse than asking. Translating into
the other language is a separate, optional call (`translation.py`), which
lands in a different minute on its own because reviewing takes one.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from flask_babel import gettext as _

from ancla.ai.client import AIClient, AIError
from ancla.profile.serialization import split_period
from ancla.profile.model import (
    Bilingual,
    Education,
    Experience,
    Language,
    Profile,
    Skill,
    SpokenLanguage,
)
from ancla.text import to_text, to_texts, json_block, normalize, slugify

# Groq's free tier is limited to 8000 tokens per minute (checked against the
# real API). That budget has to cover the system prompt (~1070 tokens), this
# text (~1 token per 3.9 characters), and the model's response all at once.
# Measured against real CVs, the response runs at ~1.0 token per character
# when both languages are asked for, so a single language costs ~0.5:
#   1070 + c/3.9 + 0.5c <= 8000  ->  c <= ~9100
# 8000 leaves margin for the wide variance seen between identical runs. Past
# that the text is cut, and the cut is reported rather than silent: a CV
# analysed only up to the middle used to look like a model that had missed
# half a career.
MAX_CARACTERES_CV = 8000

PLANTILLA_SISTEMA = """\
Analizas el texto de un CV para ayudar a una persona a construir su base de datos \
profesional. No escribes su CV: identificas qué hay en el texto y lo estructuras en \
CINCO categorías: experiencias, skills técnicas, skills personales, idiomas y educación.

Reglas:
1. Extrae SOLO lo que está literalmente en el texto. No añadas responsabilidades, \
logros, cifras o fechas que no aparezcan.
2. Si un dato no está en el texto, deja ese campo vacío. No lo completes con un \
supuesto razonable, por plausible que parezca.
3. Responde en {idioma}, y SOLO en {idioma}. No traduzcas nada a ningún otro idioma ni \
devuelvas ninguna versión alternativa de ningún campo.
4. Ante la duda entre si algo es una experiencia (un puesto o proyecto con contexto \
propio) o solo una skill suelta mencionada de pasada, propón skill. Inventar una \
experiencia alrededor de una mención suelta es peor error que perder una experiencia.
5. Cada puesto o proyecto distinto es una experiencia separada. Nunca fusiones ni \
resumas varias experiencias en una.
6. Para cada skill TÉCNICA, propón una categoría breve (lenguaje, cloud, dato, \
framework...) y unas pocas keywords de cómo se nombra en ofertas de empleo. No añadas \
tecnologías relacionadas que no aparezcan en el texto — de una mención a "Docker" no \
propongas "Kubernetes" como skill aparte.
7. Distingue skill TÉCNICA de skill PERSONAL: una tecnología, lenguaje o herramienta \
concreta (Python, SQL, Docker...) es técnica; una cualidad o forma de trabajar \
(trabajo en equipo, resolución de problemas, atención al detalle, autonomía...) es \
personal, aunque el CV las liste juntas o bajo el mismo apartado. Nunca mezcles las dos.
8. Para cada idioma HABLADO (español, inglés, alemán...) extrae también su nivel tal \
como aparezca (p. ej. "C1 Avanzado", "Nativo", "B2") — no inventes un nivel que no esté \
escrito. Un idioma hablado no es una skill técnica.
9. Antes de dar la lista de skills técnicas por definitiva, revísala tú mismo: si dos \
entradas nombran la misma tecnología o competencia con distinta redacción (p. ej. \
"Machine Learning" y "Machine Learning Development", o "Data Analysis" y "Data \
Analytics"), dejas solo una — la forma más corta y reconocible. Tampoco conviertas el \
título o el campo de una experiencia en una skill aparte (de un puesto "Data Engineer" \
no propongas la skill "Data Engineering"; de un proyecto de "Quantum Computing" no \
propongas esa etiqueta como skill): ese campo ya queda representado por la propia \
experiencia. Esto NO afecta a las tecnologías concretas que se mencionen dentro de una \
experiencia (lenguajes, librerías, herramientas del stack) — esas sí son skills \
aparte aunque no estén en una lista de skills separada, y ante la duda de si una \
tecnología concreta cuenta o no, inclúyela: es preferible algo de redundancia a que \
falte una tecnología real que sí se menciona.
10. "periodo", "stack" y "centro" se copian tal como aparecen: fechas, nombres de \
tecnología y nombres propios de centros de estudios se leen igual en cualquier idioma.
11. Extrae también la EDUCACIÓN: cada titulación, grado, máster, certificación o curso, \
con su título, el centro donde se cursó y el periodo tal como aparezcan. Una educación \
no es una experiencia ni una skill, aunque el CV la liste en el mismo apartado: el \
título de una titulación ("Grado en Ingeniería Informática") nunca se propone además \
como experiencia ni como skill aparte. Si el texto no dice el centro o el periodo, deja \
ese campo vacío.

Responde ÚNICAMENTE con este JSON, sin texto alrededor ni bloques de código:
{{
  "experiencias": [
    {{"titulo": "", "periodo": "", "bullets": [], "stack": "", "keywords": []}}
  ],
  "skills": [
    {{"nombre": "", "categoria": "", "keywords": []}}
  ],
  "skills_personales": [
    {{"nombre": "", "keywords": []}}
  ],
  "idiomas": [
    {{"nombre": "", "nivel": "", "keywords": []}}
  ],
  "educacion": [
    {{"titulo": "", "centro": "", "periodo": ""}}
  ]
}}"""

# Function words frequent enough that a handful of lines already separates
# the two languages, and rare enough in the other that a CV full of English
# technology names does not tip a Spanish CV over. Written without accents
# because the text is compared through `normalize`.
_PISTAS_IDIOMA: dict[Language, frozenset[str]] = {
    "es": frozenset(
        "de la el los las del que para con una por su y en como mas donde "
        "experiencia formacion idiomas anos actualidad".split()
    ),
    "en": frozenset(
        "the of and to for with in on at from as experience skills education "
        "languages years present".split()
    ),
}


def detect_language(texto: str) -> Language:
    """The language a CV is written in, guessed from its function words.

    Deliberately a guess and not a decision: the user is shown it and can
    change it before the call. Getting it wrong only means the entries come
    out under the wrong label, which is why correcting it has to be
    possible; refusing to guess at all would put the choice in front of
    everyone, including the majority for whom it is obvious.

    Ties go to Spanish, the language the app is written in. A CV of nothing
    but technology names has no function words to count either way.
    """
    palabras = re.findall(r"[a-z]+", normalize(texto))
    conteo = {
        idioma: sum(1 for palabra in palabras if palabra in pistas)
        for idioma, pistas in _PISTAS_IDIOMA.items()
    }
    return "en" if conteo["en"] > conteo["es"] else "es"


@dataclass(frozen=True)
class ImportResult:
    experiencias: list[Experience] = field(default_factory=list)
    skills: list[Skill] = field(default_factory=list)
    skills_personales: list[Skill] = field(default_factory=list)
    idiomas: list[SpokenLanguage] = field(default_factory=list)
    educacion: list[Education] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


def analyze_cv(
    cliente: AIClient, texto_cv: str, perfil: Profile, idioma: Language = "es"
) -> ImportResult:
    """A single call to the model, in one language.

    `idioma` is the language the CV is written in — everything comes back in
    it and the other side of each field is left empty for `translation.py`
    to fill in later, or never. `perfil` is used only so the candidates'
    provisional ids do not collide with ones that already exist.
    """
    texto = texto_cv.strip()
    avisos: list[str] = []
    if not texto:
        return ImportResult(avisos=[_("No hay texto que analizar.")])
    if not cliente.available():
        return ImportResult(
            avisos=[_("No hay ninguna clave de API configurada. Ve a Ajustes.")]
        )

    if len(texto) > MAX_CARACTERES_CV:
        avisos.append(
            _(
                "Tu CV son %(total)s caracteres y solo se han analizado los "
                "%(analizados)s primeros: no cabe más en una sola petición. Revisa "
                "lo que falte e impórtalo aparte pegando el texto restante.",
                total=len(texto), analizados=MAX_CARACTERES_CV,
            )
        )
        texto = texto[:MAX_CARACTERES_CV] + "\n[...texto recortado...]"

    try:
        bruto = cliente.complete(_system_prompt(idioma), texto)
    except AIError as error:
        # The provider clients already phrase their failures as what to do
        # next; prefixing them with a cause would bury that advice.
        return ImportResult(avisos=[*avisos, str(error)])
    except Exception as exc:
        return ImportResult(avisos=[*avisos, _("No se ha podido analizar el CV: %(error)s", error=exc)])

    datos = _extract_json(bruto)
    if datos is None:
        return ImportResult(
            avisos=[
                *avisos,
                _("El modelo no ha devuelto una respuesta interpretable. Vuelve a intentarlo."),
            ]
        )

    ids_usados: set[str] = (
        {e.id for e in perfil.experiences}
        | {s.id for s in perfil.skills}
        | {s.id for s in perfil.personal_skills}
        | {i.id for i in perfil.languages}
        | {e.id for e in perfil.education}
    )

    experiencias, duplicadas_exp = _candidates(
        datos.get("experiencias"), _to_experience, ids_usados, idioma,
        "title", _bilingual_names(perfil.experiences, "title"),
    )
    skills, duplicadas_skills = _candidates(
        datos.get("skills"), _to_skill, ids_usados, idioma,
        "name", _bilingual_names(perfil.skills, "name"),
    )
    skills_personales, duplicadas_sp = _candidates(
        datos.get("skills_personales"), _to_skill, ids_usados, idioma,
        "name", _bilingual_names(perfil.personal_skills, "name"),
    )
    idiomas, duplicadas_idiomas = _candidates(
        datos.get("idiomas"), _to_language, ids_usados, idioma,
        "name", _bilingual_names(perfil.languages, "name"),
    )
    educacion, duplicadas_educacion = _candidates(
        datos.get("educacion"), _to_education, ids_usados, idioma,
        "title", _bilingual_names(perfil.education, "title"),
    )
    duplicadas = (
        duplicadas_exp + duplicadas_skills + duplicadas_sp
        + duplicadas_idiomas + duplicadas_educacion
    )

    if not any((experiencias, skills, skills_personales, idiomas, educacion)):
        if duplicadas:
            avisos.append(
                _(
                    "No hay nada nuevo que añadir: todo lo que se ha reconocido en este "
                    "CV ya está en tu perfil."
                )
            )
        else:
            avisos.append(
                _("No se ha encontrado ninguna experiencia ni skill reconocible en el texto.")
            )
    elif duplicadas:
        avisos.append(
            _(
                "Se ha omitido %(cantidad)s elemento(s) que ya estaban en tu perfil "
                "(mismo nombre en español o en inglés) para no duplicarlos.",
                cantidad=duplicadas,
            )
        )
    return ImportResult(
        experiencias=experiencias,
        skills=skills,
        skills_personales=skills_personales,
        idiomas=idiomas,
        educacion=educacion,
        avisos=avisos,
    )


# --------------------------------------------------------------------------
# Model response -> candidates
# --------------------------------------------------------------------------


def _system_prompt(idioma: Language) -> str:
    """The prompt naming the language the answer must come back in.

    Built per call rather than kept as one constant per language: the only
    thing that changes is the name, and two near-identical copies of a
    150-line prompt drift apart the first time a rule is edited.
    """
    return PLANTILLA_SISTEMA.format(idioma={"es": "español", "en": "inglés"}[idioma])


def _extract_json(bruto: str) -> dict | None:
    bloque = json_block(bruto)
    if bloque is None:
        return None
    try:
        datos = json.loads(bloque)
    except json.JSONDecodeError:
        return None
    return datos if isinstance(datos, dict) else None


def _bilingual_names(items: list, atributo: str) -> set[str]:
    """The ES/EN names already present in the profile for this category,
    normalised to compare regardless of case, accents, or which language
    matches. `atributo` is "title" for experiences, "name" for skills and
    languages — the rest of the model shares that shape."""
    normalizados: set[str] = set()
    for item in items:
        bilingue = getattr(item, atributo)
        for valor in (bilingue["es"], bilingue["en"]):
            if valor:
                normalizados.add(normalize(valor))
    return normalizados


def _candidates(
    bruto_lista: object, parser, ids_usados: set[str], idioma: Language,
    atributo: str, existentes: set[str],
):
    """Parses a list from the model's response and drops whatever is
    already in the profile (by name, not id — the model does not know the
    profile's ids). Also drops duplicates within the batch itself: if the
    model repeats the same name twice in one response, rule 9 of the prompt
    asks it not to, but this guarantees it regardless. Returns
    `(candidates, number_of_duplicates)`."""
    existentes = set(existentes)  # copy: never mutate the caller's profile set
    candidatas = []
    duplicadas = 0
    for bruto in _as_list(bruto_lista):
        candidata = parser(_as_dict(bruto), ids_usados, idioma)
        if candidata is None:
            continue
        bilingue = getattr(candidata, atributo)
        es, en = normalize(bilingue["es"]), normalize(bilingue["en"])
        if (es and es in existentes) or (en and en in existentes):
            duplicadas += 1
            continue
        candidatas.append(candidata)
        existentes.update(nombre for nombre in (es, en) if nombre)
    return candidatas, duplicadas


def _to_experience(datos: dict, ids_usados: set[str], idioma: Language) -> Experience | None:
    titulo = _bilingual(datos.get("titulo"), idioma)
    # No title means nothing to show on the review screen: it is dropped,
    # not proposed as an empty candidate.
    if not titulo["es"].strip() and not titulo["en"].strip():
        return None
    id_ = _free_id(titulo["es"] or titulo["en"], ids_usados)
    return Experience(
        id=id_,
        title=titulo,
        **dict(zip(("period_start", "period_end"), split_period(_single_text(datos.get("periodo"))))),
        bullets=_bilingual_list(datos.get("bullets"), idioma),
        stack=_single_text(datos.get("stack")),
        keywords=to_texts(datos.get("keywords")),
    )


def _to_skill(datos: dict, ids_usados: set[str], idioma: Language) -> Skill | None:
    nombre = _bilingual(datos.get("nombre"), idioma)
    if not nombre["es"].strip() and not nombre["en"].strip():
        return None
    id_ = _free_id(nombre["es"] or nombre["en"], ids_usados)
    return Skill(
        id=id_,
        name=nombre,
        category=to_text(datos.get("categoria")),
        keywords=to_texts(datos.get("keywords")),
    )


def _to_language(datos: dict, ids_usados: set[str], idioma: Language) -> SpokenLanguage | None:
    nombre = _bilingual(datos.get("nombre"), idioma)
    if not nombre["es"].strip() and not nombre["en"].strip():
        return None
    id_ = _free_id(nombre["es"] or nombre["en"], ids_usados)
    return SpokenLanguage(
        id=id_,
        name=nombre,
        level=_bilingual(datos.get("nivel"), idioma),
        keywords=to_texts(datos.get("keywords")),
    )


def _to_education(datos: dict, ids_usados: set[str], idioma: Language) -> Education | None:
    titulo = _bilingual(datos.get("titulo"), idioma)
    if not titulo["es"].strip() and not titulo["en"].strip():
        return None
    id_ = _free_id(titulo["es"] or titulo["en"], ids_usados)
    return Education(
        id=id_,
        title=titulo,
        institution=_single_text(datos.get("centro")),
        **dict(zip(("period_start", "period_end"), split_period(_single_text(datos.get("periodo"))))),
    )


def _bilingual(datos: object, idioma: Language) -> Bilingual[str]:
    """The value under `idioma`, with the other language left empty.

    A model that answers with an `{es, en}` pair anyway is taken at its
    word: the pair costs nothing extra now that it has already been paid
    for, and dropping half of a reply that is right is worse than a prompt
    slip.
    """
    if isinstance(datos, dict) and ("es" in datos or "en" in datos):
        return Bilingual(es=to_text(datos.get("es")), en=to_text(datos.get("en")))
    return _only(to_text(datos), idioma)


def _single_text(datos: object) -> str:
    """Like `_bilingual`, but for a field asked as one value ("periodo",
    "stack"). Still tolerates the model returning an `{es, en}` pair despite
    rule 10 of the prompt — takes `es`, falling back to `en`, rather than
    losing the whole field over a prompt slip."""
    if isinstance(datos, dict):
        return to_text(datos.get("es")) or to_text(datos.get("en"))
    return to_text(datos)


def _bilingual_list(datos: object, idioma: Language) -> Bilingual[list[str]]:
    """`_bilingual` for a list of bullets."""
    if isinstance(datos, dict) and ("es" in datos or "en" in datos):
        return Bilingual(es=to_texts(datos.get("es")), en=to_texts(datos.get("en")))
    return _only(to_texts(datos), idioma)


def _only(valor, idioma: Language):
    """The value under `idioma`, empty under the other one. `valor` decides
    what "empty" is, so a text pairs with `""` and a list with `[]`."""
    vacio = [] if isinstance(valor, list) else ""
    return Bilingual(es=valor, en=vacio) if idioma == "es" else Bilingual(es=vacio, en=valor)


def _free_id(nombre: str, ids_usados: set[str]) -> str:
    """Provisional id derived from the name; the user reviews it the same
    way as in the manual forms. Gets a suffix if it is already used within
    this batch or in the profile, so two candidates can never collide."""
    base = slugify(nombre)
    candidato, n = base, 2
    while candidato in ids_usados:
        candidato = f"{base}-{n}"
        n += 1
    ids_usados.add(candidato)
    return candidato


def _as_list(valor: object) -> list:
    return valor if isinstance(valor, list) else []


def _as_dict(valor: object) -> dict:
    return valor if isinstance(valor, dict) else {}
