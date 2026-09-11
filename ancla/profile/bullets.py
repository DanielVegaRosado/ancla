"""Splits a paragraph of experience into bullets, without rewriting a word.

People write what they did as running prose — that is how a CV arrives from
a PDF, and how most of us type into a box. A CV shows bullets. Turning one
into the other by hand means re-reading the paragraph and deciding where
each idea ends, which is exactly the kind of chore that stops a profile from
getting filled in.

**The model never returns text.** It answers with the literal fragments each
bullet *starts* with, `split_at` locates them inside what the user wrote
(`profile/literal_match.locate`) and cuts there. Every character of the
result comes from the user's own text, so even a model that ignores every
instruction and answers with prose of its own can only fail to match.

**Splitting is all-or-nothing**, unlike placing the "About me" gaps. There,
each fragment is independent and one that fails is simply a gap left
unmarked. Here a failed cut point is not independent: applying the first and
the third of three proposed cuts would silently swallow whatever lay between
them into the wrong bullet. So if any fragment is missing, or the fragments
do not appear in strictly increasing order, the whole split is dropped and
the text stays as one bullet.

**One fragment is a valid answer**, not a failure: a paragraph that is
already a single idea has no business being broken into artificial bullets,
and that case comes back silently as the text unchanged.

Never raises: a missing key, a provider failure, or an unusable answer come
back as the original text as a single bullet, plus a warning.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from flask_babel import gettext as _

from ancla.ai.client import AIClient, complete_with_budget
from ancla.profile.literal_match import locate
from ancla.text import json_block, to_texts

# A paragraph longer than this, holding more than one sentence, is what
# "written as running prose" looks like in practice. Both conditions are
# required: a long single sentence is one idea and has nothing to split, and
# two short sentences ("Backend. Python.") are already bullets in all but
# name. The numbers are a threshold for *asking* the model, never for
# cutting anything — getting them slightly wrong costs one call or one
# unoffered split, never a mangled text.
MIN_CARACTERES_PARRAFO = 220
MIN_PUNTUACION_FUERTE = 2
_PUNTUACION_FUERTE = ".;!?"

# Guard, not a budget: every bullet of one experience at once is a few
# hundred characters, and something ten times that is not a paragraph to
# split but a whole CV pasted into the wrong box. Trimming it would ask the
# model to cut a text it has not seen the end of.
MAX_CARACTERES_TEXTO = 4000

# How much room to declare for the response, via `ai.client.complete_with_budget`.
# The answer is a handful of opening fragments of a few words each, never
# the text back, so it does not scale with the paragraph the way the CV
# importer's response does.
RESERVED_TOKENS = 600

SISTEMA = """\
Señalas por dónde se corta en varios bullets un texto que una persona ya ha escrito \
sobre lo que hizo en un puesto o proyecto. NO reescribes su texto: solo indicas con qué \
palabras EMPIEZA cada bullet.

Reglas:
1. Cada fragmento se copia LITERAL del texto de esa persona, carácter por carácter, con \
sus mismas mayúsculas, tildes y puntuación. Si un solo fragmento no está tal cual en el \
texto, se descarta la división entera y el texto se queda como un único bullet.
2. Un fragmento son las primeras palabras del bullet, tres o cuatro, las justas para \
localizar el punto de corte sin ambigüedad. Nunca la frase entera.
3. El primer fragmento es el comienzo del texto, y los siguientes van en el mismo orden \
en que aparecen en él, sin solaparse ni repetirse.
4. Cada bullet es una idea con sentido propio. No cortes a mitad de una idea ni separes \
una frase de lo que la continúa.
5. Si el texto ya es una sola idea, devuelve un único fragmento: el comienzo del texto. \
Partirlo a la fuerza en bullets artificiales es peor que dejarlo entero.
6. No devuelvas el texto reescrito, ni resumido, ni traducido, ni explicaciones: solo \
fragmentos copiados del texto.

Responde ÚNICAMENTE con este JSON, sin texto alrededor ni bloques de código:
{
  "fragmentos": ["", ""]
}"""


@dataclass(frozen=True)
class SplitProposal:
    """The bullets to show, plus what to tell the user.

    `bullets` is always usable: on any failure it is the text that came in,
    as a single bullet.
    """

    bullets: list[str]
    avisos: list[str] = field(default_factory=list)


def looks_unsplit(bullets: list[str]) -> bool:
    """Whether this bullet list is really one paragraph of prose.

    Used to decide which experiences of an imported CV are worth a second
    call — see `MIN_CARACTERES_PARRAFO`.
    """
    if len(bullets) != 1:
        return False
    texto = bullets[0].strip()
    fuerte = sum(texto.count(signo) for signo in _PUNTUACION_FUERTE)
    return len(texto) >= MIN_CARACTERES_PARRAFO and fuerte >= MIN_PUNTUACION_FUERTE


def suggest_split(cliente: AIClient, texto: str) -> SplitProposal:
    """One call, one language: the fragments come out of the text sent, so
    there is nothing to keep paired across languages the way the "About me"
    gaps are."""
    texto = texto.strip()
    if not texto:
        return SplitProposal([])
    if not cliente.available():
        return SplitProposal(
            [texto], [_("No hay ninguna clave de API configurada. Ve a Ajustes.")]
        )
    if len(texto) > MAX_CARACTERES_TEXTO:
        return SplitProposal(
            [texto],
            [_("El texto es demasiado largo para dividirlo de una vez. Sepáralo a mano.")],
        )

    try:
        bruto = complete_with_budget(cliente, SISTEMA, texto, RESERVED_TOKENS)
    except Exception as exc:
        return SplitProposal([texto], [_("No se han podido proponer los bullets: %(error)s", error=exc)])

    fragmentos = _fragments(bruto)
    if fragmentos is None:
        return SplitProposal(
            [texto],
            [_("El modelo no ha devuelto una respuesta interpretable. Vuelve a intentarlo.")],
        )

    bullets = split_at(texto, fragmentos)
    if bullets is None:
        return SplitProposal(
            [texto],
            [_(
                "Los puntos de corte propuestos no aparecen tal cual en tu texto, así que "
                "se deja como un solo bullet. Sepáralo a mano o vuelve a intentarlo."
            )],
        )
    return SplitProposal(bullets)


def split_at(texto: str, fragmentos: list[str]) -> list[str] | None:
    """`texto` cut in front of each fragment, or `None` if the whole split
    has to be dropped.

    Dropped when a fragment is nowhere in the text, or when they do not
    appear in strictly increasing order — see the module docstring for why
    this is all-or-nothing. Each fragment is searched in the whole text, not
    from the previous cut onwards, so a model that answers out of order is
    rejected instead of silently reordered.

    Nothing is ever lost: whatever precedes the first cut joins the first
    bullet, so the bullets concatenated are the user's text again.
    """
    limpios = [fragmento.strip() for fragmento in fragmentos if fragmento.strip()]
    if not limpios:
        return None

    cortes: list[int] = []
    for fragmento in limpios:
        tramo = locate(texto, fragmento)
        if tramo is None:
            return None
        cortes.append(tramo[0])
    if any(anterior >= siguiente for anterior, siguiente in zip(cortes, cortes[1:])):
        return None

    cortes[0] = 0
    trozos = [texto[inicio:fin].strip() for inicio, fin in zip(cortes, cortes[1:] + [len(texto)])]
    return [trozo for trozo in trozos if trozo]


# --------------------------------------------------------------------------


def _fragments(bruto: str) -> list[str] | None:
    """The model's answer as a list of fragments, or `None` if it cannot be
    read at all. An answer with no fragments is unreadable too: "do not
    split" is expressed with one fragment, not with none."""
    bloque = json_block(bruto)
    if bloque is None:
        return None
    try:
        datos = json.loads(bloque)
    except json.JSONDecodeError:
        return None
    if not isinstance(datos, dict):
        return None
    return to_texts(datos.get("fragmentos")) or None
