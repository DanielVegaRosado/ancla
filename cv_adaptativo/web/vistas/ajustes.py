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
            ajustes=contexto.ajustes_actuales(),
            url_conseguir_clave=URL_CONSEGUIR_CLAVE,
        )

    actuales = contexto.ajustes_actuales()
    nuevos = modulo_ajustes.Ajustes(
        proveedor=modulo_ajustes.proveedor_valido(request.form.get("proveedor")),
        clave_api=request.form.get("clave_api", "").strip(),
        url_base=request.form.get("url_base", "").strip(),
        modelo=request.form.get("modelo", "").strip(),
        orden_perfil=actuales.orden_perfil,
        idioma=modulo_ajustes.idioma_valido(request.form.get("idioma")),
    )
    contexto.guardar_ajustes_actuales(nuevos)

    # Aviso, no bloqueo, y solo para Groq: no todas las claves tienen por qué
    # llevar siempre este prefijo (p. ej. si Groq cambia su formato), así que
    # se guarda igual y se deja que sea la propia llamada la que confirme si
    # es válida. Pero el caso real que motivó esto —una clave de xAI (Grok,
    # "xai-...") pegada por error creyendo que era de Groq— se puede avisar
    # en el momento de guardar en vez de esperar al primer fallo. Con "Otro
    # (compatible OpenAI)" cualquier formato de clave es legítimo, así que el
    # aviso no aplica.
    if nuevos.proveedor == "groq" and nuevos.clave_api and not nuevos.clave_api.startswith("gsk_"):
        flash(
            _(
                "Esa clave no empieza por «gsk_», que es el formato de Groq. Si la "
                "conseguiste en console.x.ai en vez de console.groq.com, es de Grok "
                "(xAI) y no funcionará aquí: son proveedores distintos."
            )
        )
    flash(_("Ajustes guardados."))
    return redirect(url_for("cv_adaptativo.ver_ajustes"))
