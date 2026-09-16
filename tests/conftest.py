"""Fixtures shared by the whole test suite."""
from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from flask_wtf import CSRFProtect

from ancla.web.settings import VARIABLE_ENTORNO_CLAVE_CIFRADO


@pytest.fixture(autouse=True)
def _csrf_disabled_for_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    """The suite posts forms straight through Flask's test client — there is
    no browser to have fetched a page and carried its hidden `csrf_token`
    field first, so every existing POST test would otherwise need to learn
    about tokens. Same trusted-client reasoning as any test suite disabling
    CSRF: the check itself, and that it actually blocks an unsigned request,
    is exercised without this bypass in `test_csrf.py`, which overrides this
    fixture to a no-op for that one file."""
    original_init_app = CSRFProtect.init_app

    def _init_app_without_csrf(self, app):
        original_init_app(self, app)
        app.config["WTF_CSRF_ENABLED"] = False

    monkeypatch.setattr(CSRFProtect, "init_app", _init_app_without_csrf)


@pytest.fixture(autouse=True)
def _clave_de_cifrado_de_ajustes(monkeypatch: pytest.MonkeyPatch) -> None:
    """`Settings.save_settings`/`load_settings` need `ANCLA_CLAVE_CIFRADO` set
    to encrypt/decrypt API keys — same as any real deployment would. Autouse
    so the many existing tests that save a key through the web layer do not
    each need to know about encryption. Tests that specifically exercise the
    missing- or wrong-variable behaviour (`test_settings.py`) unset or
    replace it themselves within the test body."""
    monkeypatch.setenv(VARIABLE_ENTORNO_CLAVE_CIFRADO, Fernet.generate_key().decode())
