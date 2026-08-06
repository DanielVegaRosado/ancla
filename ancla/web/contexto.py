"""Acceso a la configuración de la petición actual (`current_app.config`).

Una sola responsabilidad: traducir claves de configuración de Flask a valores
tipados, para que cada vista no repita `current_app.config["RAIZ_PERFIL"]` ni
sepa cómo está guardado.
"""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from flask import current_app, session

from ancla.perfil import almacen
from ancla.perfil.modelo import Perfil
from ancla.web import ajustes as modulo_ajustes

_CLAVE_SESION_AJUSTES = "ajustes_demo"


def raiz() -> Path:
    return current_app.config["RAIZ_PERFIL"]


def ruta_ajustes() -> Path:
    return current_app.config["RUTA_AJUSTES"]


def modo_demo() -> bool:
    return current_app.config["MODO_DEMO"]


def perfil_actual() -> Perfil:
    return almacen.cargar_perfil(raiz())


def ajustes_actuales() -> modulo_ajustes.Ajustes:
    """En modo demo, cada visitante comparte el mismo perfil y el mismo
    proceso, así que un `ajustes.json` en disco filtraría la clave de API de
    un visitante al siguiente. Se guarda en su sesión de navegador en su
    lugar; fuera de modo demo, el fichero en disco de siempre."""
    if modo_demo():
        datos = session.get(_CLAVE_SESION_AJUSTES)
        return modulo_ajustes.Ajustes(**datos) if datos else modulo_ajustes.Ajustes()
    return modulo_ajustes.cargar_ajustes(ruta_ajustes())


def guardar_ajustes_actuales(ajustes: modulo_ajustes.Ajustes) -> None:
    if modo_demo():
        session[_CLAVE_SESION_AJUSTES] = asdict(ajustes)
        return
    modulo_ajustes.guardar_ajustes(ajustes, ruta_ajustes())


def idioma_actual() -> str:
    return ajustes_actuales().idioma
