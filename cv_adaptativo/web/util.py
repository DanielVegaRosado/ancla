"""Utilidades pequeñas y sin estado para la capa web."""
from __future__ import annotations

# Reexportado a propósito: `slugificar` vive en `cv_adaptativo.texto` porque
# también la necesita `perfil/importador.py`, y `perfil/` no puede depender
# de `web/` (la dependencia va siempre en el otro sentido). Este módulo la
# sigue exponiendo aquí para no tocar cada sitio que ya la importaba de aquí.
from cv_adaptativo.texto import slugificar

__all__ = ["slugificar", "lineas_a_lista", "lista_a_lineas", "csv_a_lista", "lista_a_csv"]


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
