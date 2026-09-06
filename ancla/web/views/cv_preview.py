"""Preview screen: the proposal laid out as a printable CV, which the user
turns into a PDF with their browser's own Ctrl+P → Save as PDF.

The app never produces the PDF itself, exactly as it never produced the one
that comes out of Word: what it hands over is a document the user's own
program prints. That keeps the export path free of native dependencies —
and it is what lets the page break be *decided* (`break-inside: avoid`)
instead of estimated, because the browser is measuring real text.

Two entry points share the same core (`_preview`), mirroring the `.docx`
export: the proposal being reviewed and an already-archived CV.

Overflow is a warning, never a cut. `capacidad_experiencias` is how many
experiences the design was drawn around, so it belongs to the design — but
whether five of them actually look right on the page is the user's call,
which is why it arrives as an editable number instead of being read
straight from the sidecar. Above it, the CV still shows every experience
the proposal chose and the browser flows the extra onto a second page.
"""
from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for
from flask_babel import gettext as _

from ancla.archive import repository as archivo
from ancla.export import fill, html_layout, html_templates
from ancla.profile.model import Proposal
from ancla.web import context
from ancla.web import draft as modulo_borrador
from ancla.web.blueprint import bp


@bp.route("/propuesta/vista-previa")
def preview_proposal():
    borrador = modulo_borrador.load_draft(context.root())
    if borrador is None:
        flash(_("Esa propuesta ya no está disponible, genera una nueva."))
        return redirect(url_for("ancla.adapt"))

    return _preview(borrador.propuesta, volver=url_for("ancla.view_proposal"))


@bp.route("/cvs/<id_>/vista-previa")
def preview_cv(id_: str):
    cv = next((c for c in archivo.list_all(context.root()) if c.id == id_), None)
    if cv is None:
        flash(_("No se encuentra el CV «%(id)s» en el archivo.", id=id_))
        return redirect(url_for("ancla.list_cvs"))

    return _preview(cv.proposal, volver=url_for("ancla.view_cv", id_=id_))


@bp.route("/plantillas-html/<id_>.css")
def cv_stylesheet(id_: str):
    """Each template's print stylesheet, served from the templates folder
    rather than from `static/`: a design is its own pair of files, and
    keeping them together is what makes adding one a matter of dropping
    files in a folder. Only an id that a discovered template actually
    claims is ever resolved, so nothing outside the folder can be read."""
    plantilla = html_templates.find_template(context.html_templates_root(), id_)
    if plantilla is None or not plantilla.has_stylesheet():
        return "", 404
    return plantilla.stylesheet_path.read_text(encoding="utf-8"), 200, {"Content-Type": "text/css; charset=utf-8"}


def _preview(propuesta: Proposal, volver: str):
    plantilla = html_templates.find_template(
        context.html_templates_root(), request.args.get("plantilla_id", "")
    )
    if plantilla is None:
        flash(_("Esa plantilla ya no está disponible."))
        return redirect(volver)

    perfil = context.current_profile()
    experiencias = fill.resolved_experiences(propuesta, perfil)
    capacidad = _capacity(plantilla)
    cuerpo = html_layout.render(
        plantilla,
        propuesta,
        perfil,
        experiencias,
        perfil.name,
        photo_url=url_for("ancla.photo_file") if perfil.photo else "",
    )
    return render_template(
        "cv_preview.html",
        plantilla=plantilla,
        cuerpo=cuerpo,
        capacidad=capacidad,
        sobran=max(len(experiencias) - capacidad, 0),
        total_experiencias=len(experiencias),
        idioma=propuesta.language,
        volver=volver,
    )


def _capacity(plantilla: html_templates.HtmlTemplate) -> int:
    """How many experiences this CV is being laid out for: whatever the
    user asked for, or the number the design declares when they haven't
    said otherwise. A meaningless value falls back to the design's own
    instead of rejecting the preview — nothing about it can spoil the
    document, it only decides whether the warning shows."""
    try:
        pedida = int(request.args.get("capacidad", ""))
    except ValueError:
        return plantilla.capacity_experiences
    return pedida if pedida > 0 else plantilla.capacity_experiences
