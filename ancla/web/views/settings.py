"""Settings screen: AI provider and API key."""
from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for
from flask_babel import gettext as _

from ancla.ai.groq import URL_CONSEGUIR_CLAVE
from ancla.web import settings as modulo_ajustes
from ancla.web import context
from ancla.web.blueprint import bp


@bp.route("/ajustes", methods=["GET", "POST"])
def view_settings():
    if request.method == "GET":
        return render_template(
            "settings.html",
            ajustes=context.current_settings(),
            url_conseguir_clave=URL_CONSEGUIR_CLAVE,
        )

    actuales = context.current_settings()
    nuevos = modulo_ajustes.Settings(
        proveedor=modulo_ajustes.valid_provider(request.form.get("proveedor")),
        clave_api=request.form.get("clave_api", "").strip(),
        url_base=request.form.get("url_base", "").strip(),
        modelo=request.form.get("modelo", "").strip(),
        orden_perfil=actuales.orden_perfil,
        idioma=modulo_ajustes.valid_language(request.form.get("idioma")),
    )
    context.save_current_settings(nuevos)

    # A warning, not a block, and only for Groq: not every key has to carry
    # this prefix (e.g. if Groq changes its format), so it is saved as-is
    # and the actual call is left to confirm whether it is valid. But the
    # real case that prompted this — an xAI (Grok, "xai-...") key pasted in
    # by mistake thinking it was Groq's — can be flagged the moment it is
    # saved instead of waiting for the first failure. With "Other
    # (OpenAI-compatible)" any key format is legitimate, so the warning
    # does not apply.
    if nuevos.proveedor == "groq" and nuevos.clave_api and not nuevos.clave_api.startswith("gsk_"):
        flash(
            _(
                "Esa clave no empieza por «gsk_», que es el formato de Groq. Si la "
                "conseguiste en console.x.ai en vez de console.groq.com, es de Grok "
                "(xAI) y no funcionará aquí: son proveedores distintos."
            )
        )
    flash(_("Ajustes guardados."))
    return redirect(url_for("ancla.view_settings"))
