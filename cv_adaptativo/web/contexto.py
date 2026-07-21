"""Acceso a la configuración de la petición actual (`current_app.config`).

Una sola responsabilidad: traducir claves de configuración de Flask a valores
tipados, para que cada vista no repita `current_app.config["RAIZ_PERFIL"]` ni
sepa cómo está guardado.
"""
from __future__ import annotations

from pathlib import Path

from flask import current_app

from cv_adaptativo.perfil import almacen
from cv_adaptativo.perfil.modelo import Perfil


def raiz() -> Path:
    return current_app.config["RAIZ_PERFIL"]


def ruta_ajustes() -> Path:
    return current_app.config["RUTA_AJUSTES"]


def perfil_actual() -> Perfil:
    return almacen.cargar_perfil(raiz())
