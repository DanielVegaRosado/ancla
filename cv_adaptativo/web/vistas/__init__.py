"""Una pantalla, un módulo: `perfil`, `adaptar`, `propuesta`, `cvs`, `ajustes`,
`soporte`. Cada uno registra sus rutas en `cv_adaptativo.web.blueprint.bp` al
importarse — importar este paquete es lo único que hace falta para que todas
las rutas queden dadas de alta.
"""
from __future__ import annotations

from cv_adaptativo.web.vistas import adaptar, ajustes, cvs, perfil, propuesta, soporte

__all__ = ["adaptar", "ajustes", "cvs", "perfil", "propuesta", "soporte"]
