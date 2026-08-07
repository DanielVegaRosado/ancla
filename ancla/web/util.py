"""Small, stateless utilities for the web layer."""
from __future__ import annotations

# Re-exported on purpose: `slugificar` lives in `ancla.text` because
# `perfil/importador.py` also needs it, and `perfil/` cannot depend on
# `web/` (the dependency always runs the other way). This module keeps
# exposing it here so every place that already imported it from here
# does not need to change.
from ancla.text import slugify

__all__ = ["slugificar", "lineas_a_lista", "lista_a_lineas", "csv_a_lista", "lista_a_csv"]


def lines_to_list(texto: str) -> list[str]:
    """A bullets textarea (one per line) into `list[str]`, with blank lines dropped."""
    return [linea.strip() for linea in texto.splitlines() if linea.strip()]


def list_to_lines(items: list[str]) -> str:
    return "\n".join(items)


def csv_to_list(texto: str) -> list[str]:
    """A comma-separated keywords text field into `list[str]`."""
    return [item.strip() for item in texto.split(",") if item.strip()]


def list_to_csv(items: list[str]) -> str:
    return ", ".join(items)
