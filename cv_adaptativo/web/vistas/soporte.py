"""Pantalla Soporte: enlace discreto en el pie, fuera de las cinco pantallas
principales. Envuelve `cv_adaptativo/soporte/mensajes.py` (agente D)."""
from __future__ import annotations

from flask import flash, redirect, render_template, request

from cv_adaptativo.soporte import mensajes as modulo_soporte
from cv_adaptativo.web import ajustes as modulo_ajustes
from cv_adaptativo.web import contexto
from cv_adaptativo.web.blueprint import bp


@bp.route("/soporte", methods=["GET", "POST"])
def soporte():
    if request.method == "GET":
        return render_template("soporte.html")

    asunto = request.form.get("asunto", "").strip()
    mensaje = request.form.get("mensaje", "").strip()
    destino = request.form.get("destino", "github")
    if not asunto or not mensaje:
        flash("Rellena el asunto y el mensaje antes de enviarlo.")
        return render_template("soporte.html")

    ajustes = modulo_ajustes.cargar_ajustes(contexto.ruta_ajustes())
    diagnostico = modulo_soporte.recoger(proveedor=ajustes.proveedor)
    modulo_soporte.guardar_mensaje(contexto.raiz(), asunto, mensaje, diagnostico)

    if destino == "correo":
        return redirect(modulo_soporte.url_correo(asunto, mensaje, diagnostico))
    return redirect(modulo_soporte.url_incidencia(asunto, mensaje, diagnostico))
