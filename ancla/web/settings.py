"""App settings: AI provider and API key.

Distinct from `perfil/`: these are not user facts, they are local
installation configuration. They live in `ajustes.json`, next to `perfil/` in
`data_root()`, and are **never** pushed to the repository (see `.gitignore`). The
key always belongs to the user.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ancla.web.providers import PROVIDERS
from ancla.web.routes import SETTINGS_FILE_NAME, data_root

RUTA_POR_DEFECTO = data_root() / SETTINGS_FILE_NAME

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
        claves_api=_read_keys(datos, proveedor),
        url_base=datos.get("url_base", ""),
        modelo=datos.get("modelo", ""),
        orden_perfil=valid_profile_order(datos.get("orden_perfil")),
        idioma=valid_language(datos.get("idioma")),
    )


def save_settings(ajustes: Settings, ruta: Path = RUTA_POR_DEFECTO) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(asdict(ajustes), ensure_ascii=False, indent=2), encoding="utf-8")
