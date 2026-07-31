"""Pantalla Ajustes: proveedor de IA y clave de API."""
from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for
from flask_babel import gettext as _

from cv_adaptativo.ia.groq import URL_CONSEGUIR_CLAVE
from cv_adaptativo.web import ajustes as modulo_ajustes
from cv_adaptativo.web import contexto
from cv_adaptativo.web.blueprint import bp


@bp.route("/ajustes", methods=["GET", "POST"])
def ver_ajustes():
    if request.method == "GET":
        return render_template(
            "ajustes.html",
            ajustes=modulo_ajustes.cargar_ajustes(contexto.ruta_ajustes()),
            url_conseguir_clave=URL_CONSEGUIR_CLAVE,
        )

    actuales = modulo_ajustes.cargar_ajustes(contexto.ruta_ajustes())
    nuevos = modulo_ajustes.Ajustes(
        proveedor=request.form.get("proveedor", modulo_ajustes.PROVEEDOR_POR_DEFECTO),
        clave_api=request.form.get("clave_api", "").strip(),
        orden_perfil=actuales.orden_perfil,
        idioma=modulo_ajustes.idioma_valido(request.form.get("idioma")),
    )
    modulo_ajustes.guardar_ajustes(nuevos, contexto.ruta_ajustes())

    # Aviso, no bloqueo: no todas las claves de Groq tienen por qué llevar
    # siempre este prefijo (p. ej. si cambian su formato), así que se guarda
    # igual y se deja que sea la propia llamada la que confirme si es válida.
    # Pero el caso real que motivó esto —una clave de xAI (Grok, "xai-...")
    # pegada por error creyendo que era de Groq— se puede avisar en el
    # momento de guardar en vez de esperar al primer fallo.
    if nuevos.clave_api and not nuevos.clave_api.startswith("gsk_"):
        flash(
            _(
                "Esa clave no empieza por «gsk_», que es el formato de Groq. Si la "
                "conseguiste en console.x.ai en vez de console.groq.com, es de Grok "
                "(xAI) y no funcionará aquí: son proveedores distintos."
            )
        )
    flash(_("Ajustes guardados."))
    return redirect(url_for("cv_adaptativo.ver_ajustes"))
