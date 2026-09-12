"""Fixtures shared by the whole test suite."""
from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from ancla.web.settings import VARIABLE_ENTORNO_CLAVE_CIFRADO


@pytest.fixture(autouse=True)
def _clave_de_cifrado_de_ajustes(monkeypatch: pytest.MonkeyPatch) -> None:
    """`Settings.save_settings`/`load_settings` need `ANCLA_CLAVE_CIFRADO` set
    to encrypt/decrypt API keys — same as any real deployment would. Autouse
    so the many existing tests that save a key through the web layer do not
    each need to know about encryption. Tests that specifically exercise the
    missing- or wrong-variable behaviour (`test_settings.py`) unset or
    replace it themselves within the test body."""
    monkeypatch.setenv(VARIABLE_ENTORNO_CLAVE_CIFRADO, Fernet.generate_key().decode())
