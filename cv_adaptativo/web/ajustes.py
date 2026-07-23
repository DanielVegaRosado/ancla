"""Ajustes de la app: proveedor de IA y clave de API.

Distintos de `perfil/`: no son hechos del usuario, son configuración de la
instalación local. Viven en `ajustes.json`, en la raíz del proyecto, y **nunca**
se suben al repositorio (ver `.gitignore`). La clave es siempre del usuario.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

RAIZ_APP = Path(__file__).resolve().parents[2]
RUTA_POR_DEFECTO = RAIZ_APP / "ajustes.json"

PROVEEDOR_POR_DEFECTO = "groq"

# Las cuatro secciones de "Mi perfil" que el usuario puede reordenar
# arrastrando. "Sobre mí" no está aquí: es la plantilla del perfil, no un
# catálogo, y siempre va primero.
SECCIONES_PERFIL = ("experiencias", "skills", "skills_personales", "idiomas")


@dataclass
class Ajustes:
    proveedor: str = PROVEEDOR_POR_DEFECTO
    clave_api: str = ""
    orden_perfil: list[str] = field(default_factory=lambda: list(SECCIONES_PERFIL))

    def configurado(self) -> bool:
        return bool(self.clave_api.strip())


def orden_perfil_valido(orden: object) -> list[str]:
    """Un orden solo vale si es exactamente las cuatro secciones conocidas,
    cada una una vez. Cualquier otra cosa (fichero editado a mano, una
    sección nueva añadida al modelo sin actualizar aquí) cae al orden por
    defecto en vez de esconder una sección o reventar."""
    if isinstance(orden, list) and sorted(orden) == sorted(SECCIONES_PERFIL):
        return list(orden)
    return list(SECCIONES_PERFIL)


def cargar_ajustes(ruta: Path = RUTA_POR_DEFECTO) -> Ajustes:
    """Sin fichero todavía = sin configurar, no un error."""
    if not ruta.exists():
        return Ajustes()
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return Ajustes()
    return Ajustes(
        proveedor=datos.get("proveedor", PROVEEDOR_POR_DEFECTO),
        clave_api=datos.get("clave_api", ""),
        orden_perfil=orden_perfil_valido(datos.get("orden_perfil")),
    )


def guardar_ajustes(ajustes: Ajustes, ruta: Path = RUTA_POR_DEFECTO) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(asdict(ajustes), ensure_ascii=False, indent=2), encoding="utf-8")
