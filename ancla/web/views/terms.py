"""Terms and conditions screen: a discreet link in the footer, outside the
main screens. Summarises the project's hard privacy rules in plain
language (see CLAUDE.md), does not add any new ones."""
from __future__ import annotations

from flask import render_template

from ancla.support.messages import CORREO_SOPORTE, REPOSITORIO
from ancla.web.blueprint import bp


@bp.route("/terminos")
def terms():
    return render_template("terms.html", repository=REPOSITORIO, correo=CORREO_SOPORTE)
