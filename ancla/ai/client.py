"""Interface with the AI provider.

The app makes ONE model call per adaptation; everything else is
deterministic. Groq is the default provider because it has a free tier: the
user creates an account, pastes their key into Settings, and pays nothing.

The key always belongs to the user and lives only on their machine. This
repo has, and can have, no one's credentials.
"""
from __future__ import annotations

import inspect
from typing import Protocol


class AIError(Exception):
    """Failure talking to the provider (invalid key, network, usage limit)."""


class AIClient(Protocol):
    """The minimum the selection engine needs from a provider.

    Defined as a Protocol so the engine does not depend on Groq, and so a
    fake client can be injected in tests without touching the network.
    """

    def complete(self, sistema: str, usuario: str) -> str:
        """Returns the model's response as text.

        Raises `ErrorIA` on any failure, with a message that can be shown
        to the user as-is (the usual cause will be the key).
        """
        ...

    def available(self) -> bool:
        """True if a key is configured. Does not check that it is valid."""
        ...


def complete_with_budget(cliente: AIClient, sistema: str, usuario: str, max_tokens: int) -> str:
    """Calls `cliente.complete`, telling it how much room the caller expects
    the response to need.

    Deliberately not part of `AIClient` itself. Only Groq's free tier
    decides whether to *admit* a request by comparing a declared ceiling
    against what is left of its per-minute allowance (see `ai/groq.py`), so
    only `GroqClient` has a use for this number — Anthropic and the generic
    OpenAI-compatible client apply their own flat ceiling regardless of what
    is asked of them. Each use case (`profile/importer.py`,
    `profile/gaps.py`, `selection/engine.py`) knows the shape of its own
    request — whether the response scales with the text it sends, or is a
    small, fixed structure regardless of it — so the number is computed
    there and handed down, instead of guessed here or hidden inside one
    provider's client.

    Detected through the client's own signature, not a type check or a
    provider name: that way a use case never has to know which provider it
    is talking to, and adding a fourth provider that also wants the hint
    needs nothing changed here.
    """
    if "max_tokens" in inspect.signature(cliente.complete).parameters:
        return cliente.complete(sistema, usuario, max_tokens=max_tokens)
    return cliente.complete(sistema, usuario)
