"""Utilidades pequeñas y sin estado para la capa web."""
from __future__ import annotations

import re
import unicodedata


def slugificar(texto: str) -> str:
    """Convierte un texto libre en un identificador de fichero seguro.

    "Ingeniero de Datos (Backend)" -> "ingeniero-de-datos-backend"
    """
    sin_acentos = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    minusculas = sin_acentos.lower().strip()
    con_guiones = re.sub(r"[^a-z0-9]+", "-", minusculas)
    return con_guiones.strip("-") or "sin-titulo"


def lineas_a_lista(texto: str) -> list[str]:
    """Un textarea de bullets (uno por línea) a `list[str]`, sin líneas vacías."""
    return [linea.strip() for linea in texto.splitlines() if linea.strip()]


def lista_a_lineas(items: list[str]) -> str:
    return "\n".join(items)


def csv_a_lista(texto: str) -> list[str]:
    """Un campo de texto de keywords separadas por comas a `list[str]`."""
    return [item.strip() for item in texto.split(",") if item.strip()]


def lista_a_csv(items: list[str]) -> str:
    return ", ".join(items)
