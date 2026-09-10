"""Proposes where the six "About me" gaps go inside the text the user wrote.

Writing the template by hand means typing `{GROUP_A_1}`…`{GROUP_B_3}`
character for character in two languages before anything can be saved. That
is the first wall for someone starting with an empty profile, so this module
lets a model mark the positions instead.

**The model never returns rewritten text.** It answers with the fragments it
proposes to replace in each language, and `place` swaps each one for its gap,
once. The fragment is only used to find the spot — tolerating the
typographic retouches models make while copying, like a different hyphen or
a dropped line break — and the span replaced is always the user's own. A
fragment that does not appear in what the user wrote is dropped, and the
gap comes back unplaced with a warning. That is what keeps "never rewrite
the user" guaranteed by architecture instead of by prompt: even a model that
ignores every instruction and answers with a whole paragraph of its own can
only fail to match, never edit.

Two consequences worth knowing before changing anything here:

- **The same gap is filled with the same skill in both languages** (see
  `AboutMe.render`), so the model is asked for the ES and the EN fragment of
  a gap together, in one call. Asking twice, once per language, would let
  `{GROUP_A_1}` land on unrelated ideas and the English CV would read as a
  different text.
- **Placing is partial, never all-or-nothing.** Whatever matches is placed;
  the rest is reported so the user can mark it by hand. Discarding four good
  positions because two fragments came back wrong would leave the person
  exactly at the wall this exists to remove.

Only the names of the *technical* skills travel in the prompt. Personal
skills and spoken languages never do — same rule that keeps them out of the
selection engine.

Never raises: a missing key, a provider failure, or an unusable answer come
back as the original template plus a warning. Marking gaps by hand works
with no provider at all, and this is only the accelerator on top.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from flask_babel import gettext as _

from ancla.ai.client import AIClient, complete_with_budget
from ancla.profile.model import AboutMe, Bilingual, Language, LANGUAGES, Skill
from ancla.profile.validation import language_name
from ancla.text import json_block, to_text

# Groq's free tier allows 8000 tokens per minute in total (checked against
# the real API, see `ia/groq.py`). Both texts, the skill names, and the
# answer share that budget, so the two inputs that grow without bound are
# capped. 2000 characters is around three times the longest "About me" that
# fits on a CV, and 40 names cover any realistic profile.
MAX_CARACTERES_SOBRE_MI = 2000
MAX_SKILLS = 40

# How much room to declare for the response, via `ai.client.complete_with_budget`.
# Unlike the CV importer, this does not scale with the length of either
# input text: the model always answers with exactly six short fragments —
# "the few words that name the concept", per the system prompt — never
# composed text, so a longer "About me" or a longer skill list changes what
# the model has to choose among, not how much it has to write back.
# Measured against the real API (checked 2026-09-06): 217 completion tokens
# for a realistic "About me" in both languages plus a 15-skill catalog. The
# margin here is wider than a single measurement alone would justify,
# because reserving too little is what leaves gaps unplaced with nothing to
# show for the call, and this call is cheap enough that a generous flat
# number costs nothing a real "About me" would ever need.
RESERVED_TOKENS = 800

_INTRO = """\
Señalas dónde van seis huecos dentro del «Sobre mí» que una persona ya ha escrito{idiomas}. \
NO reescribes su texto: solo indicas qué trozos exactos se sustituirán después por \
nombres de skills suyas.

Los seis huecos son GROUP_A_1, GROUP_A_2 y GROUP_A_3, que se rellenan con conceptos o \
dominios de trabajo (machine learning, backend, análisis de datos), y GROUP_B_1, \
GROUP_B_2 y GROUP_B_3, que se rellenan con lenguajes y tecnologías concretas (Python, \
Docker, PostgreSQL). Poner uno donde va el otro produce frases absurdas.

Reglas:
"""

_REGLA_LITERAL = (
    "Cada fragmento se copia LITERAL del texto de esa persona, carácter por carácter, con "
    "sus mismas mayúsculas, tildes y puntuación. Un fragmento que no esté tal cual en el "
    "texto se descarta y ese hueco se queda sin colocar."
)
_REGLA_CORTO = (
    "Un fragmento son las pocas palabras que nombran el concepto o la tecnología, nunca la "
    "frase entera: al sustituirlo por el nombre de una skill, la frase tiene que seguir "
    "leyéndose bien."
)
# Only meaningful with both languages: `AboutMe.render` fills a gap with one
# skill shared by the two (see module docstring), so with a single language
# there is nothing to keep paired.
_REGLA_PAREJA = (
    "El mismo hueco en español y en inglés marca la MISMA idea en el mismo punto de la "
    "frase. Los dos se rellenan con la misma skill, así que si no se corresponden el CV en "
    "inglés queda incoherente."
)
_REGLA_SIN_SOLAPE = "Los fragmentos no se solapan entre sí ni se repiten en dos huecos."
_REGLA_PARCIAL = (
    "Si el texto no da para los seis, deja vacíos los que no puedas. Es mejor un hueco sin "
    "colocar que un trozo señalado a la fuerza."
)
_REGLA_SIN_REESCRIBIR = (
    "No devuelvas el texto reescrito, ni frases nuevas, ni explicaciones, ni las skills "
    "que te paso: solo fragmentos copiados del texto."
)

_CIERRE = """
Responde ÚNICAMENTE con este JSON, sin texto alrededor ni bloques de código:
{esquema}"""


def _system_prompt(idiomas: tuple[Language, ...], huecos: tuple[str, ...]) -> str:
    """Built for one or two languages: the pairing rule and the mention of
    "español e inglés" only make sense when both are being asked for, and
    the JSON schema asks for a plain fragment per gap instead of an
    `{"es": ..., "en": ...}` pair when there is only one language to fill.

    Never mentions a language that has nothing written in it — there is no
    reason to point the model at an empty "Sobre mí" it was not asked to
    touch.
    """
    reglas = [_REGLA_LITERAL, _REGLA_CORTO]
    if len(idiomas) == 2:
        reglas.append(_REGLA_PAREJA)
    reglas += [_REGLA_SIN_SOLAPE, _REGLA_PARCIAL, _REGLA_SIN_REESCRIBIR]
    cuerpo_reglas = "\n".join(f"{n}. {regla}" for n, regla in enumerate(reglas, start=1))
    intro = _INTRO.format(idiomas=", en español y en inglés" if len(idiomas) == 2 else "")
    return intro + cuerpo_reglas + _CIERRE.format(esquema=_esquema_json(idiomas, huecos))


def _esquema_json(idiomas: tuple[Language, ...], huecos: tuple[str, ...]) -> str:
    nombres = [hueco.strip("{}") for hueco in huecos]
    if len(idiomas) == 2:
        relleno: object = {"es": "", "en": ""}
    else:
        relleno = ""
    return json.dumps({nombre: relleno for nombre in nombres}, indent=2)


@dataclass(frozen=True)
class GapProposal:
    """The template with whatever could be placed, plus what to tell the user.

    `about_me` is always usable: on any failure it is the text that came in,
    untouched.
    """

    about_me: AboutMe
    avisos: list[str] = field(default_factory=list)


def suggest_gaps(cliente: AIClient, sobre_mi: AboutMe, skills: list[Skill]) -> GapProposal:
    """One call for whichever languages have text. `skills` must be the
    technical catalog.

    With both languages written, the model is asked for the ES and the EN
    fragment of each gap together, in the same call (see module docstring:
    asking twice would let a gap land on unrelated ideas). With only one
    language written there is no pairing to ask for, so the request and the
    prompt drop it — see `_system_prompt`.
    """
    idiomas = tuple(idioma for idioma in LANGUAGES if sobre_mi.template[idioma].strip())
    if not idiomas:
        return GapProposal(sobre_mi, [_("Escribe primero tu «Sobre mí» en los dos idiomas.")])
    if not cliente.available():
        return GapProposal(
            sobre_mi, [_("No hay ninguna clave de API configurada. Ve a Ajustes.")]
        )

    huecos = sobre_mi.gaps()
    try:
        bruto = complete_with_budget(
            cliente,
            _system_prompt(idiomas, huecos),
            _request(sobre_mi, skills, idiomas),
            RESERVED_TOKENS,
        )
    except Exception as exc:
        return GapProposal(sobre_mi, [_("No se han podido proponer los huecos: %(error)s", error=exc)])

    fragmentos = _fragments(bruto, huecos, idiomas)
    if fragmentos is None:
        return GapProposal(
            sobre_mi,
            [_("El modelo no ha devuelto una respuesta interpretable. Vuelve a intentarlo.")],
        )

    textos: dict[Language, str] = {}
    avisos: list[str] = []
    for idioma in LANGUAGES:
        original = sobre_mi.template[idioma]
        # An empty language has nowhere to place a fragment — not the same
        # as the model failing to find one in real text.
        if not original.strip():
            textos[idioma] = original
            continue
        texto, sin_colocar = place(
            original,
            {hueco: pareja[idioma] for hueco, pareja in fragmentos.items()},
        )
        textos[idioma] = texto
        if sin_colocar:
            avisos.append(_aviso_sin_colocar(idioma, sin_colocar))
    return GapProposal(AboutMe(template=Bilingual(es=textos["es"], en=textos["en"])), avisos)


def place(texto: str, fragmentos: dict[str, str]) -> tuple[str, list[str]]:
    """Replaces each fragment with its gap, once each.

    Returns the resulting text and the gaps left unplaced, either because
    the fragment is empty or because it is not in the text — including the
    case where an earlier gap already consumed it, which is how overlapping
    fragments end up rejected instead of tangled.

    The fragment only says *where* the gap goes (see `_locate`); what gets
    replaced is always the span as it stands in the user's text, so a model
    that retyped a hyphen or dropped a line break still cannot put a single
    character of its own into the result.

    A gap already present in the text is left where the user put it: this
    screen's manual marking and this proposal edit the same field, and the
    proposal never moves what has already been decided by hand.
    """
    resultado = texto
    sin_colocar: list[str] = []
    for hueco, fragmento in fragmentos.items():
        if hueco in resultado:
            continue
        tramo = _locate(resultado, fragmento.strip())
        if tramo is None:
            sin_colocar.append(hueco)
            continue
        inicio, fin = tramo
        resultado = resultado[:inicio] + hueco + resultado[fin:]
    return resultado, sin_colocar


# Characters a model may type in place of the hyphen the user wrote.
_DASHES = "-\u2010\u2011\u2012\u2013\u2014\u2015\u2212"
_SOFT_HYPHEN = "\u00ad"
_DASH = f"[{re.escape(_DASHES)}]"
# A word split across two lines by a justified paragraph ("back-\nend"),
# or joined by an invisible soft hyphen, which a model copies back whole.
_SPLIT_WORD = rf"(?:[{re.escape(_DASHES)}{_SOFT_HYPHEN}][^\S\n]*\n\s*|{_SOFT_HYPHEN})?"


def _locate(texto: str, fragmento: str) -> tuple[int, int] | None:
    """Start and end of `fragmento` inside `texto`, or `None` if absent.

    An exact match wins, so text that placed before keeps placing in the
    same spot. Otherwise the search tolerates only differences of form that
    models introduce when copying: whitespace and line breaks, one kind of
    hyphen for another, and a word split by a line-end hyphen. Case and
    accents are never relaxed — a match there could land the gap on words
    the user wrote differently, which is a different place, not a different
    shape of the same one.
    """
    if not fragmento:
        return None
    inicio = texto.find(fragmento)
    if inicio != -1:
        return inicio, inicio + len(fragmento)
    coincidencia = _tolerant_pattern(fragmento).search(texto)
    return coincidencia.span() if coincidencia else None


def _tolerant_pattern(fragmento: str) -> re.Pattern[str]:
    partes: list[str] = []
    anterior = ""
    for caracter in fragmento:
        if caracter.isspace():
            if not anterior.isspace():
                partes.append(r"\s+")
        elif caracter in _DASHES:
            partes.append(_DASH + r"\s*")
        else:
            if anterior.isalnum() and caracter.isalnum():
                partes.append(_SPLIT_WORD)
            partes.append(re.escape(caracter))
        anterior = caracter
    return re.compile("".join(partes))


# --------------------------------------------------------------------------


_ETIQUETA_IDIOMA = {"es": "ES", "en": "EN"}


def _request(sobre_mi: AboutMe, skills: list[Skill], idiomas: tuple[Language, ...]) -> str:
    partes = [
        f"Sobre mí ({_ETIQUETA_IDIOMA[idioma]}):\n{_trim(sobre_mi.template[idioma])}"
        for idioma in idiomas
    ]
    nombres = _skill_names(skills)
    if nombres:
        partes.append("Skills técnicas de esta persona: " + ", ".join(nombres))
    return "\n\n".join(partes)


def _trim(texto: str) -> str:
    texto = texto.strip()
    return texto[:MAX_CARACTERES_SOBRE_MI]


def _skill_names(skills: list[Skill]) -> list[str]:
    """Names only, no categories or keywords: they are there so the model
    picks fragments that can actually be swapped for one of them, and the
    descriptions would multiply the cost of the call without changing which
    words it points at."""
    nombres: list[str] = []
    vistos: set[str] = set()
    for skill in skills[:MAX_SKILLS]:
        for nombre in (skill.name["es"], skill.name["en"]):
            nombre = nombre.strip()
            if nombre and nombre.lower() not in vistos:
                vistos.add(nombre.lower())
                nombres.append(nombre)
    return nombres


def _fragments(
    bruto: str, huecos: tuple[str, ...], idiomas: tuple[Language, ...]
) -> dict[str, Bilingual[str]] | None:
    """The model's answer as `{gap: fragments}`, or `None` if it cannot be
    read at all. The gaps come from `AboutMe`, so anything the model made up
    on its own is ignored rather than trusted."""
    bloque = json_block(bruto)
    if bloque is None:
        return None
    try:
        datos = json.loads(bloque)
    except json.JSONDecodeError:
        return None
    if not isinstance(datos, dict):
        return None
    # The skeleton in the prompt asks for the name without braces, but a
    # model that copies the gap as it appears in the text is answering the
    # question just as well.
    return {
        hueco: _bilingual(datos.get(hueco.strip("{}"), datos.get(hueco)), idiomas)
        for hueco in huecos
    }


def _bilingual(datos: object, idiomas: tuple[Language, ...]) -> Bilingual[str]:
    """Reads one gap's answer in whatever shape `_system_prompt` asked for:
    `{"es": ..., "en": ...}` for two languages, a plain fragment for one.
    The language that was not asked for stays empty — `place()` never looks
    at it, because that is exactly the language whose original text is
    empty too."""
    if len(idiomas) == 1:
        fragmento = to_text(datos)
        return Bilingual(**{idiomas[0]: fragmento, _other(idiomas[0]): ""})
    datos = datos if isinstance(datos, dict) else {}
    return Bilingual(es=to_text(datos.get("es")), en=to_text(datos.get("en")))


def _other(idioma: Language) -> Language:
    return "en" if idioma == "es" else "es"


def _aviso_sin_colocar(idioma: Language, huecos: list[str]) -> str:
    return _(
        "En %(idioma)s no se han podido colocar estos huecos: %(huecos)s. "
        "Márcalos tú: selecciona las palabras y pulsa el botón del hueco.",
        idioma=language_name(idioma),
        huecos=", ".join(huecos),
    )
