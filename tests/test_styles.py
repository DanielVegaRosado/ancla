"""Guards the one stylesheet rule the interface silently depends on.

Several screens hide and show elements through the `hidden` attribute, from
the server and from `app.js` (the per-provider fields in Settings, the
untranslated badge, the draft warning). The browser applies `hidden` as
`display: none` from its own stylesheet, which **any** `display` rule in
ours overrides — so an element given a layout (`.campo { display: flex }`)
stays on screen while every check on the attribute says it is hidden.

That is exactly how a Settings field marked hidden kept showing, with the
HTML correct and the JavaScript correct. Nothing in the suite could catch
it, because the bug lives in the interaction between the two files.
"""
from __future__ import annotations

import re
from pathlib import Path

HOJA = Path(__file__).resolve().parent.parent / "ancla" / "web" / "static" / "style.css"

# `display` shorthand or not, with any amount of space, ending in !important.
_REGLA = re.compile(r"\[hidden\][^{]*\{[^}]*display\s*:\s*none\s*!important", re.IGNORECASE)


def test_la_hoja_de_estilos_hace_que_hidden_gane():
    assert _REGLA.search(HOJA.read_text(encoding="utf-8")), (
        "Falta `[hidden] { display: none !important; }` en style.css: sin esa "
        "regla, cualquier elemento con `display` propio se sigue viendo aunque "
        "esté marcado como oculto."
    )
