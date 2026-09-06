"""Settings screen: AI provider and API key."""
from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for
from flask_babel import gettext as _

from ancla.web import settings as modulo_ajustes
from ancla.web import context
from ancla.web.blueprint import bp
from ancla.web.providers import PROVIDERS, display_name


@bp.route("/ajustes", methods=["GET", "POST"])
def view_settings():
    if request.method == "GET":
        return render_template(
            "settings.html",
            ajustes=context.current_settings(),
            proveedores=PROVIDERS,
            nombre_proveedor=display_name,
        )

    actuales = context.current_settings()
    proveedor = modulo_ajustes.valid_provider(request.form.get("proveedor"))
    if proveedor == "personalizado" and context.demo_mode():
        # Same restriction enforced in `web/providers.py` at the point the
        # AI call is made — this one just avoids the visitor saving a
        # setting that would fail later anyway.
        flash(
            _(
                "El proveedor personalizado no está disponible en esta demo pública "
                "(evita que el servidor compartido llame a direcciones arbitrarias). "
                "Prueba con Groq, OpenAI, Mistral, OpenRouter o Anthropic."
            )
        )
        proveedor = modulo_ajustes.PROVEEDOR_POR_DEFECTO
    # An empty Model field falls back to the provider's known-good default
    # (`Provider.default_model`) instead of being saved blank: it is what
    # lets pasting only the key leave the provider usable. `personalizado`
    # has no default to fall back to (there is no endpoint to guess a model
    # for), so it keeps demanding one typed by hand.
    modelo = request.form.get("modelo", "").strip() or PROVIDERS[proveedor].default_model
    # Only the key for the provider being saved changes; every other
    # provider's remembered key is carried over untouched, which is the
    # whole point of keeping one per provider instead of a single field.
    claves = dict(actuales.claves_api)
    claves[proveedor] = request.form.get("clave_api", "").strip()
    nuevos = modulo_ajustes.Settings(
        proveedor=proveedor,
        claves_api=claves,
        url_base=request.form.get("url_base", "").strip(),
        modelo=modelo,
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
    #
    # The wording leads with what to do rather than with what is wrong: the
    # person reading it is trying to get started, and the shape of the key
    # is not information they can act on by itself.
    if nuevos.proveedor == "groq" and nuevos.clave_api and not nuevos.clave_api.startswith("gsk_"):
        flash(
            _(
                "Esa clave no parece de Groq, así que seguramente no funcione. "
                "Consigue la tuya gratis en console.groq.com: entra, crea una clave "
                "nueva y pégala aquí. Ojo, que console.x.ai es otro servicio "
                "distinto (Grok) aunque el nombre se parezca mucho."
            )
        )
    # Same idea, this time for Anthropic: a key generated for a different
    # provider and pasted here by mistake fails the same way — flag it at
    # save time rather than after the first call.
    if (
        nuevos.proveedor == "anthropic"
        and nuevos.clave_api
        and not nuevos.clave_api.startswith("sk-ant-")
    ):
        flash(
            _(
                "Esa clave no parece de Anthropic, así que seguramente no funcione. "
                "Consigue la tuya en console.anthropic.com: entra, crea una clave "
                "nueva y pégala aquí. Las claves de Anthropic empiezan por sk-ant-."
            )
        )
    flash(_("Ajustes guardados."))
    return redirect(url_for("ancla.view_settings"))
