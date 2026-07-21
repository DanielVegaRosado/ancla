"""El único `Blueprint` de la app, en su propio módulo.

Cada pantalla registra sus rutas aquí (`cv_adaptativo/web/vistas/*.py`) en vez
de tener un blueprint por pantalla: los nombres de endpoint (`cv_adaptativo.
ver_perfil`, etc.) son los mismos de siempre, así que ninguna plantilla que
use `url_for` tiene que cambiar. Vive en su propio fichero para que las
vistas puedan importarlo sin depender unas de otras ni crear un ciclo con
`cv_adaptativo.web.vistas`.
"""
from __future__ import annotations

from flask import Blueprint

bp = Blueprint("cv_adaptativo", __name__)
