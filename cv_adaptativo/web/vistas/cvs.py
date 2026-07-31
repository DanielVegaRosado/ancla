"""Pantalla Mis CVs: el archivo histórico de propuestas guardadas."""
from __future__ import annotations

from collections import Counter

from flask import flash, redirect, render_template, request, url_for
from flask_babel import gettext as _
from werkzeug.utils import secure_filename

from cv_adaptativo.archivo import repositorio as archivo
from cv_adaptativo.perfil.modelo import EstadoCV
from cv_adaptativo.propuesta.formato import a_markdown, a_texto
from cv_adaptativo.web import contexto
from cv_adaptativo.web.blueprint import bp
from cv_adaptativo.web.presentacion import ETIQUETAS_ESTADO


@bp.route("/cvs")
def listar_cvs():
    """El resumen por estado sirve de filtro: cada tarjeta lleva el valor por
    el que filtrar (`filtro`), y "Total" (`filtro="todos"`) lo quita. El
    filtrado en sí es JS del lado del cliente (`app.js`) sobre `data-estado`
    en cada tarjeta — no hace falta ida y vuelta al servidor para algo tan
    simple, y sin JS se ven todos los CVs igualmente."""
    cvs = archivo.listar(contexto.raiz())
    conteo = Counter(cv.estado for cv in cvs)
    resumen_estados = [{"etiqueta": "Total", "cantidad": len(cvs), "filtro": "todos"}] + [
        {"etiqueta": ETIQUETAS_ESTADO[estado], "cantidad": conteo[estado], "filtro": estado.value}
        for estado in EstadoCV
    ]
    return render_template("cvs.html", cvs=cvs, resumen_estados=resumen_estados)


def _buscar_o_ninguno(id_: str):
    return next((c for c in archivo.listar(contexto.raiz()) if c.id == id_), None)


@bp.route("/cvs/<id_>")
def ver_cv(id_: str):
    cv = _buscar_o_ninguno(id_)
    if cv is None:
        flash(_("No se encuentra el CV «%(id)s» en el archivo.", id=id_))
        return redirect(url_for("cv_adaptativo.listar_cvs"))

    perfil = contexto.perfil_actual()
    return render_template(
        "cv_detalle.html",
        cv=cv,
        perfil=perfil,
        texto_plano=a_texto(cv.propuesta, perfil),
        texto_markdown=a_markdown(cv.propuesta, perfil),
        estados=list(EstadoCV),
    )


@bp.route("/cvs/<id_>/estado", methods=["POST"])
def cambiar_estado_cv(id_: str):
    estado = request.form.get("estado", "")
    try:
        archivo.cambiar_estado(contexto.raiz(), id_, EstadoCV(estado))
        flash(_("Estado actualizado."))
    except ValueError:
        flash(_("Estado no reconocido."))
    return redirect(url_for("cv_adaptativo.ver_cv", id_=id_))


@bp.route("/cvs/<id_>/adjuntar", methods=["POST"])
def adjuntar_cv(id_: str):
    archivo_subido = request.files.get("adjunto")
    if archivo_subido is None or not archivo_subido.filename:
        flash(_("Elige un archivo antes de adjuntarlo."))
        return redirect(url_for("cv_adaptativo.ver_cv", id_=id_))

    nombre_seguro = secure_filename(archivo_subido.filename)
    destino_temporal = contexto.raiz() / "cvs" / "adjuntos" / f"_subida_{id_}_{nombre_seguro}"
    destino_temporal.parent.mkdir(parents=True, exist_ok=True)
    archivo_subido.save(destino_temporal)
    archivo.adjuntar(contexto.raiz(), id_, destino_temporal)
    destino_temporal.unlink(missing_ok=True)
    flash(_("Archivo adjuntado."))
    return redirect(url_for("cv_adaptativo.ver_cv", id_=id_))
