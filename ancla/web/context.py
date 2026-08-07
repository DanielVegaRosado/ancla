"""Access to the current request's configuration (`current_app.config`).

A single responsibility: translating Flask config keys into typed values,
so no view has to repeat `current_app.config["RAIZ_PERFIL"]` or know how it
is stored.
"""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from flask import current_app, session

from ancla.profile import store
from ancla.profile.model import Profile
from ancla.web import settings as modulo_ajustes

_CLAVE_SESION_AJUSTES = "ajustes_demo"


def root() -> Path:
    return current_app.config["RAIZ_PERFIL"]


def settings_path() -> Path:
    return current_app.config["RUTA_AJUSTES"]


def demo_mode() -> bool:
    return current_app.config["MODO_DEMO"]


def current_profile() -> Profile:
    return store.load_profile(root())


def current_settings() -> modulo_ajustes.Settings:
    """In demo mode, every visitor shares the same profile and the same
    process, so an `ajustes.json` on disk would leak one visitor's API key
    to the next. It is stored in their browser session instead; outside
    demo mode, the usual file on disk."""
    if demo_mode():
        datos = session.get(_CLAVE_SESION_AJUSTES)
        return modulo_ajustes.Settings(**datos) if datos else modulo_ajustes.Settings()
    return modulo_ajustes.load_settings(settings_path())


def save_current_settings(ajustes: modulo_ajustes.Settings) -> None:
    if demo_mode():
        session[_CLAVE_SESION_AJUSTES] = asdict(ajustes)
        return
    modulo_ajustes.save_settings(ajustes, settings_path())


def current_language() -> str:
    return current_settings().idioma
