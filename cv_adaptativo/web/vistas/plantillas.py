"""Pantalla Plantillas: enlace discreto en el pie, fuera de las cinco
pantallas principales — mismo patrón que Soporte.

Las plantillas son diseño (Canva), no datos del perfil: viven aquí como una
lista fija en vez de en `perfil/`, porque no son algo que el usuario edite
desde la app ni algo que varíe entre instalaciones. `plantillas/README.md`,
en la raíz del repositorio, documenta lo mismo para quien mire el proyecto
en GitHub sin llegar a ejecutarlo.
"""
from __future__ import annotations

from dataclasses import dataclass

from flask import render_template
from flask_babel import gettext as _

from cv_adaptativo.web.blueprint import bp


@dataclass(frozen=True)
class Plantilla:
    nombre: str
    url: str


URL_MINIMALISTA_CALIDA = "https://www.canva.com/design/DAHHeNVzaGM/mggPEzw06NPeboGC6D5wCQ/edit"
URL_CORPORATIVA_CLASICA = "https://www.canva.com/design/DAHHeKwDZM4/RKBBp6YcMzbNCAdErRfSrQ/edit"


@bp.route("/plantillas")
def plantillas():
    # Los nombres se traducen aquí, al construir la respuesta, no en una
    # constante de módulo: `_()` solo resuelve el idioma correcto dentro de
    # una petición, y necesita además un literal (no una variable) para que
    # pybabel lo extraiga al catálogo — de ahí que cada nombre esté escrito
    # a mano en su propia llamada, en vez de en un bucle.
    plantillas = (
        Plantilla(nombre=_("Minimalista Cálida"), url=URL_MINIMALISTA_CALIDA),
        Plantilla(nombre=_("Corporativa Clásica"), url=URL_CORPORATIVA_CLASICA),
    )
    return render_template("plantillas.html", plantillas=plantillas)
