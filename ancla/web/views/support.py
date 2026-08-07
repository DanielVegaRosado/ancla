"""Support screen: a discreet link in the footer, outside the five main
screens. Wraps `ancla/soporte/mensajes.py` (agent D)."""
from __future__ import annotations

from flask import flash, redirect, render_template, request
from flask_babel import gettext as _

from ancla.support import messages as modulo_soporte
from ancla.web import context
from ancla.web.blueprint import bp


def _translated_types() -> dict[str, str]:
    # Explicit literals, not `_(variable)`: pybabel only extracts strings
    # passed directly to `_()`, so iterating `TIPOS.items()` and translating
    # each value dynamically leaves no trace in the catalog — the text
    # silently stays untranslated. The keys come from `modulo_soporte.TIPOS`,
    # the single source of truth for which types exist.
    return {
        "problema": _("Problema"),
        "sugerencia": _("Sugerencia"),
    }


@bp.route("/soporte", methods=["GET", "POST"])
def support():
    if request.method == "GET":
        return render_template("support.html", tipos=_translated_types())

    asunto = request.form.get("asunto", "").strip()
    mensaje = request.form.get("mensaje", "").strip()
    tipo = request.form.get("tipo", modulo_soporte.TIPO_POR_DEFECTO)
    destino = request.form.get("destino", "github")
    if not mensaje:
        flash(_("Cuéntanos qué ha pasado, o qué se te ha ocurrido, antes de enviarlo."))
        return render_template("support.html", tipos=_translated_types())

    ajustes = context.current_settings()
    diagnostico = modulo_soporte.collect(proveedor=ajustes.proveedor)
    modulo_soporte.save_message(context.root(), asunto, mensaje, diagnostico, tipo)

    if destino == "correo":
        return redirect(modulo_soporte.email_url(asunto, mensaje, diagnostico, tipo))
    return redirect(modulo_soporte.issue_url(asunto, mensaje, diagnostico, tipo))
