"""Instantiates the `ClienteIA` for the provider chosen in Settings.

A single point so the web layer does not depend on any specific provider:
`groq` and `anthropic` each have their own client (Groq and Claude do not
share an API format with anyone else here), and a family that shares the
generic OpenAI-compatible client — `openai`, `mistral`, and `openrouter`
with a already-known URL (`URLS_CONOCIDAS`), plus `personalizado` for any
other endpoint that speaks that same format (Together, a local Ollama...)
with whatever URL the user types in.

Adding a provider with a new known URL is one line in `URLS_CONOCIDAS` plus
one entry in `_FABRICAS`, never editing `crear_cliente` — open for
extension, closed for modification.
"""
from __future__ import annotations

import os
from typing import Callable

from flask_babel import gettext as _

from ancla.ai.client import AIClient, AIError

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


def _groq_client(clave_api: str, url_base: str, modelo: str) -> AIClient:
    from ancla.ai.groq import GroqClient

    # The app's Settings take priority; GROQ_API_KEY is just a shortcut for
    # a developer who does not want to paste the key into the interface.
    return GroqClient(clave_api or os.environ.get("GROQ_API_KEY", ""))


def _anthropic_client(clave_api: str, url_base: str, modelo: str) -> AIClient:
    from ancla.ai.anthropic import AnthropicClient

    return AnthropicClient(clave_api, modelo)


def _openai_compatible_client(url_fija: str):
    """A factory of factories: binds a known URL without the user ever
    seeing it or being able to desync it by typing it in by hand."""

    def factory(clave_api: str, url_base: str, modelo: str) -> AIClient:
        from ancla.ai.openai_compatible import OpenAICompatibleClient

        return OpenAICompatibleClient(clave_api, url_fija, modelo)

    return factory


def _custom_client(clave_api: str, url_base: str, modelo: str) -> AIClient:
    from ancla.ai.openai_compatible import OpenAICompatibleClient

    return OpenAICompatibleClient(clave_api, url_base, modelo)


_FABRICAS: dict[str, Callable[[str, str, str], AIClient]] = {
    "groq": _groq_client,
    "openai": _openai_compatible_client(URLS_CONOCIDAS["openai"]),
    "anthropic": _anthropic_client,
    "mistral": _openai_compatible_client(URLS_CONOCIDAS["mistral"]),
    "openrouter": _openai_compatible_client(URLS_CONOCIDAS["openrouter"]),
    "personalizado": _custom_client,
}


def create_client(proveedor: str, clave_api: str, url_base: str = "", modelo: str = "") -> AIClient:
    factory = _FABRICAS.get(proveedor)
    if factory is None:
        raise AIError(_("Proveedor de IA desconocido: «%(proveedor)s».", proveedor=proveedor))

    try:
        return factory(clave_api, url_base, modelo)
    except ImportError as error:
        nombre = NOMBRES.get(proveedor, proveedor)
        raise AIError(
            _(
                "El proveedor %(nombre)s todavía no está disponible en esta instalación.",
                nombre=nombre,
            )
        ) from error
