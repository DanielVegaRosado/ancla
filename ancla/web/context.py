"""Access to the current request's configuration (`current_app.config`).

A single responsibility: translating Flask config keys into typed values,
so no view has to repeat `current_app.config["RAIZ_PERFIL"]` or know how it
is stored.
"""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from flask import current_app, has_request_context, session
from flask_login import current_user

from ancla.profile import store
from ancla.profile.model import Profile
from ancla.web import settings as modulo_ajustes
from ancla.web.routes import SETTINGS_FILE_NAME

_CLAVE_SESION_AJUSTES = "ajustes_demo"


def _user_dir() -> Path | None:
    """The logged-in user's own folder under `perfiles/`, or None when no one
    is logged in. Every view reaches the profile, the archived CVs (`cvs/`,
    inside the profile folder) and the settings through `root()` and
    `settings_path()`, so resolving the user here is what isolates one
    account's data from another's without any view knowing about accounts.

    Without a session (the desktop build, or a visitor who never logged in)
    this returns None and the single shared folder keeps being used, exactly
    as before accounts existed. Demo mode is left out on purpose: its
    visitors share the example profile by design, logged in or not."""
    if demo_mode() or not has_request_context() or not current_user.is_authenticated:
        return None
    return current_app.config["RAIZ_PERFILES"] / str(current_user.get_id())


def root() -> Path:
    carpeta_usuario = _user_dir()
    return carpeta_usuario if carpeta_usuario else current_app.config["RAIZ_PERFIL"]


def settings_path() -> Path:
    carpeta_usuario = _user_dir()
    return carpeta_usuario / SETTINGS_FILE_NAME if carpeta_usuario else current_app.config["RUTA_AJUSTES"]


def canva_templates_root() -> Path:
    return current_app.config["RAIZ_PLANTILLAS_CANVA"]


def html_templates_root() -> Path:
    return current_app.config["RAIZ_PLANTILLAS_HTML"]


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
