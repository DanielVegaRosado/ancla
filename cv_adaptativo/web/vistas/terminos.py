"""Pantalla Términos y condiciones: enlace discreto en el pie, fuera de las
pantallas principales. Resume en lenguaje llano las reglas duras de
privacidad del proyecto (ver CLAUDE.md), no añade ninguna nueva."""
from __future__ import annotations

from flask import render_template

from cv_adaptativo.soporte.mensajes import CORREO_SOPORTE, REPOSITORIO
from cv_adaptativo.web.blueprint import bp


@bp.route("/terminos")
def terminos():
    return render_template("terminos.html", repositorio=REPOSITORIO, correo=CORREO_SOPORTE)
