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

from cv_adaptativo.web.blueprint import bp


@dataclass(frozen=True)
class Plantilla:
    nombre: str
    url: str


# TODO(Daniel): sustituir el nombre por el que describa mejor cada estilo
# antes de publicar — "Plantilla A/B" no le dice nada a quien no las ha visto.
PLANTILLAS = (
    Plantilla(
        nombre="Plantilla A",
        url="https://www.canva.com/design/DAHHeNVzaGM/mggPEzw06NPeboGC6D5wCQ/edit",
    ),
    Plantilla(
        nombre="Plantilla B",
        url="https://www.canva.com/design/DAHHeKwDZM4/RKBBp6YcMzbNCAdErRfSrQ/edit",
    ),
)


@bp.route("/plantillas")
def plantillas():
    return render_template("plantillas.html", plantillas=PLANTILLAS)
