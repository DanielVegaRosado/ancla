"""Ajustes de la app: proveedor de IA y clave de API.

Distintos de `perfil/`: no son hechos del usuario, son configuración de la
instalación local. Viven en `ajustes.json`, en la raíz del proyecto, y **nunca**
se suben al repositorio (ver `.gitignore`). La clave es siempre del usuario.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

RAIZ_APP = Path(__file__).resolve().parents[2]
RUTA_POR_DEFECTO = RAIZ_APP / "ajustes.json"

PROVEEDOR_POR_DEFECTO = "groq"


@dataclass
class Ajustes:
    proveedor: str = PROVEEDOR_POR_DEFECTO
    clave_api: str = ""

    def configurado(self) -> bool:
        return bool(self.clave_api.strip())


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
    )


def guardar_ajustes(ajustes: Ajustes, ruta: Path = RUTA_POR_DEFECTO) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(asdict(ajustes), ensure_ascii=False, indent=2), encoding="utf-8")
