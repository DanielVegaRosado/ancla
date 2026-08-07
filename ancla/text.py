"""Text utilities shared across the whole package.

Only what more than one module needs lives here. This is deliberate: two
copies of the same normalisation end up drifting apart, and the day one
starts ignoring accents and the other does not, the engine will say
"Machine Learning" is a gap in the profile when the skill is right there.
"""
from __future__ import annotations

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


def slugify(texto: str) -> str:
    """Turns free text into a safe file identifier.

    "Data Engineer (Backend)" -> "data-engineer-backend"
    """
    sin_acentos = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    minusculas = sin_acentos.lower().strip()
    con_guiones = re.sub(r"[^a-z0-9]+", "-", minusculas)
    return con_guiones.strip("-") or "sin-titulo"


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
