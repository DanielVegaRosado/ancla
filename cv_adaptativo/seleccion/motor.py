"""El núcleo: elegir qué mostrar del perfil para una vacante concreta.

Esta es la pieza que distingue al producto. No redacta un CV: **selecciona**
entre hechos que el usuario ya ha verificado, los ordena por relevancia y
explica por qué ha elegido cada uno.

Reglas duras, heredadas de la skill personal `/cv-adaptativo`:

1. Nunca proponer una experiencia o skill que no exista en el perfil. Si la
   vacante pide algo que el usuario no tiene, va a `huecos`, no al CV.
2. Nunca reescribir los bullets del usuario: se muestran tal cual los escribió.
3. Toda elección lleva motivo. Sin motivo, el usuario no puede juzgar la
   propuesta, y juzgarla es justo lo que le pedimos que haga.

CONTRATO — implementa el agente B.
"""
from __future__ import annotations

from cv_adaptativo.ia.cliente import ClienteIA
from cv_adaptativo.perfil.modelo import (
    N_EXPERIENCIAS,
    N_SKILLS,
    Idioma,
    Perfil,
    Propuesta,
)


def adaptar(
    perfil: Perfil,
    vacante: str,
    idioma: Idioma,
    cliente: ClienteIA,
    n_experiencias: int = N_EXPERIENCIAS,
    n_skills: int = N_SKILLS,
) -> Propuesta:
    """Adapta el perfil a la vacante. Una sola llamada al modelo.

    Si el perfil tiene menos elementos de los pedidos, devuelve los que haya:
    completar el hueco inventando es exactamente lo que no hace este producto.

    Lanza `ErrorIA` si el proveedor falla, y `ValueError` si el perfil está
    vacío o no tiene plantilla de "Sobre mí".
    """
    raise NotImplementedError
