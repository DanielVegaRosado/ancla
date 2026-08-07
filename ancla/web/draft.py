"""The proposal currently being reviewed, before it is saved to the archive.

Not part of `perfil/almacen.py`'s contract (that is verified facts); this
is ephemeral working state for the Adapt → Proposal screen. Lives in a file
next to the profile rather than in a Flask session cookie because a whole
pasted job posting does not fit in a signed cookie's ~4 KB.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from ancla.profile.model import (
    Proposal,
    SelectedAboutMe,
    SelectedExperience,
)

NOMBRE_FICHERO = ".borrador.json"


@dataclass
class Draft:
    vacante: str
    empresa: str
    puesto: str
    propuesta: Proposal


def _path(root: Path) -> Path:
    return root / NOMBRE_FICHERO


def save_draft(root: Path, borrador: Draft) -> None:
    root.mkdir(parents=True, exist_ok=True)
    _path(root).write_text(
        json.dumps(asdict(borrador), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_draft(root: Path) -> Draft | None:
    ruta = _path(root)
    if not ruta.exists():
        return None
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        propuesta_datos = datos["propuesta"]
        propuesta = Proposal(
            language=propuesta_datos["language"],
            about_me=SelectedAboutMe(**propuesta_datos["about_me"]),
            skills=list(propuesta_datos["skills"]),
            experiences=[
                SelectedExperience(**e) for e in propuesta_datos["experiences"]
            ],
            skills_reason=propuesta_datos.get("skills_reason", ""),
            gaps=list(propuesta_datos.get("gaps", [])),
        )
        return Draft(
            vacante=datos["vacante"],
            empresa=datos["empresa"],
            puesto=datos["puesto"],
            propuesta=propuesta,
        )
    except (json.JSONDecodeError, OSError, KeyError, TypeError):
        return None


def delete_draft(root: Path) -> None:
    _path(root).unlink(missing_ok=True)
