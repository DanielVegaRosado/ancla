"""Render de la propuesta a texto que el usuario copia y pega.

La app no genera el PDF: el diseño sigue siendo del usuario (Canva u otra
herramienta). Aquí solo se produce texto limpio, en el mismo orden en que
aparece en el CV, listo para pegar bloque a bloque.

CONTRATO — implementa el agente C.
"""
from __future__ import annotations

from cv_adaptativo.perfil.modelo import Perfil, Propuesta


def a_texto(propuesta: Propuesta, perfil: Perfil) -> str:
    """Texto plano, para pegar en Canva. Sin motivos: solo el contenido del CV."""
    raise NotImplementedError


def a_markdown(propuesta: Propuesta, perfil: Perfil) -> str:
    """Markdown con los motivos y los huecos detectados, para guardar o revisar."""
    raise NotImplementedError
