"""App settings: AI provider and API key.

Distinct from `perfil/`: these are not user facts, they are local
installation configuration. They live in `ajustes.json`, at the project
root, and are **never** pushed to the repository (see `.gitignore`). The
key always belongs to the user.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ancla.web.routes import data_root

RUTA_POR_DEFECTO = data_root() / "ajustes.json"

PROVEEDOR_POR_DEFECTO = "groq"
# "personalizado" is the only one that asks for the URL by hand — the rest
# have it built in (see `web/proveedores.py`), so only a user pointing at
# an unlisted provider (or a local Ollama) needs to type it.
# "anthropic" does not need a URL either: it does not share the generic
# OpenAI-compatible client (its API is different), it has its own module
# with the URL fixed inside, same as Groq.
PROVEEDORES = ("groq", "openai", "anthropic", "mistral", "openrouter", "personalizado")
# Everyone except Groq needs the user to say which model they want — Groq's
# is fixed.
PROVEEDORES_CON_MODELO = ("openai", "anthropic", "mistral", "openrouter", "personalizado")

# The four "My profile" sections the user can reorder by dragging. "About
# me" is not here: it is the profile's template, not a catalog, and always
# comes first.
SECCIONES_PERFIL = ("experiencias", "skills", "skills_personales", "idiomas")

IDIOMA_POR_DEFECTO = "es"
# Manual selector in the header, never auto-detection: the preference is
# stored here, alongside the rest of the installation's configuration.
IDIOMAS_INTERFAZ = ("es", "en")


@dataclass
class Settings:
    proveedor: str = PROVEEDOR_POR_DEFECTO
    clave_api: str = ""
    # `url_base` is only saved (and only needed) with proveedor="personalizado"
    # — for everyone else the URL is fixed in `web/proveedores.py`. `modelo`
    # is needed by everyone except Groq (see PROVEEDORES_CON_MODELO).
    url_base: str = ""
    modelo: str = ""
    orden_perfil: list[str] = field(default_factory=lambda: list(SECCIONES_PERFIL))
    idioma: str = IDIOMA_POR_DEFECTO

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


def load_settings(ruta: Path = RUTA_POR_DEFECTO) -> Settings:
    """No file yet means not configured, not an error."""
    if not ruta.exists():
        return Settings()
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return Settings()
    return Settings(
        proveedor=valid_provider(datos.get("proveedor")),
        clave_api=datos.get("clave_api", ""),
        url_base=datos.get("url_base", ""),
        modelo=datos.get("modelo", ""),
        orden_perfil=valid_profile_order(datos.get("orden_perfil")),
        idioma=valid_language(datos.get("idioma")),
    )


def save_settings(ajustes: Settings, ruta: Path = RUTA_POR_DEFECTO) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(asdict(ajustes), ensure_ascii=False, indent=2), encoding="utf-8")
