"""Utilidades de texto compartidas por todo el paquete.

Aquí solo vive lo que necesita más de un módulo. Es a propósito: dos copias de
la misma normalización acaban divergiendo, y el día que una empiece a ignorar
los acentos y la otra no, el motor dirá que "Aprendizaje automático" es un
hueco del perfil cuando la skill está ahí.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any


def a_texto(valor: Any) -> str:
    """Un texto limpio, o cadena vacía si lo que venía no era un texto.

    Todo lo que se lee de fuera —la respuesta del modelo, un YAML editado a
    mano— puede traer un número, `None` o una lista donde se esperaba texto.
    Aquí se decide una vez que eso significa "vacío" y no una excepción.
    """
    return valor.strip() if isinstance(valor, str) else ""


def a_textos(valor: Any) -> list[str]:
    """Una lista de textos no vacíos, descartando lo que no lo sea."""
    if not isinstance(valor, list):
        return []
    return [limpio for elemento in valor if (limpio := a_texto(elemento))]


def normalizar(texto: str) -> str:
    """Minúsculas, sin acentos y sin espacios de más, para comparar.

    Compara texto que escriben personas distintas —el usuario en su perfil, el
    modelo en su respuesta, la empresa en la oferta— así que "FastAPI",
    "fastapi" y "Fast API " tienen que caer en el mismo sitio.
    """
    descompuesto = unicodedata.normalize("NFKD", texto or "")
    sin_acentos = "".join(c for c in descompuesto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sin_acentos).strip().lower()
