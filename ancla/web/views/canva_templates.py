"""Templates screen: a discreet link in the footer nav, outside the five
main screens — same pattern as Support.

The templates are design references (PDFs Daniel exported from Canva by
hand), not profile data: they live in `canva-templates/` rather than in
`perfil/`, because they are not something the user edits from the app nor
something that varies between installations. Shown inline, full-page —
never a redirect out to canva.com, so the app stays the only place a user
needs to be to see them.
"""
from __future__ import annotations

from flask import abort, render_template, send_file

from ancla.design import gallery
from ancla.web import context
from ancla.web.blueprint import bp


@bp.route("/plantillas")
def canva_templates():
    plantillas = gallery.list_templates(context.canva_templates_root())
    return render_template("canva_templates.html", canva_templates=plantillas, idioma=context.current_language())


@bp.route("/plantillas/<id>")
def canva_template_detail(id: str):
    plantilla = gallery.find_template(context.canva_templates_root(), id)
    if plantilla is None:
        abort(404)
    return render_template("canva_template_detail.html", plantilla=plantilla, idioma=context.current_language())


@bp.route("/plantillas/<id>/archivo")
def canva_template_file(id: str):
    plantilla = gallery.find_template(context.canva_templates_root(), id)
    if plantilla is None:
        abort(404)
    return send_file(plantilla.path)
