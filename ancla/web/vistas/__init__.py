"""Una pantalla, un módulo: `perfil`, `adaptar`, `propuesta`, `cvs`, `ajustes`,
`soporte`, `plantillas`, `importar`, `terminos`. Cada uno registra sus rutas
en `ancla.web.blueprint.bp` al importarse — importar este paquete es
lo único que hace falta para que todas las rutas queden dadas de alta.
"""
from __future__ import annotations

from ancla.web.vistas import (
    adaptar,
    ajustes,
    cvs,
    importar,
    perfil,
    plantillas,
    propuesta,
    soporte,
    terminos,
)

__all__ = [
    "adaptar",
    "ajustes",
    "cvs",
    "importar",
    "perfil",
    "plantillas",
    "propuesta",
    "soporte",
    "terminos",
]
