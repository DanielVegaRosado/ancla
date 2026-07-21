"""La propuesta que se está revisando ahora mismo, antes de guardarla en el archivo.

No es parte del contrato de `perfil/almacen.py` (eso son hechos verificados);
esto es estado de trabajo efímero de la pantalla Adaptar → Propuesta. Vive en
un fichero junto al perfil en vez de en la cookie de sesión de Flask porque una
vacante pegada entera no cabe en los ~4 KB de una cookie firmada.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from cv_adaptativo.perfil.modelo import (
    ExperienciaSeleccionada,
    Propuesta,
    SeleccionSobreMi,
)

NOMBRE_FICHERO = ".borrador.json"


@dataclass
class Borrador:
    vacante: str
    empresa: str
    puesto: str
    propuesta: Propuesta


def _ruta(raiz: Path) -> Path:
    return raiz / NOMBRE_FICHERO


def guardar_borrador(raiz: Path, borrador: Borrador) -> None:
    raiz.mkdir(parents=True, exist_ok=True)
    _ruta(raiz).write_text(
        json.dumps(asdict(borrador), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def cargar_borrador(raiz: Path) -> Borrador | None:
    ruta = _ruta(raiz)
    if not ruta.exists():
        return None
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        propuesta_datos = datos["propuesta"]
        propuesta = Propuesta(
            idioma=propuesta_datos["idioma"],
            sobre_mi=SeleccionSobreMi(**propuesta_datos["sobre_mi"]),
            skills=list(propuesta_datos["skills"]),
            experiencias=[
                ExperienciaSeleccionada(**e) for e in propuesta_datos["experiencias"]
            ],
            motivo_skills=propuesta_datos.get("motivo_skills", ""),
            huecos=list(propuesta_datos.get("huecos", [])),
        )
        return Borrador(
            vacante=datos["vacante"],
            empresa=datos["empresa"],
            puesto=datos["puesto"],
            propuesta=propuesta,
        )
    except (json.JSONDecodeError, OSError, KeyError, TypeError):
        return None


def borrar_borrador(raiz: Path) -> None:
    _ruta(raiz).unlink(missing_ok=True)
