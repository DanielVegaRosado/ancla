"""Instancia el `ClienteIA` del proveedor elegido en Ajustes.

Un único punto para que la web no dependa de un proveedor concreto: `groq` y
`anthropic` tienen cada uno su propio cliente (Groq y Claude no comparten
formato de API con nadie más aquí), y una familia que comparte el cliente
genérico compatible con OpenAI — `openai`, `mistral` y `openrouter` con la
URL ya conocida (`URLS_CONOCIDAS`), más `personalizado` para cualquier otro
endpoint que hable ese mismo formato (Together, un Ollama local...) con la
URL que escriba el usuario.

Añadir un proveedor con URL conocida nueva es una línea en `URLS_CONOCIDAS` +
una entrada en `_FABRICAS`, no editar `crear_cliente` — abierto a extensión,
cerrado a modificación.
"""
from __future__ import annotations

import os
from typing import Callable

from flask_babel import gettext as _

from cv_adaptativo.ia.cliente import ClienteIA, ErrorIA

NOMBRES = {
    "groq": "Groq",
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "mistral": "Mistral",
    "openrouter": "OpenRouter",
    "personalizado": "Otro (URL manual)",
}

URLS_CONOCIDAS = {
    "openai": "https://api.openai.com/v1",
    "mistral": "https://api.mistral.ai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
}


def _cliente_groq(clave_api: str, url_base: str, modelo: str) -> ClienteIA:
    from cv_adaptativo.ia.groq import ClienteGroq

    # Los Ajustes de la app mandan; GROQ_API_KEY es solo un atajo para quien
    # desarrolla y no quiere pegar la clave en la interfaz.
    return ClienteGroq(clave_api or os.environ.get("GROQ_API_KEY", ""))


def _cliente_anthropic(clave_api: str, url_base: str, modelo: str) -> ClienteIA:
    from cv_adaptativo.ia.anthropic import ClienteAnthropic

    return ClienteAnthropic(clave_api, modelo)


def _cliente_compatible_openai(url_fija: str):
    """Fábrica de fábricas: liga una URL conocida sin que el usuario la vea
    ni pueda desincronizarla escribiéndola a mano."""

    def fabrica(clave_api: str, url_base: str, modelo: str) -> ClienteIA:
        from cv_adaptativo.ia.openai_compatible import ClienteCompatibleOpenAI

        return ClienteCompatibleOpenAI(clave_api, url_fija, modelo)

    return fabrica


def _cliente_personalizado(clave_api: str, url_base: str, modelo: str) -> ClienteIA:
    from cv_adaptativo.ia.openai_compatible import ClienteCompatibleOpenAI

    return ClienteCompatibleOpenAI(clave_api, url_base, modelo)


_FABRICAS: dict[str, Callable[[str, str, str], ClienteIA]] = {
    "groq": _cliente_groq,
    "openai": _cliente_compatible_openai(URLS_CONOCIDAS["openai"]),
    "anthropic": _cliente_anthropic,
    "mistral": _cliente_compatible_openai(URLS_CONOCIDAS["mistral"]),
    "openrouter": _cliente_compatible_openai(URLS_CONOCIDAS["openrouter"]),
    "personalizado": _cliente_personalizado,
}


def crear_cliente(proveedor: str, clave_api: str, url_base: str = "", modelo: str = "") -> ClienteIA:
    fabrica = _FABRICAS.get(proveedor)
    if fabrica is None:
        raise ErrorIA(_("Proveedor de IA desconocido: «%(proveedor)s».", proveedor=proveedor))

    try:
        return fabrica(clave_api, url_base, modelo)
    except ImportError as error:
        nombre = NOMBRES.get(proveedor, proveedor)
        raise ErrorIA(
            _(
                "El proveedor %(nombre)s todavía no está disponible en esta instalación.",
                nombre=nombre,
            )
        ) from error
