"""El error del perfil, en un módulo propio para que no haya importaciones circulares.

Lo lanzan tanto `almacen` (ficheros y carpetas) como `serializacion` (formato
YAML), y ninguno de los dos puede importar del otro sin morderse la cola.
"""
from __future__ import annotations


class ErrorPerfil(Exception):
    """Fallo leyendo o escribiendo el perfil, con un mensaje para el usuario.

    El texto va en español y nombra el fichero: la capa web lo enseña tal cual,
    nunca una traza de Python.
    """
