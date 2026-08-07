"""My CVs screen: the historical archive of saved proposals."""
from __future__ import annotations

from collections import Counter

from flask import flash, redirect, render_template, request, url_for
from flask_babel import gettext as _
from werkzeug.utils import secure_filename

from ancla.archive import repository as archivo
from ancla.profile.model import CVStatus
from ancla.proposal.format import to_markdown, to_text
from ancla.web import context
from ancla.web.blueprint import bp
from ancla.web.presentation import ETIQUETAS_ESTADO


@bp.route("/cvs")
def list_cvs():
    """The status summary doubles as a filter: each card carries the value
    to filter by (`filtro`), and "Total" (`filtro="todos"`) clears it. The
    filtering itself is client-side JS (`app.js`) over each card's
    `data-estado` — no need for a server round trip for something this
    simple, and every CV is still visible without JS."""
    cvs = archivo.list_all(context.root())
    conteo = Counter(cv.status for cv in cvs)
    resumen_estados = [{"etiqueta": "Total", "cantidad": len(cvs), "filtro": "todos"}] + [
        {"etiqueta": ETIQUETAS_ESTADO[estado], "cantidad": conteo[estado], "filtro": estado.value}
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
    )


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
        flash(_("Elige un archivo antes de adjuntarlo."))
        return redirect(url_for("ancla.view_cv", id_=id_))

    nombre_seguro = secure_filename(archivo_subido.filename)
    destino_temporal = context.root() / "cvs" / "attachments" / f"_subida_{id_}_{nombre_seguro}"
    destino_temporal.parent.mkdir(parents=True, exist_ok=True)
    archivo_subido.save(destino_temporal)
    archivo.attach(context.root(), id_, destino_temporal)
    destino_temporal.unlink(missing_ok=True)
    flash(_("Archivo adjuntado."))
    return redirect(url_for("ancla.view_cv", id_=id_))
