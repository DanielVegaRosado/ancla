"""Dónde vive `perfil/`, `ajustes.json` y `cvs/` por defecto.

No hay base de datos: todo es ficheros en una carpeta real del disco, así
que esa carpeta tiene que sobrevivir entre arranques y ser la misma
carpeta que el usuario ve y puede mover o respaldar.

Ejecutando desde el código fuente (`python run.py`, tests, desarrollo), esa
carpeta es la raíz del repositorio. Empaquetada con PyInstaller en un único
ejecutable (`--onefile`), el runtime se autoextrae en una carpeta temporal
distinta en cada arranque (`sys._MEIPASS`) — escribir ahí perdería el
perfil del usuario de una sesión a otra. `sys.frozen` (que PyInstaller
define) distingue los dos casos; en el empaquetado, la carpeta estable es
la que contiene el propio ejecutable (`sys.executable`), no el código
extraído.
"""
from __future__ import annotations

import sys
from pathlib import Path


def raiz_datos() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]
