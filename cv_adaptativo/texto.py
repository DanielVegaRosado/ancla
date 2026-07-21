"""Utilidades de texto compartidas por todo el paquete.

Aquí solo vive lo que necesita más de un módulo. Es a propósito: dos copias de
la misma normalización acaban divergiendo, y el día que una empiece a ignorar
los acentos y la otra no, el motor dirá que "Aprendizaje automático" es un
hueco del perfil cuando la skill está ahí.
"""
from __future__ import annotations

import re
import unicodedata


def normalizar(texto: str) -> str:
    """Minúsculas, sin acentos y sin espacios de más, para comparar.

    Compara texto que escriben personas distintas —el usuario en su perfil, el
    modelo en su respuesta, la empresa en la oferta— así que "FastAPI",
    "fastapi" y "Fast API " tienen que caer en el mismo sitio.
    """
    descompuesto = unicodedata.normalize("NFKD", texto or "")
    sin_acentos = "".join(c for c in descompuesto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sin_acentos).strip().lower()
