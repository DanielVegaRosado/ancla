"""Las candidatas de un CV importado que se están revisando ahora mismo, antes
de decidir cuáles guardar en el perfil.

Mismo motivo que `borrador.py`: no cabe en una cookie de sesión, así que vive
en un fichero junto al perfil. No es parte del contrato de `perfil/almacen.py`
—esto no son hechos verificados todavía, son propuestas sin confirmar—, por
eso vive en `web/` y no en `perfil/`.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from cv_adaptativo.perfil.modelo import Bilingue, Experiencia, IdiomaHablado, Skill

NOMBRE_FICHERO = ".importacion.json"


@dataclass
class Importacion:
    experiencias: list[Experiencia] = field(default_factory=list)
    skills: list[Skill] = field(default_factory=list)
    skills_personales: list[Skill] = field(default_factory=list)
    idiomas: list[IdiomaHablado] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


def _ruta(raiz: Path) -> Path:
    return raiz / NOMBRE_FICHERO


def guardar_importacion(raiz: Path, importacion: Importacion) -> None:
    raiz.mkdir(parents=True, exist_ok=True)
    _ruta(raiz).write_text(
        json.dumps(asdict(importacion), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def cargar_importacion(raiz: Path) -> Importacion | None:
    ruta = _ruta(raiz)
    if not ruta.exists():
        return None
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        return Importacion(
            experiencias=[_a_experiencia(e) for e in datos["experiencias"]],
            skills=[_a_skill(s) for s in datos["skills"]],
            skills_personales=[_a_skill(s) for s in datos.get("skills_personales", [])],
            idiomas=[_a_idioma(i) for i in datos.get("idiomas", [])],
            avisos=list(datos.get("avisos", [])),
        )
    except (json.JSONDecodeError, OSError, KeyError, TypeError):
        return None


def borrar_importacion(raiz: Path) -> None:
    _ruta(raiz).unlink(missing_ok=True)


def _a_experiencia(datos: dict) -> Experiencia:
    return Experiencia(
        id=datos["id"],
        titulo=Bilingue(**datos["titulo"]),
        periodo=Bilingue(**datos["periodo"]),
        bullets=Bilingue(**datos["bullets"]),
        stack=Bilingue(**datos["stack"]),
        keywords=list(datos.get("keywords", [])),
        estado=datos.get("estado", ""),
    )


def _a_skill(datos: dict) -> Skill:
    return Skill(
        id=datos["id"],
        nombre=Bilingue(**datos["nombre"]),
        categoria=datos.get("categoria", ""),
        keywords=list(datos.get("keywords", [])),
    )


def _a_idioma(datos: dict) -> IdiomaHablado:
    return IdiomaHablado(
        id=datos["id"],
        nombre=Bilingue(**datos["nombre"]),
        nivel=Bilingue(**datos["nivel"]),
        keywords=list(datos.get("keywords", [])),
    )
