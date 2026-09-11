"""Text utilities shared across the whole package.

Only what more than one module needs lives here. This is deliberate: two
copies of the same normalisation end up drifting apart, and the day one
starts ignoring accents and the other does not, the engine will say
"Machine Learning" is a gap in the profile when the skill is right there.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Any


def to_text(valor: Any) -> str:
    """Clean text, or an empty string if what came in was not text.

    Anything read from outside — the model's response, a hand-edited YAML —
    can bring a number, `None`, or a list where text was expected. This is
    where it is decided, once, that such cases mean "empty", not an exception.
    """
    return valor.strip() if isinstance(valor, str) else ""


def to_texts(valor: Any) -> list[str]:
    """A list of non-empty texts, dropping anything that is not one."""
    if not isinstance(valor, list):
        return []
    return [limpio for elemento in valor if (limpio := to_text(elemento))]


MAX_SLUG = 80
"""Longest id `slugify` returns. Leaves ample room under the 255-byte file
name limit for `<id>.yaml.tmp` and the `-2` suffix the importer may add."""

_LARGO_HUELLA = 10


def slugify(texto: str) -> str:
    """Turns free text into a safe file identifier.

    "Data Engineer (Backend)" -> "data-engineer-backend"

    Two different texts must never share an id: the profile forms detect a
    duplicate by id and blame the name the person typed, so an id clash
    between two different names would be reported as a duplicate that does
    not exist. The readable ASCII part alone cannot guarantee that when it
    loses information — a name in Arabic, Chinese, Cyrillic... (which ASCII
    drops entirely), one made only of emoji, or one longer than `MAX_SLUG`.
    In those cases, and only those, a short hash of the normalised text is
    appended, so the id stays distinct and stable (same text, same id) while
    Latin names keep the plain ids they always had.

    The id stays ASCII on purpose rather than allowing Unicode file names:
    the store and the CV archive validate ids as `[a-z0-9._-]`, ids travel in
    URLs and inside zip backups (whose non-ASCII names Windows tools still
    mangle), macOS normalises file names to NFD so a Unicode id could stop
    matching its own file, and the 255 limit is in bytes, not characters.
    """
    descompuesto = unicodedata.normalize("NFKD", texto or "")
    sin_acentos = "".join(c for c in descompuesto if not unicodedata.combining(c))
    legible = re.sub(r"[^a-z0-9]+", "-", sin_acentos.lower()).strip("-")
    perdio_letras = any(c.isalnum() and not c.isascii() for c in sin_acentos)
    perdio_simbolos = not legible and bool(normalize(texto))
    if not (perdio_letras or perdio_simbolos or len(legible) > MAX_SLUG):
        return legible or "sin-titulo"

    huella = hashlib.blake2s(normalize(texto).encode("utf-8"), digest_size=_LARGO_HUELLA // 2).hexdigest()
    recortado = legible[: MAX_SLUG - _LARGO_HUELLA - 1].rstrip("-")
    return f"{recortado}-{huella}" if recortado else huella


def normalize(texto: str) -> str:
    """Lowercase, accent-free, and with no extra spaces, for comparison.

    Compares text written by different people — the user in their profile,
    the model in its response, the company in the posting — so "FastAPI",
    "fastapi", and "Fast API " all have to land in the same place.
    """
    descompuesto = unicodedata.normalize("NFKD", texto or "")
    sin_acentos = "".join(c for c in descompuesto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sin_acentos).strip().lower()


def json_block(texto: str) -> str | None:
    """The text's first balanced `{...}` object, or `None` if there is none.

    Models wrap JSON in ```json or precede it with a friendly sentence no
    matter how much the prompt forbids it; trimming it here is cheaper than
    spending another call. Counts brace depth and respects string literals
    (a `{` inside a bullet does not throw off the count), unlike simply
    grabbing the text's first and last brace.
    """
    inicio = (texto or "").find("{")
    if inicio == -1:
        return None
    profundidad = 0
    en_cadena = False
    escapado = False
    for pos in range(inicio, len(texto)):
        caracter = texto[pos]
        if en_cadena:
            if escapado:
                escapado = False
            elif caracter == "\\":
                escapado = True
            elif caracter == '"':
                en_cadena = False
        elif caracter == '"':
            en_cadena = True
        elif caracter == "{":
            profundidad += 1
        elif caracter == "}":
            profundidad -= 1
            if profundidad == 0:
                return texto[inicio : pos + 1]
    return None
