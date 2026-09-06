"""Guards the English catalog, which no other test looks at.

The `.po` is a single large file edited in batches at the end of each piece
of work, and three different failures have already reached the screen from
it: a string left untranslated shows in Spanish, an escape written as
`\\u00ab` instead of `«` is printed literally, and a placeholder that does
not match the original breaks rendering — that last one even stops
`pybabel compile`, which is easy to miss when the suite is green anyway.

Reads the `.po` rather than the compiled `.mo`: it is the file people edit,
and it is where the mistakes are made.
"""
from __future__ import annotations

import re
from pathlib import Path

CATALOGO = (
    Path(__file__).resolve().parent.parent
    / "ancla" / "translations" / "en" / "LC_MESSAGES" / "messages.po"
)

_ENTRADA = re.compile(
    r'(#, fuzzy\n)?msgid ((?:"(?:[^"\\]|\\.)*"\n)+)msgstr ((?:"(?:[^"\\]|\\.)*"\n?)+)'
)
_TROZO = re.compile(r'"((?:[^"\\]|\\.)*)"')
_MARCADOR = re.compile(r"%\([a-z_]+\)s")


def _entradas() -> list[tuple[str, str, bool]]:
    """Every (original, translation, is_fuzzy) in the catalog, with the
    quoting undone. A long message is split across several quoted lines in a
    `.po`, hence the join."""
    texto = CATALOGO.read_text(encoding="utf-8")
    entradas = []
    for coincidencia in _ENTRADA.finditer(texto):
        original = "".join(_TROZO.findall(coincidencia.group(2)))
        traduccion = "".join(_TROZO.findall(coincidencia.group(3)))
        if original:  # the header entry has an empty msgid
            entradas.append((original, traduccion, bool(coincidencia.group(1))))
    return entradas


def test_no_queda_ninguna_cadena_sin_traducir():
    faltan = [original for original, traduccion, _ in _entradas() if not traduccion]

    assert not faltan, "Cadenas que se verían en español: " + " | ".join(faltan)


def test_no_queda_ninguna_traduccion_marcada_como_dudosa():
    """A fuzzy entry is a guess `pybabel` made from a similar string, and it
    is often about something else entirely: it needs a person to confirm
    it, not to be shipped."""
    dudosas = [original for original, _, fuzzy in _entradas() if fuzzy]

    assert not dudosas, "Traducciones sin confirmar: " + " | ".join(dudosas)


def test_los_marcadores_de_una_traduccion_son_los_de_su_original():
    """A translation naming a placeholder the original does not have fails
    at render time, and one that drops a placeholder silently loses whatever
    it was going to say."""
    descuadrados = [
        f"{original!r} -> {traduccion!r}"
        for original, traduccion, _ in _entradas()
        if traduccion and set(_MARCADOR.findall(original)) != set(_MARCADOR.findall(traduccion))
    ]

    assert not descuadrados, "Marcadores que no cuadran: " + " | ".join(descuadrados)


def test_ninguna_traduccion_lleva_escapes_unicode_sin_resolver():
    """`\\u00ab` in a `.po` is four characters, not «: gettext does not
    decode it, so it reaches the screen as written."""
    con_escapes = [
        original
        for original, traduccion, _ in _entradas()
        if re.search(r"\\\\u[0-9a-fA-F]{4}", traduccion)
    ]

    assert not con_escapes, "Traducciones con escapes literales: " + " | ".join(con_escapes)
