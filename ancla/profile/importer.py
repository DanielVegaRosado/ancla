"""Analyses a CV's text and proposes candidates for the profile's four
sections: experience, technical skills, personal skills, and languages.

Different from `migrador.py`: that one converts a rigid, purpose-built
format (`TITULO_ES:`, `BULLETS_ES:`...) with regular expressions, no AI,
because there is no ambiguity to resolve. An arbitrary CV is free-form prose
— everyone writes it differently — so here a model needs to understand the
text, not a regex.

The text it analyses always comes from `extraccion.py` (deterministic) or
from what the user pasted by hand: never from the model itself "reading" a
PDF, which could mistranscribe a word without anyone noticing.

**Nothing is saved here.** This module only proposes `Experience`/`Skill`/
`SpokenLanguage` objects with a provisional id; the web layer saves them —
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

**Translates when a language is missing** (product decision, 2026-07-22): if
the CV is only in Spanish, the model also proposes the English version, and
vice versa. This is the one deliberate exception to "never rewrite the
user" — there is nothing written yet to rewrite here, and the user reviews
the translation before anything is saved. **Pending for v1.1:** higher
quality translation backed by dictionaries (Oxford/Cambridge) instead of
leaving it entirely to the model's judgment.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from ancla.ai.client import AIClient
from ancla.profile.model import Bilingual, Experience, Profile, Skill, SpokenLanguage
from ancla.text import to_text, to_texts, json_block, normalize, slugify

# Groq's free tier is limited to 8000 tokens per minute (checked against the
# real API). That budget has to cover the system prompt (~450 tokens), this
# text, and the model's response all at once — an overly long CV can leave
# so little room for the response that Groq truncates or rejects it
# outright. 10,000 characters is plenty for any real CV (1-2 pages) and
# leaves room for all three.
MAX_CARACTERES_CV = 10000

SISTEMA = """\
Analizas el texto de un CV para ayudar a una persona a construir su base de datos \
profesional. No escribes su CV: identificas qué hay en el texto y lo estructuras en \
CUATRO categorías: experiencias, skills técnicas, skills personales e idiomas.

Reglas:
1. Extrae SOLO lo que está literalmente en el texto. No añadas responsabilidades, \
logros, cifras o fechas que no aparezcan.
2. Si un dato no está en el texto, deja ese campo vacío. No lo completes con un \
supuesto razonable, por plausible que parezca.
3. El texto puede estar en un solo idioma. Si falta la versión en el otro, TRADUCE \
de forma literal y fiel — no reformules ni mejores el estilo, traduce el contenido \
tal cual está.
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
como aparezca (p. ej. "C1 Avanzado", "Nativo", "B2") y tradúcelo igual que el resto — no \
inventes un nivel que no esté escrito. Un idioma hablado no es una skill técnica.
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

Responde ÚNICAMENTE con este JSON, sin texto alrededor ni bloques de código:
{
  "experiencias": [
    {"titulo": {"es": "", "en": ""}, "periodo": {"es": "", "en": ""},
     "bullets": {"es": [], "en": []}, "stack": {"es": "", "en": ""},
     "keywords": []}
  ],
  "skills": [
    {"nombre": {"es": "", "en": ""}, "categoria": "", "keywords": []}
  ],
  "skills_personales": [
    {"nombre": {"es": "", "en": ""}, "keywords": []}
  ],
  "idiomas": [
    {"nombre": {"es": "", "en": ""}, "nivel": {"es": "", "en": ""}, "keywords": []}
  ]
}"""


@dataclass(frozen=True)
class ImportResult:
    experiencias: list[Experience] = field(default_factory=list)
    skills: list[Skill] = field(default_factory=list)
    skills_personales: list[Skill] = field(default_factory=list)
    idiomas: list[SpokenLanguage] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


def analyze_cv(cliente: AIClient, texto_cv: str, perfil: Profile) -> ImportResult:
    """A single call to the model. `perfil` is used only so the candidates'
    provisional ids do not collide with ones that already exist."""
    texto = texto_cv.strip()
    if not texto:
        return ImportResult(avisos=["No hay texto que analizar."])
    if not cliente.available():
        return ImportResult(
            avisos=["No hay ninguna clave de API configurada. Ve a Ajustes."]
        )

    if len(texto) > MAX_CARACTERES_CV:
        texto = texto[:MAX_CARACTERES_CV] + "\n[...texto recortado...]"

    try:
        bruto = cliente.complete(SISTEMA, texto)
    except Exception as exc:
        return ImportResult(avisos=[f"No se ha podido analizar el CV: {exc}"])

    datos = _extract_json(bruto)
    if datos is None:
        return ImportResult(
            avisos=["El modelo no ha devuelto una respuesta interpretable. Vuelve a intentarlo."]
        )

    ids_usados: set[str] = (
        {e.id for e in perfil.experiences}
        | {s.id for s in perfil.skills}
        | {s.id for s in perfil.personal_skills}
        | {i.id for i in perfil.languages}
    )

    experiencias, duplicadas_exp = _candidates(
        datos.get("experiencias"), _to_experience, ids_usados,
        "title", _bilingual_names(perfil.experiences, "title"),
    )
    skills, duplicadas_skills = _candidates(
        datos.get("skills"), _to_skill, ids_usados,
        "name", _bilingual_names(perfil.skills, "name"),
    )
    skills_personales, duplicadas_sp = _candidates(
        datos.get("skills_personales"), _to_skill, ids_usados,
        "name", _bilingual_names(perfil.personal_skills, "name"),
    )
    idiomas, duplicadas_idiomas = _candidates(
        datos.get("idiomas"), _to_language, ids_usados,
        "name", _bilingual_names(perfil.languages, "name"),
    )
    duplicadas = duplicadas_exp + duplicadas_skills + duplicadas_sp + duplicadas_idiomas

    avisos = []
    if not any((experiencias, skills, skills_personales, idiomas)):
        if duplicadas:
            avisos.append(
                "No hay nada nuevo que añadir: todo lo que se ha reconocido en este "
                "CV ya está en tu perfil."
            )
        else:
            avisos.append(
                "No se ha encontrado ninguna experiencia ni skill reconocible en el texto."
            )
    elif duplicadas:
        avisos.append(
            f"Se ha omitido {duplicadas} elemento(s) que ya estaban en tu perfil "
            "(mismo nombre en español o en inglés) para no duplicarlos."
        )
    return ImportResult(
        experiencias=experiencias,
        skills=skills,
        skills_personales=skills_personales,
        idiomas=idiomas,
        avisos=avisos,
    )


# --------------------------------------------------------------------------
# Model response -> candidates
# --------------------------------------------------------------------------


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


def _candidates(bruto_lista: object, parser, ids_usados: set[str], atributo: str, existentes: set[str]):
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
        candidata = parser(_as_dict(bruto), ids_usados)
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


def _to_experience(datos: dict, ids_usados: set[str]) -> Experience | None:
    titulo = _bilingual(datos.get("titulo"))
    # No title means nothing to show on the review screen: it is dropped,
    # not proposed as an empty candidate.
    if not titulo["es"].strip() and not titulo["en"].strip():
        return None
    id_ = _free_id(titulo["es"] or titulo["en"], ids_usados)
    return Experience(
        id=id_,
        title=titulo,
        period=_bilingual(datos.get("periodo")),
        bullets=_bilingual_list(datos.get("bullets")),
        stack=_bilingual(datos.get("stack")),
        keywords=to_texts(datos.get("keywords")),
    )


def _to_skill(datos: dict, ids_usados: set[str]) -> Skill | None:
    nombre = _bilingual(datos.get("nombre"))
    if not nombre["es"].strip() and not nombre["en"].strip():
        return None
    id_ = _free_id(nombre["es"] or nombre["en"], ids_usados)
    return Skill(
        id=id_,
        name=nombre,
        category=to_text(datos.get("categoria")),
        keywords=to_texts(datos.get("keywords")),
    )


def _to_language(datos: dict, ids_usados: set[str]) -> SpokenLanguage | None:
    nombre = _bilingual(datos.get("nombre"))
    if not nombre["es"].strip() and not nombre["en"].strip():
        return None
    id_ = _free_id(nombre["es"] or nombre["en"], ids_usados)
    return SpokenLanguage(
        id=id_,
        name=nombre,
        level=_bilingual(datos.get("nivel")),
        keywords=to_texts(datos.get("keywords")),
    )


def _bilingual(datos: object) -> Bilingual[str]:
    datos = datos if isinstance(datos, dict) else {}
    return Bilingual(es=to_text(datos.get("es")), en=to_text(datos.get("en")))


def _bilingual_list(datos: object) -> Bilingual[list[str]]:
    datos = datos if isinstance(datos, dict) else {}
    return Bilingual(es=to_texts(datos.get("es")), en=to_texts(datos.get("en")))


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
