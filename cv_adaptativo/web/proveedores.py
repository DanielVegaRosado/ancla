"""Instancia el `ClienteIA` del proveedor elegido en Ajustes.

Un único punto para que la web no dependa de un proveedor concreto: hoy solo
Groq, pero la lista crece en v1.1 sin tocar el resto de la app.
"""
from __future__ import annotations

import os

from cv_adaptativo.ia.cliente import ClienteIA, ErrorIA

NOMBRES = {"groq": "Groq"}


def crear_cliente(proveedor: str, clave_api: str) -> ClienteIA:
    if proveedor == "groq":
        try:
            from cv_adaptativo.ia.groq import ClienteGroq
        except ImportError as error:
            raise ErrorIA(
                "El proveedor Groq todavía no está disponible en esta instalación."
            ) from error
        # Los Ajustes de la app mandan; GROQ_API_KEY es solo un atajo para
        # quien desarrolla y no quiere pegar la clave en la interfaz.
        return ClienteGroq(clave_api or os.environ.get("GROQ_API_KEY", ""))

    raise ErrorIA(f"Proveedor de IA desconocido: «{proveedor}».")
