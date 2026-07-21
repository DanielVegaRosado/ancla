"""Extracción de datos de la vacante pegada por el usuario.

Solo lo determinista y barato: empresa y puesto, para nombrar el CV en el
archivo y poder avisar de que ya existe uno de esa empresa antes de gastar una
llamada al modelo. El análisis de requisitos de verdad lo hace el motor, dentro
de esa única llamada.

CONTRATO — implementa el agente B.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DatosVacante:
    empresa: str = ""
    puesto: str = ""


def extraer_datos(vacante: str) -> DatosVacante:
    """Intenta adivinar empresa y puesto del texto pegado.

    Es una heurística: devuelve cadenas vacías si no lo ve claro, y la web
    deja que el usuario los corrija siempre. Nunca bloquea el flujo.
    """
    raise NotImplementedError
