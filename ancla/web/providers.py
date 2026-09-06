"""Registry of the AI providers offered in Settings, and the only place
that turns the chosen one into a `ClienteIA`.

A single point so the web layer does not depend on any specific provider:
`groq` and `anthropic` each have their own client (Groq and Claude do not
share an API format with anyone else here), and a family that shares the
generic OpenAI-compatible client — `openai`, `mistral`, and `openrouter`
with an already-known URL, plus `personalizado` for any other endpoint
that speaks that same format (Together, a local Ollama...) with whatever
URL the user types in.

Everything the app needs to know about a provider lives in its `Provider`
entry, including what the Settings screen shows about it: where the user
gets a key, whether there is a free tier, what a model name looks like
there. Kept together on purpose — a URL in a separate table is a URL that
gets forgotten when a provider is added.

Adding a provider is one entry in `PROVIDERS`, never editing
`create_client` — open for extension, closed for modification.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable

from flask_babel import gettext as _

from ancla.ai.anthropic import URL_CONSEGUIR_CLAVE as URL_CLAVE_ANTHROPIC
from ancla.ai.client import AIClient, AIError
from ancla.ai.groq import URL_CONSEGUIR_CLAVE as URL_CLAVE_GROQ


@dataclass(frozen=True)
class Provider:
    """One entry of the Settings dropdown, and how to build its client.

    `key_url` is empty for `personalizado` alone: there is no page to send
    the user to when the endpoint is one they chose themselves.

    `default_model` is a real default, not a hint: Settings pre-fills the
    Model field with it, so pasting the key is enough to get a working
    provider. It is empty for `personalizado` (no endpoint-specific model
    can be guessed) and for `groq` (`needs_model=False`, its client picks
    its own default internally). **Known cost**: the provider can retire
    the model named here — see `AnthropicClient._explain`'s `NotFoundError`
    branch and `OpenAICompatibleClient._explain`'s 404 branch, which name
    the misconfigured model and point back to Settings, same pattern as
    `groq.py`'s own 404 handling.

    `needs_model` is false only for `groq`: its client has its own default
    model, so Settings never shows a Model field for it at all.

    `key_hint` is the prefix its keys are known to start with — shown next
    to the key field as both a hint and the input's placeholder, and reused
    to flag a key pasted from the wrong provider in `views/settings.py`.
    Left empty for a provider with no fixed, confirmed prefix (`personalizado`
    included: any format is legitimate there), rather than print a hint that
    might not hold.
    """

    name: str
    create: Callable[[str, str, str], AIClient]
    key_url: str = ""
    default_model: str = ""
    free_tier: bool = False
    needs_model: bool = True
    key_hint: str = ""


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


PROVIDERS: dict[str, Provider] = {
    "groq": Provider(
        name="Groq",
        create=_groq_client,
        key_url=URL_CLAVE_GROQ,
        free_tier=True,
        needs_model=False,
        key_hint="gsk_",
    ),
    "openai": Provider(
        name="OpenAI",
        create=_openai_compatible_client("https://api.openai.com/v1"),
        key_url="https://platform.openai.com/api-keys",
        default_model="gpt-4o-mini",
    ),
    "anthropic": Provider(
        name="Anthropic",
        create=_anthropic_client,
        key_url=URL_CLAVE_ANTHROPIC,
        default_model="claude-haiku-4-5",
        key_hint="sk-ant-",
    ),
    "mistral": Provider(
        name="Mistral",
        create=_openai_compatible_client("https://api.mistral.ai/v1"),
        key_url="https://console.mistral.ai/api-keys",
        default_model="mistral-small-latest",
    ),
    "openrouter": Provider(
        name="OpenRouter",
        create=_openai_compatible_client("https://openrouter.ai/api/v1"),
        key_url="https://openrouter.ai/keys",
        default_model="openai/gpt-4o-mini",
    ),
    # Kept last on purpose: `settings.html` renders the dropdown in
    # registry order, and this is the one entry every other provider's user
    # never needs to see (see `display_name` below for its translated label).
    "personalizado": Provider(
        name="Otro (URL manual)",
        create=_custom_client,
    ),
}


def display_name(clave: str, proveedor: Provider) -> str:
    """Text for one entry of the Settings provider dropdown.

    Every other provider's name is a brand name and does not translate.
    `personalizado`'s is a UI label ("Other"), so it cannot live translated
    inside the frozen `PROVIDERS` dict (built once at import time, before
    any request/locale exists) — it is resolved here instead, at request
    time. The literal stays a direct `_(...)` call so `pybabel extract`
    still finds it despite the dict-driven dropdown.
    """
    if clave == "personalizado":
        return _("Otro (URL manual)")
    return proveedor.name


def create_client(proveedor: str, clave_api: str, url_base: str = "", modelo: str = "") -> AIClient:
    if proveedor == "personalizado":
        from flask import has_app_context

        from ancla.web import context

        # `has_app_context()` first: this function has no Flask context of
        # its own (existing callers like `test_crear_cliente_con_...` in
        # tests/test_web.py call it with no app pushed at all), and
        # `context.demo_mode()` reads `current_app.config`, which raises
        # `RuntimeError` outside one.
        if has_app_context() and context.demo_mode():
            # `url_base` is free text with no host/scheme check: outside the
            # demo it is the owner pointing at their own machine, but here
            # any anonymous visitor could aim the shared server at an
            # internal address (SSRF) and read the connect/auth error back
            # as a signal of what is reachable.
            raise AIError(
                _(
                    "El proveedor personalizado no está disponible en esta demo pública: "
                    "dejaría que el servidor compartido hiciera peticiones a cualquier "
                    "dirección escrita por un visitante. Prueba con Groq, OpenAI, "
                    "Mistral, OpenRouter o Anthropic."
                )
            )

    entrada = PROVIDERS.get(proveedor)
    if entrada is None:
        raise AIError(_("Proveedor de IA desconocido: «%(proveedor)s».", proveedor=proveedor))

    try:
        return entrada.create(clave_api, url_base, modelo)
    except ImportError as error:
        raise AIError(
            _(
                "El proveedor %(nombre)s todavía no está disponible en esta instalación.",
                nombre=entrada.name,
            )
        ) from error
