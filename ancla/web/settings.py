"""App settings: AI provider and API key.

Distinct from `perfil/`: these are not user facts, they are local
installation configuration. They live in `ajustes.json`, next to `perfil/` in
`data_root()`, and are **never** pushed to the repository (see `.gitignore`). The
key always belongs to the user.

The API keys (`claves_api`, and the `clave_api` derived from it — see
`Settings.__post_init__`) are encrypted at rest with Fernet before they
reach disk, and decrypted on load. This is the first step of a longer
migration: today `ajustes.json` is still a single file shared by one owner
on their own machine, harmless in plain text — but Ancla is headed towards a
hosted product with many users, where a plain-text file on a shared server
is a single point of failure that leaks everyone's key at once. Where the
file lives, and the "one install, one owner" model, are unchanged here —
that is a later, separate migration.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from ancla.web.providers import PROVIDERS
from ancla.web.routes import SETTINGS_FILE_NAME, data_root

RUTA_POR_DEFECTO = data_root() / SETTINGS_FILE_NAME

# The Fernet key that encrypts the API keys, distinct from the API keys
# themselves. Never in the repo or in `ajustes.json` — an env var is the
# only place it can live without becoming just another secret next to the
# ones it protects. Generate one with:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
VARIABLE_ENTORNO_CLAVE_CIFRADO = "ANCLA_CLAVE_CIFRADO"
# Marks a value in `claves_api` as Fernet-encrypted, so a file written before
# this change (plain text, no marker) is told apart from one written after
# it without needing a second field. A Fernet token is itself base64, so the
# marker cannot collide with one.
_PREFIJO_CIFRADO = "fernet:v1:"


class SettingsError(Exception):
    """Failure encrypting or decrypting a saved setting, with a message for
    the user in Spanish — same convention as `profile.errors.ProfileError`:
    the web layer shows it as-is, never a Python traceback."""


def _cipher() -> Fernet:
    clave = os.environ.get(VARIABLE_ENTORNO_CLAVE_CIFRADO, "").strip()
    if not clave:
        raise SettingsError(
            f"Falta la variable de entorno {VARIABLE_ENTORNO_CLAVE_CIFRADO}: es la clave que "
            "cifra las claves de API antes de guardarlas, y sin ella no se pueden guardar ni "
            "leer con seguridad. Genera una y defínela antes de arrancar la app:\n"
            'python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"'
        )
    try:
        return Fernet(clave.encode("utf-8"))
    except (ValueError, TypeError) as error:
        raise SettingsError(
            f"La variable de entorno {VARIABLE_ENTORNO_CLAVE_CIFRADO} no contiene una clave "
            "Fernet válida (debe ser la que genera `Fernet.generate_key()`)."
        ) from error


def _encrypt_keys(claves: dict[str, str]) -> dict[str, str]:
    """Encrypts every non-empty value that is not already marked as
    encrypted — a safety net against double-encrypting a value some future
    caller passes through untouched, rather than something the current
    callers rely on (`load_settings` always hands back plain text)."""
    pendientes = {p: c for p, c in claves.items() if c and not c.startswith(_PREFIJO_CIFRADO)}
    if not pendientes:
        return dict(claves)
    cipher = _cipher()
    return {
        proveedor: (
            _PREFIJO_CIFRADO + cipher.encrypt(clave.encode("utf-8")).decode("ascii")
            if clave and not clave.startswith(_PREFIJO_CIFRADO)
            else clave
        )
        for proveedor, clave in claves.items()
    }


def _decrypt_keys(claves: dict[str, str]) -> dict[str, str]:
    """Values without the marker are read as-is: a plain-text `ajustes.json`
    from before this change keeps working with no migration step, and gets
    encrypted the first time it is saved again (see `save_settings`)."""
    cifradas = {p: c for p, c in claves.items() if c.startswith(_PREFIJO_CIFRADO)}
    if not cifradas:
        return dict(claves)
    cipher = _cipher()
    resultado = {}
    for proveedor, clave in claves.items():
        if not clave.startswith(_PREFIJO_CIFRADO):
            resultado[proveedor] = clave
            continue
        token = clave[len(_PREFIJO_CIFRADO):]
        try:
            resultado[proveedor] = cipher.decrypt(token.encode("ascii")).decode("utf-8")
        except InvalidToken as error:
            raise SettingsError(
                f"No se ha podido descifrar la clave de API guardada para «{proveedor}»: la "
                f"variable de entorno {VARIABLE_ENTORNO_CLAVE_CIFRADO} no coincide con la que se "
                "usó para cifrarla."
            ) from error
    return resultado


PROVEEDOR_POR_DEFECTO = "groq"
# Derived from the registry (`web/providers.py`), not maintained by hand:
# a provider added there is offered here automatically, with no second
# place that can fall out of sync.
#
# "personalizado" is the only one that asks for the URL by hand — the rest
# have it built in (see `Provider.create` in `web/providers.py`), so only a
# user pointing at an unlisted provider (or a local Ollama) needs to type
# it. "anthropic" does not need a URL either: it does not share the generic
# OpenAI-compatible client (its API is different), it has its own module
# with the URL fixed inside, same as Groq.
PROVEEDORES = tuple(PROVIDERS)
# Everyone except Groq needs a model — Groq's own client has a fixed one.
PROVEEDORES_CON_MODELO = tuple(clave for clave, entrada in PROVIDERS.items() if entrada.needs_model)

# The "My profile" sections the user can reorder by dragging. "About me"
# and "Contact" are not here: they are single fixed blocks, not catalogs,
# and always come first, right after the summary counters.
SECCIONES_PERFIL = ("experiencias", "skills", "skills_personales", "idiomas", "educacion")

IDIOMA_POR_DEFECTO = "es"
# Manual selector in the header, never auto-detection: the preference is
# stored here, alongside the rest of the installation's configuration.
IDIOMAS_INTERFAZ = ("es", "en")


@dataclass
class Settings:
    proveedor: str = PROVEEDOR_POR_DEFECTO
    # The key for `proveedor` right now. Kept as a plain field (not derived
    # on every read) so every existing caller that builds or reads a
    # `Settings` by its key alone — `create_client(ajustes.proveedor,
    # ajustes.clave_api, ...)`, the handful of tests that do
    # `Settings(proveedor=..., clave_api=...)` — keeps working unchanged.
    # `claves_api` is the one that actually gets saved to disk long-term:
    # `__post_init__` is what keeps the two from drifting apart.
    clave_api: str = ""
    # One remembered key per provider, so switching providers in Settings
    # does not throw away the key already generated for the previous one.
    claves_api: dict[str, str] = field(default_factory=dict)
    # `url_base` is only saved (and only needed) with proveedor="personalizado"
    # — for everyone else the URL is fixed in `web/providers.py`. `modelo`
    # is needed by everyone except Groq (see PROVEEDORES_CON_MODELO).
    url_base: str = ""
    modelo: str = ""
    orden_perfil: list[str] = field(default_factory=lambda: list(SECCIONES_PERFIL))
    idioma: str = IDIOMA_POR_DEFECTO

    def __post_init__(self) -> None:
        """A `clave_api` passed in (construction, not loading) is what the
        caller means as the key for `proveedor`, so it is recorded into
        `claves_api` under that key. Otherwise `clave_api` is derived back
        out of `claves_api` for `proveedor` — the case `load_settings` hits
        after reading a file that only carries the map."""
        if self.clave_api:
            self.claves_api = {**self.claves_api, self.proveedor: self.clave_api}
        else:
            self.clave_api = self.claves_api.get(self.proveedor, "")

    def saved_key(self, proveedor: str) -> str:
        """The key remembered for a provider other than the one currently
        selected — lets Settings show what is already saved for whichever
        provider the visitor picks in the dropdown, not just for `proveedor`
        (see `static/app.js`, which reads it to swap the key field without
        a page reload)."""
        return self.claves_api.get(proveedor, "")

    def configured(self) -> bool:
        if not self.clave_api.strip():
            return False
        if self.proveedor in PROVEEDORES_CON_MODELO and not self.modelo.strip():
            return False
        if self.proveedor == "personalizado" and not self.url_base.strip():
            return False
        return True


def valid_provider(proveedor: object) -> str:
    if isinstance(proveedor, str) and proveedor in PROVEEDORES:
        return proveedor
    return PROVEEDOR_POR_DEFECTO


def valid_language(idioma: object) -> str:
    if isinstance(idioma, str) and idioma in IDIOMAS_INTERFAZ:
        return idioma
    return IDIOMA_POR_DEFECTO


def valid_profile_order(orden: object) -> list[str]:
    """An order is only valid if it is exactly the four known sections,
    each once. Anything else (a hand-edited file, a new section added to
    the model without updating this) falls back to the default order
    instead of hiding a section or crashing."""
    if isinstance(orden, list) and sorted(orden) == sorted(SECCIONES_PERFIL):
        return list(orden)
    return list(SECCIONES_PERFIL)


def _read_keys(datos: dict[str, Any], proveedor: str) -> dict[str, str]:
    """Reads the per-provider map a current file has, falling back to the
    single `clave_api` a file saved before this change still has — read as
    belonging to `proveedor`, the only provider it could have been for.
    Existing installations keep their key with no rewrite forced on them,
    same approach as `profile/serialization.py`'s `_plain_text` for a field
    that stopped being bilingual."""
    claves = dict(datos.get("claves_api") or {})
    clave_unica = datos.get("clave_api")
    if clave_unica and proveedor not in claves:
        claves[proveedor] = clave_unica
    return claves


def load_settings(ruta: Path = RUTA_POR_DEFECTO) -> Settings:
    """No file yet means not configured, not an error."""
    if not ruta.exists():
        return Settings()
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return Settings()
    proveedor = valid_provider(datos.get("proveedor"))
    return Settings(
        proveedor=proveedor,
        claves_api=_decrypt_keys(_read_keys(datos, proveedor)),
        url_base=datos.get("url_base", ""),
        modelo=datos.get("modelo", ""),
        orden_perfil=valid_profile_order(datos.get("orden_perfil")),
        idioma=valid_language(datos.get("idioma")),
    )


def save_settings(ajustes: Settings, ruta: Path = RUTA_POR_DEFECTO) -> None:
    """Writes `claves_api` encrypted, never in plain text. The redundant
    top-level `clave_api` field (`Settings.__post_init__` derives it back on
    load) is dropped instead of written a second time — writing it plain
    would defeat the encryption above, and writing it encrypted too would
    just be the same secret stored twice."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    datos = asdict(ajustes)
    datos["claves_api"] = _encrypt_keys(ajustes.claves_api)
    del datos["clave_api"]
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
