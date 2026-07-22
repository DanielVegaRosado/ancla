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


def slugificar(texto: str) -> str:
    """Convierte un texto libre en un identificador de fichero seguro.

    "Ingeniero de Datos (Backend)" -> "ingeniero-de-datos-backend"
    """
    sin_acentos = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    minusculas = sin_acentos.lower().strip()
    con_guiones = re.sub(r"[^a-z0-9]+", "-", minusculas)
    return con_guiones.strip("-") or "sin-titulo"


def normalizar(texto: str) -> str:
    """Minúsculas, sin acentos y sin espacios de más, para comparar.

    Compara texto que escriben personas distintas —el usuario en su perfil, el
    modelo en su respuesta, la empresa en la oferta— así que "FastAPI",
    "fastapi" y "Fast API " tienen que caer en el mismo sitio.
    """
    descompuesto = unicodedata.normalize("NFKD", texto or "")
    sin_acentos = "".join(c for c in descompuesto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sin_acentos).strip().lower()


def bloque_json(texto: str) -> str | None:
    """El primer objeto `{...}` equilibrado del texto, o `None` si no hay uno.

    Los modelos envuelven el JSON en ```json o lo preceden de una frase amable
    por mucho que el prompt lo prohíba; recortarlo aquí sale más barato que
    gastar otra llamada. Cuenta profundidad de llaves y respeta las cadenas de
    texto (una `{` dentro de un bullet no rompe el conteo), a diferencia de
    buscar la primera y la última llave del texto sin más.
    """
    inicio = (texto or "").find("{")
    if inicio == -1:
        return None
    profundidad = 0
    en_cadena = False
    escapado = False
    for pos in range(inicio, len(texto)):
        caracter = texto[pos]
        if en_cadena:
            if escapado:
                escapado = False
            elif caracter == "\\":
                escapado = True
            elif caracter == '"':
                en_cadena = False
        elif caracter == '"':
            en_cadena = True
        elif caracter == "{":
            profundidad += 1
        elif caracter == "}":
            profundidad -= 1
            if profundidad == 0:
                return texto[inicio : pos + 1]
    return None
