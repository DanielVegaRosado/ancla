"""Export screen: turn a proposal into a filled `.docx`, picking one of the
templates declared in `docx-templates/` (see `ancla/export/templates.py`).

Two entry points share the same core (`_build_or_overflow`): the proposal
still being reviewed (`/propuesta/exportar`) and an already-archived CV
(`/cvs/<id>/exportar`) — a saved CV is exactly as exportable as a draft
one, the only difference is where its `Proposal` comes from and where
"back" points to.

The one piece of interaction this needs is the overflow question: when the
proposal has more experiences than the chosen template declares room for,
nothing gets silently cut. `_build_or_overflow` renders a confirmation
screen instead, and the same route is posted to again with the user's
choice (`desbordamiento`) to actually produce the file.
"""
from __future__ import annotations

from flask import Response, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _

from ancla.archive import repository as archivo
from ancla.export import fill, templates
from ancla.profile.model import Profile, Proposal, SelectedExperience
from ancla.web import context
from ancla.web import draft as modulo_borrador
from ancla.web.blueprint import bp

MIMETYPE_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

DESBORDAMIENTO_RELEVANTES = "relevantes"
DESBORDAMIENTO_TODAS = "todas"


@bp.route("/propuesta/exportar", methods=["POST"])
def export_proposal():
    borrador = modulo_borrador.load_draft(context.root())
    if borrador is None:
        flash(_("Esa propuesta ya no está disponible, genera una nueva."))
        return redirect(url_for("ancla.adapt"))

    return _build_or_overflow(
        borrador.propuesta,
        accion_exportar=url_for("ancla.export_proposal"),
        volver=url_for("ancla.view_proposal"),
        nombre_fichero="cv",
    )


@bp.route("/cvs/<id_>/exportar", methods=["POST"])
def export_cv(id_: str):
    cv = next((c for c in archivo.list_all(context.root()) if c.id == id_), None)
    if cv is None:
        flash(_("No se encuentra el CV «%(id)s» en el archivo.", id=id_))
        return redirect(url_for("ancla.list_cvs"))

    return _build_or_overflow(
        cv.proposal,
        accion_exportar=url_for("ancla.export_cv", id_=id_),
        volver=url_for("ancla.view_cv", id_=id_),
        nombre_fichero=cv.id,
    )


def _build_or_overflow(propuesta: Proposal, accion_exportar: str, volver: str, nombre_fichero: str):
    plantilla = templates.find_template(context.docx_templates_root(), request.form.get("plantilla_id", ""))
    if plantilla is None:
        flash(_("Esa plantilla ya no está disponible."))
        return redirect(volver)

    perfil = context.current_profile()
    seleccion = fill.resolved_selection(propuesta, perfil)
    seleccion = _completada_hasta_capacidad(seleccion, perfil, plantilla)

    desbordamiento = request.form.get("desbordamiento", "")
    if _overflows(seleccion, plantilla) and desbordamiento not in (
        DESBORDAMIENTO_RELEVANTES,
        DESBORDAMIENTO_TODAS,
    ):
        return render_template(
            "export_overflow.html",
            plantilla=plantilla,
            incluidas=seleccion[: plantilla.capacity_experiences],
            excluidas=seleccion[plantilla.capacity_experiences :],
            idioma=propuesta.language,
            accion_exportar=accion_exportar,
            volver=volver,
        )

    if desbordamiento == DESBORDAMIENTO_RELEVANTES and _overflows(seleccion, plantilla):
        seleccion = seleccion[: plantilla.capacity_experiences]
    experiencias = [experiencia for _, experiencia in seleccion]

    contenido = fill.render(plantilla, propuesta, perfil, experiencias, perfil.name, context.root())
    return Response(
        contenido,
        mimetype=MIMETYPE_DOCX,
        headers={"Content-Disposition": f'attachment; filename="{nombre_fichero}-{plantilla.id}.docx"'},
    )


def _overflows(seleccion: list, plantilla: templates.ExportTemplate) -> bool:
    return plantilla.capacity_experiences > 0 and len(seleccion) > plantilla.capacity_experiences


def _completada_hasta_capacidad(
    seleccion: list, perfil: Profile, plantilla: templates.ExportTemplate
) -> list:
    """Tops the selection up to the template's capacity with profile
    experiences the AI selection engine did not pick, so a template built
    for N experiences always shows N when the profile has at least that
    many, instead of silently showing fewer — the AI's default pick count
    is independent of any given template's capacity. Plain fill, not a
    relevance choice: no reason is attached, unlike an AI-selected
    experience.
    """
    capacidad = plantilla.capacity_experiences
    faltan = capacidad - len(seleccion)
    if capacidad <= 0 or faltan <= 0:
        return seleccion
    ids_incluidos = {seleccionada.id for seleccionada, _ in seleccion}
    candidatas = [e for e in perfil.experiences if e.id not in ids_incluidos]
    relleno = [(SelectedExperience(id=experiencia.id), experiencia) for experiencia in candidatas[:faltan]]
    return seleccion + relleno
