"""Instancia el `ClienteIA` del proveedor elegido en Ajustes.

Un único punto para que la web no dependa de un proveedor concreto: hoy solo
Groq, pero la lista crece en v1.1 sin tocar el resto de la app.
"""
from __future__ import annotations

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
        return ClienteGroq(clave_api)

    raise ErrorIA(f"Proveedor de IA desconocido: «{proveedor}».")
