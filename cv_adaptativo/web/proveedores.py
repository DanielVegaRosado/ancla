"""Instancia el `ClienteIA` del proveedor elegido en Ajustes.

Un único punto para que la web no dependa de un proveedor concreto: hoy solo
Groq, pero la lista crece en v1.1 sin tocar el resto de la app. Añadir un
proveedor nuevo es registrar una entrada en `_FABRICAS`, no editar
`crear_cliente` — abierto a extensión, cerrado a modificación.
"""
from __future__ import annotations

import os
from typing import Callable

from flask_babel import gettext as _

from cv_adaptativo.ia.cliente import ClienteIA, ErrorIA

NOMBRES = {"groq": "Groq"}


def _cliente_groq(clave_api: str) -> ClienteIA:
    from cv_adaptativo.ia.groq import ClienteGroq

    # Los Ajustes de la app mandan; GROQ_API_KEY es solo un atajo para quien
    # desarrolla y no quiere pegar la clave en la interfaz.
    return ClienteGroq(clave_api or os.environ.get("GROQ_API_KEY", ""))


_FABRICAS: dict[str, Callable[[str], ClienteIA]] = {"groq": _cliente_groq}


def crear_cliente(proveedor: str, clave_api: str) -> ClienteIA:
    fabrica = _FABRICAS.get(proveedor)
    if fabrica is None:
        raise ErrorIA(_("Proveedor de IA desconocido: «%(proveedor)s».", proveedor=proveedor))

    try:
        return fabrica(clave_api)
    except ImportError as error:
        nombre = NOMBRES.get(proveedor, proveedor)
        raise ErrorIA(
            _(
                "El proveedor %(nombre)s todavía no está disponible en esta instalación.",
                nombre=nombre,
            )
        ) from error
