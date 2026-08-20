"""My CVs screen: the historical archive of saved proposals."""
from __future__ import annotations

import uuid
from collections import Counter

from flask import abort, flash, redirect, render_template, request, send_file, url_for
from flask_babel import gettext as _

from ancla.archive import repository as archivo
from ancla.export import templates as plantillas_docx
from ancla.profile.model import CVStatus, SavedCV
from ancla.proposal.format import to_markdown, to_text
from ancla.web import context
from ancla.web.blueprint import bp
from ancla.web.presentation import etiquetas_estado


@bp.route("/cvs")
def list_cvs():
    """The status summary doubles as a filter: each card carries the value
    to filter by (`filtro`), and "Total" (`filtro="todos"`) clears it. The
    filtering itself is client-side JS (`app.js`) over each card's
    `data-estado` — no need for a server round trip for something this
    simple, and every CV is still visible without JS."""
    cvs = archivo.list_all(context.root())
    conteo = Counter(cv.status for cv in cvs)
    etiquetas = etiquetas_estado()
    resumen_estados = [{"etiqueta": _("Total"), "cantidad": len(cvs), "filtro": "todos"}] + [
        {"etiqueta": etiquetas[estado], "cantidad": conteo[estado], "filtro": estado.value}
        for estado in CVStatus
    ]
    return render_template("cvs.html", cvs=cvs, resumen_estados=resumen_estados)


def _find_or_none(id_: str):
    return next((c for c in archivo.list_all(context.root()) if c.id == id_), None)


@bp.route("/cvs/<id_>")
def view_cv(id_: str):
    cv = _find_or_none(id_)
    if cv is None:
        flash(_("No se encuentra el CV «%(id)s» en el archivo.", id=id_))
        return redirect(url_for("ancla.list_cvs"))

    perfil = context.current_profile()
    return render_template(
        "cv_detail.html",
        cv=cv,
        perfil=perfil,
        texto_plano=to_text(cv.proposal, perfil),
        texto_markdown=to_markdown(cv.proposal, perfil),
        estados=list(CVStatus),
        plantillas_docx=plantillas_docx.list_templates(context.docx_templates_root()),
        adjuntos=_display_names(cv),
    )


def _display_names(cv: SavedCV) -> list[tuple[str, str]]:
    """`(nombre_en_disco, nombre_a_mostrar)` for each attachment — the
    file name on disk is prefixed with the CV's own id to keep two CVs'
    attachments from colliding in the shared folder (see
    `repository._unique_attachment_path`), which isn't something the user
    needs to see."""
    prefijo = f"{cv.id}__"
    return [(nombre, nombre.removeprefix(prefijo)) for nombre in cv.attachments]


@bp.route("/cvs/<id_>/estado", methods=["POST"])
def change_cv_status(id_: str):
    estado = request.form.get("estado", "")
    try:
        archivo.change_status(context.root(), id_, CVStatus(estado))
        flash(_("Estado actualizado."))
    except ValueError:
        flash(_("Estado no reconocido."))
    return redirect(url_for("ancla.view_cv", id_=id_))


@bp.route("/cvs/<id_>/adjuntar", methods=["POST"])
def attach_cv(id_: str):
    archivo_subido = request.files.get("adjunto")
    if archivo_subido is None or not archivo_subido.filename:
        flash(_("Elige un archivo antes de guardarlo."))
        return redirect(url_for("ancla.view_cv", id_=id_))

    destino_temporal = context.root() / "cvs" / "attachments" / f"_subida_{uuid.uuid4().hex}"
    destino_temporal.parent.mkdir(parents=True, exist_ok=True)
    archivo_subido.save(destino_temporal)
    archivo.attach(context.root(), id_, destino_temporal, archivo_subido.filename)
    destino_temporal.unlink(missing_ok=True)
    flash(_("Archivo guardado."))
    return redirect(url_for("ancla.view_cv", id_=id_))


@bp.route("/cvs/<id_>/adjunto/<nombre_archivo>")
def cv_attachment_file(id_: str, nombre_archivo: str):
    cv = _find_or_none(id_)
    if cv is None:
        abort(404)
    ruta = archivo.attachment_path(context.root(), cv, nombre_archivo)
    if ruta is None or not ruta.is_file():
        abort(404)
    return send_file(ruta)


@bp.route("/cvs/<id_>/adjunto/<nombre_archivo>/borrar", methods=["POST"])
def remove_cv_attachment(id_: str, nombre_archivo: str):
    archivo.remove_attachment(context.root(), id_, nombre_archivo)
    flash(_("Archivo borrado."))
    return redirect(url_for("ancla.view_cv", id_=id_))
