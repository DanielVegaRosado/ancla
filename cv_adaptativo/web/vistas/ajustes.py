"""Pantalla Ajustes: proveedor de IA y clave de API."""
from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for

from cv_adaptativo.web import ajustes as modulo_ajustes
from cv_adaptativo.web import contexto
from cv_adaptativo.web.blueprint import bp


@bp.route("/ajustes", methods=["GET", "POST"])
def ver_ajustes():
    if request.method == "GET":
        return render_template("ajustes.html", ajustes=modulo_ajustes.cargar_ajustes(contexto.ruta_ajustes()))

    nuevos = modulo_ajustes.Ajustes(
        proveedor=request.form.get("proveedor", modulo_ajustes.PROVEEDOR_POR_DEFECTO),
        clave_api=request.form.get("clave_api", "").strip(),
    )
    modulo_ajustes.guardar_ajustes(nuevos, contexto.ruta_ajustes())
    flash("Ajustes guardados.")
    return redirect(url_for("cv_adaptativo.ver_ajustes"))
