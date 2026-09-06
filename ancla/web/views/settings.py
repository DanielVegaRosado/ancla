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

    _flash_si_la_clave_no_parece_valida(nuevos)
    flash(_("Ajustes guardados."))
    return redirect(url_for("ancla.view_settings"))


def _flash_si_la_clave_no_parece_valida(nuevos: modulo_ajustes.Settings) -> None:
    """Warn, without blocking, when the key just saved does not have its
    provider's known shape (`Provider.key_hint` + `Provider.min_key_length`).

    A shape check can never confirm a key works — only the provider's own
    API call can, on the first real request — so this always saves the key
    as typed and only ever says it "does not look like" a valid key, never
    that it is invalid. A provider with no confirmed shape (`key_hint`
    empty, e.g. "personalizado") is never flagged.

    The wording leads with what to do rather than with what is wrong: the
    person reading it is trying to get started, and the shape of the key is
    not information they can act on by itself.
    """
    proveedor = PROVIDERS.get(nuevos.proveedor)
    if proveedor is None or not nuevos.clave_api or proveedor.looks_like_valid_key(nuevos.clave_api):
        return

    if proveedor.free_tier:
        mensaje = _(
            "Esa clave no parece de %(nombre)s, así que seguramente no funcione. "
            "Consigue la tuya gratis en %(url)s: entra, crea una clave nueva y "
            "pégala aquí.",
            nombre=proveedor.name,
            url=proveedor.key_url,
        )
    else:
        mensaje = _(
            "Esa clave no parece de %(nombre)s, así que seguramente no funcione. "
            "Consigue la tuya en %(url)s: entra, crea una clave nueva y pégala aquí.",
            nombre=proveedor.name,
            url=proveedor.key_url,
        )
    mensaje += " " + str(
        _(
            "Las claves de %(nombre)s empiezan por %(prefijo)s.",
            nombre=proveedor.name,
            prefijo=proveedor.key_hint,
        )
    )
    flash(mensaje)
