"""Preview screen: the proposal laid out as a printable CV, which the user
turns into a PDF with their browser's own Ctrl+P → Save as PDF.

The app never produces the PDF itself, exactly as it never produced the one
that comes out of Word: what it hands over is a document the user's own
program prints. That keeps the export path free of native dependencies —
and it is what lets the page break be *decided* (`break-inside: avoid`)
instead of estimated, because the browser is measuring real text.

Both entry points share the same core (`_preview`): the proposal being
reviewed and an already-archived CV.

Overflow here does not just happen — a printed CV that ends with two
entries and half a blank sheet is the whole reason this screen enforces a
range instead of only warning about one, and the type is then measured
down to whatever fits the rest (`static/cv_fit.js`, see
`html-templates/README.md`). Only a text too long for even the smallest
type still prints two pages, and the screen says so first.
`capacidad` is how many experiences actually
go on the page: clamped to the template's own `[capacity_min, capacity_max]`
range rather than read straight off the sidecar, because the design's
range is a starting point and whether that many really look right is the
user's call. Whatever sits beyond it is left out of the render and named
on screen instead, with its selection reason — never disappearing
silently. Fewer experiences than `capacity_min` is not cut short the
other way: rule 1 forbids padding the CV with anything that isn't in the
profile, so the page prints exactly what there is, with a notice that the
design was drawn for more.
"""
from __future__ import annotations

from flask import flash, redirect, render_template, request, session, url_for
from flask_babel import gettext as _

from ancla.archive import repository as archivo
from ancla.export import fields, html_layout, html_templates
from ancla.profile.model import Proposal
from ancla.web import context
from ancla.web import draft as modulo_borrador
from ancla.web.blueprint import bp

# Session key for the last chosen capacity, per template id. The session
# (not the draft) is what this belongs to: the same preference must also
# hold for an already-archived CV's preview (`preview_cv`), which has no
# draft at all, and it is a UI habit tied to this browser, not a fact of
# the proposal being reviewed. Keyed by template id rather than a single
# number because each design has its own `[capacity_min, capacity_max]`
# range — what fits a dense one-column layout doesn't fit a spacious one.
_CLAVE_SESION_CAPACIDAD = "capacidad_html"


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
    seleccion = fields.resolved_selection(propuesta, perfil)
    capacidad = _capacity(plantilla)
    incluidas = seleccion[:capacidad]
    excluidas = seleccion[capacidad:]
    experiencias = [experiencia for _, experiencia in incluidas]
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
        excluidas=excluidas,
        total_experiencias=len(seleccion),
        bajo_el_minimo=len(incluidas) < plantilla.capacity_min,
        idioma=propuesta.language,
        volver=volver,
    )


def _capacity(plantilla: html_templates.HtmlTemplate) -> int:
    """How many experiences actually go on the page: whatever the user
    asked for, clamped to the template's own `[capacity_min, capacity_max]`
    — a value the user cannot spoil, unlike the old free-standing warning,
    because letting it exceed `capacity_max` is exactly what used to spill
    onto a second page. A missing or unreadable request falls back to
    whatever was last chosen for this same template in this session, and
    only then to the design's own maximum (or its minimum, if it declares
    no maximum at all) — the choice made this call is remembered for next
    time either way, so a plain reload or a trip back to the form and
    back doesn't reset it."""
    minimo = max(plantilla.capacity_min, 1)
    por_defecto = plantilla.capacity_max if plantilla.capacity_max > 0 else minimo
    recordada = _capacidad_recordada(plantilla.id)
    try:
        pedida = int(request.args["capacidad"])
    except (KeyError, ValueError):
        pedida = recordada if recordada is not None else por_defecto
    pedida = max(pedida, minimo)
    if plantilla.capacity_max > 0:
        pedida = min(pedida, plantilla.capacity_max)
    _recordar_capacidad(plantilla.id, pedida)
    return pedida


def _capacidad_recordada(plantilla_id: str) -> int | None:
    return session.get(_CLAVE_SESION_CAPACIDAD, {}).get(plantilla_id)


def _recordar_capacidad(plantilla_id: str, capacidad: int) -> None:
    # Flask only detects a session write when the value itself is
    # reassigned, not when a nested dict already inside it is mutated in
    # place — so a fresh dict is built and reassigned rather than patched.
    recordadas = dict(session.get(_CLAVE_SESION_CAPACIDAD, {}))
    recordadas[plantilla_id] = capacidad
    session[_CLAVE_SESION_CAPACIDAD] = recordadas
