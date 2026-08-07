"""The candidates from an imported CV currently being reviewed, before
deciding which ones to save into the profile.

Same reason as `borrador.py`: does not fit in a session cookie, so it lives
in a file next to the profile. Not part of `perfil/almacen.py`'s contract
— these are not verified facts yet, they are unconfirmed proposals — which
is why this lives in `web/` and not in `perfil/`.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ancla.profile.model import Bilingual, Experience, Skill, SpokenLanguage

NOMBRE_FICHERO = ".importacion.json"


@dataclass
class ImportBatch:
    experiencias: list[Experience] = field(default_factory=list)
    skills: list[Skill] = field(default_factory=list)
    skills_personales: list[Skill] = field(default_factory=list)
    idiomas: list[SpokenLanguage] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


def _path(root: Path) -> Path:
    return root / NOMBRE_FICHERO


def save_import(root: Path, importacion: ImportBatch) -> None:
    root.mkdir(parents=True, exist_ok=True)
    _path(root).write_text(
        json.dumps(asdict(importacion), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_import(root: Path) -> ImportBatch | None:
    ruta = _path(root)
    if not ruta.exists():
        return None
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        return ImportBatch(
            experiencias=[_to_experience(e) for e in datos["experiencias"]],
            skills=[_to_skill(s) for s in datos["skills"]],
            skills_personales=[_to_skill(s) for s in datos.get("skills_personales", [])],
            idiomas=[_to_language(i) for i in datos.get("idiomas", [])],
            avisos=list(datos.get("avisos", [])),
        )
    except (json.JSONDecodeError, OSError, KeyError, TypeError):
        return None


def delete_import(root: Path) -> None:
    _path(root).unlink(missing_ok=True)


def _to_experience(datos: dict) -> Experience:
    return Experience(
        id=datos["id"],
        title=Bilingual(**datos["title"]),
        period=Bilingual(**datos["period"]),
        bullets=Bilingual(**datos["bullets"]),
        stack=Bilingual(**datos["stack"]),
        keywords=list(datos.get("keywords", [])),
        status=datos.get("status", ""),
    )


def _to_skill(datos: dict) -> Skill:
    return Skill(
        id=datos["id"],
        name=Bilingual(**datos["name"]),
        category=datos.get("category", ""),
        keywords=list(datos.get("keywords", [])),
    )


def _to_language(datos: dict) -> SpokenLanguage:
    return SpokenLanguage(
        id=datos["id"],
        name=Bilingual(**datos["name"]),
        level=Bilingual(**datos["level"]),
        keywords=list(datos.get("keywords", [])),
    )
