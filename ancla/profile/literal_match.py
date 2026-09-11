"""Finds, inside the user's own text, a fragment a model copied from it.

Several helpers ask the model to point at text instead of producing it: the
"About me" gaps (`profile/gaps.py`) and the bullet splitter
(`profile/bullets.py`) both answer with literal fragments, and the code
locates each one and cuts or replaces *there*. That is what keeps "never
rewrite the user" guaranteed by architecture rather than by prompt: a model
that answers with words of its own can only fail to match.

Locating is the part they share, and it has to behave identically in all of
them — a tolerance that exists on one side and not the other would mean the
same answer places a gap but fails to split a paragraph, for no reason a
user could ever see.
"""
from __future__ import annotations

import re

# Characters a model may type in place of the hyphen the user wrote.
_DASHES = "-‐‑‒–—―−"
_SOFT_HYPHEN = "­"
_DASH = f"[{re.escape(_DASHES)}]"
# A word split across two lines by a justified paragraph ("back-\nend"),
# or joined by an invisible soft hyphen, which a model copies back whole.
_SPLIT_WORD = rf"(?:[{re.escape(_DASHES)}{_SOFT_HYPHEN}][^\S\n]*\n\s*|{_SOFT_HYPHEN})?"


def locate(texto: str, fragmento: str) -> tuple[int, int] | None:
    """Start and end of `fragmento` inside `texto`, or `None` if absent.

    An exact match wins, so text that matched before keeps matching in the
    same spot. Otherwise the search tolerates only differences of form that
    models introduce when copying: whitespace and line breaks, one kind of
    hyphen for another, and a word split by a line-end hyphen. Case and
    accents are never relaxed — a match there could land on words the user
    wrote differently, which is a different place, not a different shape of
    the same one.

    The caller is expected to use the returned span against its own text,
    never the fragment the model sent back.
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
