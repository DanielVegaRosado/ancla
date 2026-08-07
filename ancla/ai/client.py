"""Interface with the AI provider.

The app makes ONE model call per adaptation; everything else is
deterministic. Groq is the default provider because it has a free tier: the
user creates an account, pastes their key into Settings, and pays nothing.

The key always belongs to the user and lives only on their machine. This
repo has, and can have, no one's credentials.
"""
from __future__ import annotations

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
