"""Proposes where the six "About me" gaps go inside the text the user wrote.

Writing the template by hand means typing `{GROUP_A_1}`…`{GROUP_B_3}`
character for character in two languages before anything can be saved. That
is the first wall for someone starting with an empty profile, so this module
lets a model mark the positions instead.

**The model never returns rewritten text.** It answers with the fragments it
proposes to replace in each language, and `place` swaps each one for its gap
with a literal, single-occurrence replacement. A fragment that does not
appear verbatim in what the user wrote is dropped, and the gap comes back
unplaced with a warning. That is what keeps "never rewrite the user"
guaranteed by architecture instead of by prompt: even a model that ignores
every instruction and answers with a whole paragraph of its own can only
fail to match, never edit.

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

SISTEMA = """\
Señalas dónde van seis huecos dentro del «Sobre mí» que una persona ya ha escrito, en \
español y en inglés. NO reescribes su texto: solo indicas qué trozos exactos se \
sustituirán después por nombres de skills suyas.

Los seis huecos son GROUP_A_1, GROUP_A_2 y GROUP_A_3, que se rellenan con conceptos o \
dominios de trabajo (machine learning, backend, análisis de datos), y GROUP_B_1, \
GROUP_B_2 y GROUP_B_3, que se rellenan con lenguajes y tecnologías concretas (Python, \
Docker, PostgreSQL). Poner uno donde va el otro produce frases absurdas.

Reglas:
1. Cada fragmento se copia LITERAL del texto de esa persona, carácter por carácter, con \
sus mismas mayúsculas, tildes y puntuación. Un fragmento que no esté tal cual en el \
texto se descarta y ese hueco se queda sin colocar.
2. Un fragmento son las pocas palabras que nombran el concepto o la tecnología, nunca la \
frase entera: al sustituirlo por el nombre de una skill, la frase tiene que seguir \
leyéndose bien.
3. El mismo hueco en español y en inglés marca la MISMA idea en el mismo punto de la \
frase. Los dos se rellenan con la misma skill, así que si no se corresponden el CV en \
inglés queda incoherente.
4. Los fragmentos no se solapan entre sí ni se repiten en dos huecos.
5. Si el texto no da para los seis, deja vacíos los que no puedas. Es mejor un hueco sin \
colocar que un trozo señalado a la fuerza.
6. No devuelvas el texto reescrito, ni frases nuevas, ni explicaciones, ni las skills \
que te paso: solo fragmentos copiados del texto.

Responde ÚNICAMENTE con este JSON, sin texto alrededor ni bloques de código:
{
  "GROUP_A_1": {"es": "", "en": ""},
  "GROUP_A_2": {"es": "", "en": ""},
  "GROUP_A_3": {"es": "", "en": ""},
  "GROUP_B_1": {"es": "", "en": ""},
  "GROUP_B_2": {"es": "", "en": ""},
  "GROUP_B_3": {"es": "", "en": ""}
}"""


@dataclass(frozen=True)
class GapProposal:
    """The template with whatever could be placed, plus what to tell the user.

    `about_me` is always usable: on any failure it is the text that came in,
    untouched.
    """

    about_me: AboutMe
    avisos: list[str] = field(default_factory=list)


def suggest_gaps(cliente: AIClient, sobre_mi: AboutMe, skills: list[Skill]) -> GapProposal:
    """One call for both languages. `skills` must be the technical catalog."""
    if not any(sobre_mi.template[idioma].strip() for idioma in LANGUAGES):
        return GapProposal(sobre_mi, [_("Escribe primero tu «Sobre mí» en los dos idiomas.")])
    if not cliente.available():
        return GapProposal(
            sobre_mi, [_("No hay ninguna clave de API configurada. Ve a Ajustes.")]
        )

    try:
        bruto = complete_with_budget(cliente, SISTEMA, _request(sobre_mi, skills), RESERVED_TOKENS)
    except Exception as exc:
        return GapProposal(sobre_mi, [_("No se han podido proponer los huecos: %(error)s", error=exc)])

    fragmentos = _fragments(bruto, sobre_mi.gaps())
    if fragmentos is None:
        return GapProposal(
            sobre_mi,
            [_("El modelo no ha devuelto una respuesta interpretable. Vuelve a intentarlo.")],
        )

    textos: dict[Language, str] = {}
    avisos: list[str] = []
    for idioma in LANGUAGES:
        texto, sin_colocar = place(
            sobre_mi.template[idioma],
            {hueco: pareja[idioma] for hueco, pareja in fragmentos.items()},
        )
        textos[idioma] = texto
        if sin_colocar:
            avisos.append(_aviso_sin_colocar(idioma, sin_colocar))
    return GapProposal(AboutMe(template=Bilingual(es=textos["es"], en=textos["en"])), avisos)


def place(texto: str, fragmentos: dict[str, str]) -> tuple[str, list[str]]:
    """Replaces each fragment with its gap, literally and once each.

    Returns the resulting text and the gaps left unplaced, either because
    the fragment is empty or because it is not in the text word for word —
    including the case where an earlier gap already consumed it, which is
    how overlapping fragments end up rejected instead of tangled.

    A gap already present in the text is left where the user put it: this
    screen's manual marking and this proposal edit the same field, and the
    proposal never moves what has already been decided by hand.
    """
    resultado = texto
    sin_colocar: list[str] = []
    for hueco, fragmento in fragmentos.items():
        if hueco in resultado:
            continue
        fragmento = fragmento.strip()
        if not fragmento or fragmento not in resultado:
            sin_colocar.append(hueco)
            continue
        resultado = resultado.replace(fragmento, hueco, 1)
    return resultado, sin_colocar


# --------------------------------------------------------------------------


def _request(sobre_mi: AboutMe, skills: list[Skill]) -> str:
    partes = [
        f"Sobre mí (ES):\n{_trim(sobre_mi.template['es'])}",
        f"Sobre mí (EN):\n{_trim(sobre_mi.template['en'])}",
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


def _fragments(bruto: str, huecos: tuple[str, ...]) -> dict[str, Bilingual[str]] | None:
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
        hueco: _bilingual(datos.get(hueco.strip("{}"), datos.get(hueco)))
        for hueco in huecos
    }


def _bilingual(datos: object) -> Bilingual[str]:
    datos = datos if isinstance(datos, dict) else {}
    return Bilingual(es=to_text(datos.get("es")), en=to_text(datos.get("en")))


def _aviso_sin_colocar(idioma: Language, huecos: list[str]) -> str:
    return _(
        "En %(idioma)s no se han podido colocar estos huecos: %(huecos)s. "
        "Márcalos tú: selecciona las palabras y pulsa el botón del hueco.",
        idioma=language_name(idioma),
        huecos=", ".join(huecos),
    )
