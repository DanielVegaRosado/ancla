"""Analyses a CV's text and proposes candidates for the profile's seven
sections: experience, technical skills, personal skills, languages,
education, contact details, and the "About me" paragraph.

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

**A CV too long for one call keeps the part `_recortar` had to leave out**
(`ImportResult.restante`), instead of discarding it: the web layer stores it
next to the batch under review and can send it through `analyze_cv` again as
a second, independent call, the same one-more-minute pattern as the
translation above. If that second call is itself too long, `restante` comes
back non-empty again — the same mechanism repeats rather than needing to
special-case a third part.

**Contact and "About me" follow the same semantic criterion as the other
five categories: nothing here depends on a literal header appearing in the
text.** A CV with no heading at all before its opening paragraph, or one
that calls it "Perfil profesional" or "Summary" instead of "Sobre mí", is
read the same way. "About me" comes back as **plain text, exactly as
written** — the prompt is never asked to place the `{GROUP_A_*}`/
`{GROUP_B_*}` gaps; that stays `gaps.py`'s job, called separately by the web
layer once the text is back, using the same model that already places gaps
over text a person typed by hand. Contact fields follow rule 1 like
everything else: only what is literally in the text, never a guessed email
or phone number.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace

from flask_babel import gettext as _

from ancla.ai.client import AIClient, AIError, complete_with_budget
from ancla.profile import bullets as bullets_module
from ancla.profile import extraction
from ancla.profile.serialization import split_period
from ancla.profile.model import (
    AboutMe,
    Bilingual,
    Education,
    Experience,
    Language,
    Profile,
    Skill,
    SpokenLanguage,
)
from ancla.text import to_text, to_texts, json_block, normalize, slugify

# How much room to declare for the response Groq is asked to admit — see
# `ai.client.complete_with_budget`. This module reserves its own number
# instead of leaving it to `ai/groq.py`'s generic fallback because it is the
# one caller here whose response genuinely scales with what it sends: the
# model copies fields out of the CV, so a longer CV produces a longer
# answer, unlike the selection engine's fixed-shape ids and reasons or the
# "About me" gaps' six short fragments.
#
# Measured against the real API, single-language, across five real and
# synthetic CVs on two separate days: between 0.52 and 0.87
# completion tokens per character sent, depending on how densely the CV is
# written — a CV that is mostly short bullet lists costs more per character
# than one written in prose. A single sample was tried and wrong twice
# before this: 0.53 the first time, 0.867 the second. With that dispersion,
# the factor below is set against the worst ratio seen, not the average or
# the best — reserving too little is what cuts the JSON in half, and
# over-reserving only risks the 429 the SDK already retries on its own.
TOKENS_RESPUESTA_POR_CARACTER = 1.2
MIN_TOKENS_RESPUESTA = 1500

# Groq's free tier admits a request only if the system prompt (~1070 tokens,
# measured against the real API), the CV text (~1 token per 3.9 characters,
# also measured) and the declared response budget together fit under its
# 8000-tokens-per-minute ceiling. The response budget is
# `TOKENS_RESPUESTA_POR_CARACTER` above, so this is computed from that same
# constant rather than a second hardcoded ratio that could drift from it —
# that drift is exactly how the previous ceiling (8000 characters) ended up
# built on a per-language factor of 0.5 that the response's actual worst
# case had already outgrown by the time anyone measured it again.
_TOKENS_PROMPT_SISTEMA = 1070
_CARACTERES_POR_TOKEN_ENTRADA = 3.9
_TOKENS_POR_MINUTO_GRATIS = 8000
MAX_CARACTERES_CV = int(
    (_TOKENS_POR_MINUTO_GRATIS - _TOKENS_PROMPT_SISTEMA)
    / (1 / _CARACTERES_POR_TOKEN_ENTRADA + TOKENS_RESPUESTA_POR_CARACTER)
)
MAX_TOKENS_RESPUESTA = MAX_CARACTERES_CV  # never asked for more than a full CV could need

PLANTILLA_SISTEMA = """\
Analizas el texto de un CV para ayudar a una persona a construir su base de datos \
profesional. No escribes su CV: identificas qué hay en el texto y lo estructuras en \
SIETE categorías: experiencias, skills técnicas, skills personales, idiomas, educación, \
contacto y sobre mí.

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
propongas "Kubernetes" como skill aparte. Propón también unas pocas keywords de cómo se \
nombra en ofertas de empleo para cada experiencia, cada skill PERSONAL y cada idioma \
HABLADO — mismo criterio que para las skills técnicas.
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
12. Extrae también el CONTACTO: el nombre completo de la persona, la línea que va bajo \
el nombre si describe un rol o titulación (p. ej. "Ingeniero Informático", "Data \
Engineer" — nunca el nombre de una empresa), y las líneas de contacto sueltas (teléfono, \
email, ciudad, LinkedIn, GitHub, portfolio...) tal como aparecen. Nunca dependas de que \
haya un apartado con la palabra "Contacto": esta información suele ir junto al nombre, \
al principio del CV, sin ningún título propio. No inventes ni completes ningún dato de \
contacto que no esté escrito.
13. Extrae también el SOBRE MÍ: si el CV trae un párrafo de presentación personal — a \
veces bajo un título como "Sobre mí", "Perfil profesional", "Summary" u "Objective", \
pero a menudo sin ningún título, como el primer párrafo de prosa del documento — \
cópialo TAL CUAL, sin resumirlo, acortarlo ni reescribirlo con otras palabras: es la \
única categoría que se copia entera en vez de estructurarse en campos. Si el CV no trae \
ningún párrafo así, deja este campo vacío — no lo construyas a partir de la experiencia \
ni de las skills.

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
  ],
  "contacto": {{"nombre": "", "titular": "", "lineas": []}},
  "sobre_mi": ""
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


def _recortar(texto: str) -> tuple[str, str, str]:
    """The part of an oversized CV that fits, the warning to show for it, and
    what was left out.

    Cutting on a section boundary is what the warning is really for: the
    piece that was read is a whole run of sections and the piece that was
    not starts with its own title, so the advice can name the exact line to
    split the file on instead of a character count nobody can act on. That
    same boundary is what makes the leftover worth keeping instead of
    discarding: the caller can offer it back as a second, independent call
    later, on its own minute of quota, rather than making the user cut the
    file by hand.

    A CV with no recognisable section falls back to the line cut, which is
    not a lesser case to tidy up later: a CV pasted as one loose paragraph
    is ordinary, and whole lines are still the best cut available for it.
    """
    frontera = extraction.last_section_boundary(texto, MAX_CARACTERES_CV)
    if frontera is not None:
        analizados = frontera.position
        aviso = _(
            "Corta este CV justo antes de «%(seccion)s» e importa esa segunda parte "
            "por separado: no cabe entero de una vez. Se ha analizado todo lo "
            "anterior, %(analizados)s de sus %(total)s caracteres.",
            seccion=frontera.heading, analizados=analizados, total=len(texto),
        )
    else:
        analizados = _corte_por_linea(texto, MAX_CARACTERES_CV)
        aviso = _(
            "Corta este CV en dos partes e impórtalas por separado: no cabe "
            "entero de una vez. De los %(total)s caracteres que tiene, solo se "
            "han leído los primeros %(analizados)s.",
            total=len(texto), analizados=analizados,
        )
    return (
        texto[:analizados].rstrip() + "\n[...texto recortado...]",
        aviso,
        texto[analizados:].lstrip(),
    )


def _corte_por_linea(texto: str, limite: int) -> int:
    """Where to cut `texto` at or before `limite`, on a line break rather
    than mid-word, so the truncated text sent to the model still reads as
    whole lines instead of a sentence severed halfway through.

    Falls back to a hard cut at `limite` when there is no line break in at
    least the second half of the allowed range — a CV pasted as one giant
    paragraph, for instance — so a missing line break never throws away
    much more of the budget than it has to.
    """
    corte = texto.rfind("\n", limite // 2, limite)
    return corte if corte != -1 else limite


@dataclass(frozen=True)
class ContactCandidate:
    """Proposed name, headline and contact lines — the same three values
    `profile/store.py::save_contact` takes, kept together here only for
    convenience. Not a `profile/model.py` type: a contact has never been
    its own persisted shape, just three loose fields on `Profile`."""

    name: str = ""
    headline: Bilingual[str] = field(default_factory=lambda: Bilingual(es="", en=""))
    lines: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (self.name or self.lines or self.headline["es"] or self.headline["en"])


@dataclass(frozen=True)
class ImportResult:
    experiencias: list[Experience] = field(default_factory=list)
    skills: list[Skill] = field(default_factory=list)
    skills_personales: list[Skill] = field(default_factory=list)
    idiomas: list[SpokenLanguage] = field(default_factory=list)
    educacion: list[Education] = field(default_factory=list)
    # Single values, not lists: a CV has one name and one "About me", never
    # several candidates to choose among. `None` means nothing recognisable
    # was found, same convention as an empty title dropping an experience.
    contacto: ContactCandidate | None = None
    sobre_mi: AboutMe | None = None
    avisos: list[str] = field(default_factory=list)
    # What `_recortar` left out, if this CV was too long for one call. Empty
    # unless a cut happened — the web layer is what decides whether to keep
    # it around and offer it back as a second import.
    restante: str = ""


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
    restante = ""
    if not texto:
        return ImportResult(avisos=[_("No hay texto que analizar.")])
    if not cliente.available():
        return ImportResult(
            avisos=[_("No hay ninguna clave de API configurada. Ve a Ajustes.")]
        )

    if len(texto) > MAX_CARACTERES_CV:
        texto, aviso, restante = _recortar(texto)
        avisos.append(aviso)

    try:
        bruto = complete_with_budget(
            cliente, _system_prompt(idioma), texto, _reserved_tokens(texto)
        )
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
    experiencias = _split_paragraph_bullets(cliente, experiencias, idioma)
    duplicadas = (
        duplicadas_exp + duplicadas_skills + duplicadas_sp
        + duplicadas_idiomas + duplicadas_educacion
    )

    # Contact and "About me" are single values, never checked against the
    # profile for duplicates: re-importing a CV is meant to let the person
    # refresh their name or contact lines, not have them silently skipped
    # because a "Contacto" with that name already exists.
    contacto = _to_contact(datos.get("contacto"), idioma)
    sobre_mi = _to_about_me(datos.get("sobre_mi"), idioma)

    if not any((experiencias, skills, skills_personales, idiomas, educacion, contacto, sobre_mi)):
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
        contacto=contacto,
        sobre_mi=sobre_mi,
        avisos=avisos,
        restante=restante,
    )


def _split_paragraph_bullets(
    cliente: AIClient, experiencias: list[Experience], idioma: Language
) -> list[Experience]:
    """Splits into bullets the experiences whose "what I did" came back as
    one paragraph of prose — one extra call each, and only for those.

    A CV written in prose extracts as a single long bullet per job, which is
    not what a CV shows. Asking the main prompt to split as it extracts was
    the other option and was rejected: that prompt copies fields out of the
    text, and giving it a second job over the same text is what invites it
    to paraphrase while it is at it. The splitter gets the paragraph on its
    own and can only point at where to cut it (see `profile/bullets.py`).

    Failures are silent here, unlike the manual button: this runs behind an
    import the user did not ask to have reorganised, the text is already
    kept whole as one bullet either way, and the review screen it lands on
    is the place to split it by hand. A warning per experience about a
    convenience nobody requested would bury the ones that do matter.
    """
    divididas: list[Experience] = []
    for experiencia in experiencias:
        lista = experiencia.bullets[idioma]
        if not bullets_module.looks_unsplit(lista):
            divididas.append(experiencia)
            continue
        propuesta = bullets_module.suggest_split(cliente, lista[0])
        if len(propuesta.bullets) < 2:
            divididas.append(experiencia)
            continue
        otro: Language = "en" if idioma == "es" else "es"
        nuevos = Bilingual(
            **{idioma: propuesta.bullets, otro: experiencia.bullets[otro]}
        )
        divididas.append(replace(experiencia, bullets=nuevos))
    return divididas


# --------------------------------------------------------------------------
# Model response -> candidates
# --------------------------------------------------------------------------


def _reserved_tokens(texto: str) -> int:
    """Room to declare for the response, from the size of the CV text sent.

    See `TOKENS_RESPUESTA_POR_CARACTER` above for where the factor comes
    from. `texto` is already clamped to `MAX_CARACTERES_CV` by the caller,
    so this never has to clamp against a runaway input on its own.
    """
    escalado = int(len(texto) * TOKENS_RESPUESTA_POR_CARACTER)
    return max(MIN_TOKENS_RESPUESTA, min(MAX_TOKENS_RESPUESTA, escalado))


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
        category=_bilingual(datos.get("categoria"), idioma),
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


def _to_contact(datos: object, idioma: Language) -> ContactCandidate | None:
    """`nombre` and `lineas` are read as `_single_text`/plain lists — they
    are not bilingual, same as `Profile.name` and `Profile.contact`
    themselves. `titular` is the one field of the three that changes with
    the CV's language, so it goes through `_bilingual` like a title or a
    skill name: it lands under `idioma` and the other side stays empty for
    `translation.py`."""
    datos = _as_dict(datos)
    candidata = ContactCandidate(
        name=_single_text(datos.get("nombre")),
        headline=_bilingual(datos.get("titular"), idioma),
        lines=to_texts(datos.get("lineas")),
    )
    return None if candidata.is_empty() else candidata


def _to_about_me(datos: object, idioma: Language) -> AboutMe | None:
    """The paragraph as the model copied it, under `idioma` only — this
    module never asks for the `{GROUP_A_*}`/`{GROUP_B_*}` gaps, that is
    `gaps.py`'s job once this text is back (see the module docstring)."""
    texto = _single_text(datos)
    return AboutMe(template=_only(texto, idioma)) if texto.strip() else None


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
