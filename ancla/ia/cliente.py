"""Interfaz con el proveedor de IA.

La app hace UNA llamada al modelo por adaptación; todo lo demás es determinista.
Groq es el proveedor por defecto porque tiene nivel gratuito: el usuario crea
una cuenta, pega su clave en Ajustes y no paga nada.

La clave es siempre del usuario y vive solo en su máquina. En este repo no hay
ni puede haber credenciales de nadie.
"""
from __future__ import annotations

from typing import Protocol


class ErrorIA(Exception):
    """Fallo al hablar con el proveedor (clave inválida, red, límite de uso)."""


class ClienteIA(Protocol):
    """Lo mínimo que necesita el motor de selección de un proveedor.

    Se define como Protocol para que el motor no dependa de Groq y para poder
    inyectar un cliente falso en los tests sin tocar la red.
    """

    def completar(self, sistema: str, usuario: str) -> str:
        """Devuelve la respuesta del modelo en texto.

        Lanza `ErrorIA` ante cualquier fallo, con un mensaje que se le pueda
        enseñar tal cual al usuario (la causa habitual será la clave).
        """
        ...

    def disponible(self) -> bool:
        """True si hay clave configurada. No comprueba que sea válida."""
        ...
