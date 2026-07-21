"""El archivo de CVs: cada adaptación queda guardada.

Es lo que convierte la app en algo a lo que se vuelve. Cada vacante deja poso:
la base de hechos crece y el archivo de candidaturas crece con ella.

Se guarda la propuesta estructurada, no un PDF: así se puede reabrir, comparar,
duplicar para una vacante parecida y (en v2) cruzar con el feedback real de la
empresa. Un PDF sería un callejón sin salida.

CONTRATO — implementa el agente D.
"""
from __future__ import annotations

from pathlib import Path

from cv_adaptativo.perfil.modelo import CVGuardado, EstadoCV


def guardar(raiz: Path, cv: CVGuardado) -> None:
    """Escribe `cvs/<fecha>_<empresa>_<puesto>.yaml`."""
    raise NotImplementedError


def listar(raiz: Path) -> list[CVGuardado]:
    """Todos los CV archivados, del más reciente al más antiguo."""
    raise NotImplementedError


def buscar_por_empresa(raiz: Path, empresa: str) -> list[CVGuardado]:
    """CV previos de esa empresa, comparando sin distinguir mayúsculas ni acentos.

    Sostiene el aviso de reciclaje: antes de gastar una llamada al modelo, la
    app avisa de que ya existe un CV para esa empresa y ofrece reutilizarlo.
    Solo avisa — decide el usuario.
    """
    raise NotImplementedError


def cambiar_estado(raiz: Path, id: str, estado: EstadoCV) -> None:
    raise NotImplementedError


def adjuntar(raiz: Path, id: str, archivo: Path) -> Path:
    """Copia el CV final del usuario a `cvs/adjuntos/` y devuelve su ruta.

    Cualquier formato vale (PDF, docx, imagen). No se valida ni se convierte:
    el diseño es cosa del usuario y de su herramienta.
    """
    raise NotImplementedError
