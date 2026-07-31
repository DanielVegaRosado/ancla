"""Pantalla Soporte: enlace discreto en el pie, fuera de las cinco pantallas
principales. Envuelve `cv_adaptativo/soporte/mensajes.py` (agente D)."""
from __future__ import annotations

from flask import flash, redirect, render_template, request
from flask_babel import gettext as _

from cv_adaptativo.soporte import mensajes as modulo_soporte
from cv_adaptativo.web import ajustes as modulo_ajustes
from cv_adaptativo.web import contexto
from cv_adaptativo.web.blueprint import bp


def _tipos_traducidos() -> dict[str, str]:
    # Literales explícitos, no `_(variable)`: pybabel solo extrae strings
    # pasados directamente a `_()`, así que iterar `TIPOS.items()` y traducir
    # cada valor de forma dinámica no deja ningún rastro en el catálogo — el
    # texto se queda sin traducir en silencio. Las claves vienen de
    # `modulo_soporte.TIPOS`, la única fuente de verdad para qué tipos existen.
    return {
        "problema": _("Problema"),
        "sugerencia": _("Sugerencia"),
    }


@bp.route("/soporte", methods=["GET", "POST"])
def soporte():
    if request.method == "GET":
        return render_template("soporte.html", tipos=_tipos_traducidos())

    asunto = request.form.get("asunto", "").strip()
    mensaje = request.form.get("mensaje", "").strip()
    tipo = request.form.get("tipo", modulo_soporte.TIPO_POR_DEFECTO)
    destino = request.form.get("destino", "github")
    if not mensaje:
        flash(_("Cuéntanos qué ha pasado, o qué se te ha ocurrido, antes de enviarlo."))
        return render_template("soporte.html", tipos=_tipos_traducidos())

    ajustes = modulo_ajustes.cargar_ajustes(contexto.ruta_ajustes())
    diagnostico = modulo_soporte.recoger(proveedor=ajustes.proveedor)
    modulo_soporte.guardar_mensaje(contexto.raiz(), asunto, mensaje, diagnostico, tipo)

    if destino == "correo":
        return redirect(modulo_soporte.url_correo(asunto, mensaje, diagnostico, tipo))
    return redirect(modulo_soporte.url_incidencia(asunto, mensaje, diagnostico, tipo))
