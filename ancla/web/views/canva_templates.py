"""Templates screen: a discreet link in the footer, outside the five main
screens — same pattern as Support.

The templates are design (Canva), not profile data: they live here as a
fixed list rather than in `perfil/`, because they are not something the
user edits from the app nor something that varies between installations.
`canva-templates/README.md`, at the repository root, documents the same
thing for anyone browsing the project on GitHub without running it.
"""
from __future__ import annotations

from dataclasses import dataclass

from flask import render_template
from flask_babel import gettext as _

from ancla.web.blueprint import bp


@dataclass(frozen=True)
class CanvaTemplate:
    nombre: str
    url: str


URL_MINIMALISTA_CALIDA = "https://www.canva.com/design/DAHHeNVzaGM/mggPEzw06NPeboGC6D5wCQ/edit"
URL_CORPORATIVA_CLASICA = "https://www.canva.com/design/DAHHeKwDZM4/RKBBp6YcMzbNCAdErRfSrQ/edit"


@bp.route("/plantillas")
def canva_templates():
    # The names are translated here, when building the response, not as a
    # module-level constant: `_()` only resolves the right language within
    # a request, and it also needs a literal (not a variable) for pybabel to
    # extract it into the catalog — which is why each name is written out
    # by hand in its own call, instead of in a loop.
    canva_templates = (
        CanvaTemplate(nombre=_("Minimalista Cálida"), url=URL_MINIMALISTA_CALIDA),
        CanvaTemplate(nombre=_("Corporativa Clásica"), url=URL_CORPORATIVA_CLASICA),
    )
    return render_template("canva_templates.html", canva_templates=canva_templates)
