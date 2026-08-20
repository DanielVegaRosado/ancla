"""Discovers Canva template previews (PDFs Daniel exported by hand) from a
folder. Same pattern as `ancla/export/templates.py`: a `<nombre>.pdf`
paired with a sibling `<nombre>.yaml` for its visible name (`nombre: Texto`
for the same name in both languages, or `nombre: {es: ..., en: ...}` for a
different one per interface language). Adding one never touches code —
drop both files in `canva-templates/` and it shows up. A `.pdf` without
its `.yaml`, or with one that fails to parse, is skipped.

These are design references shown inline in the app, never filled or
exported — unrelated to `ancla/export/templates.py`'s `.docx` templates,
even though a design and its matching export template often share a name.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from ancla.profile.model import Bilingual

CARPETA_POR_DEFECTO = "canva-templates"


@dataclass(frozen=True)
class DesignTemplate:
    id: str
    name: Bilingual[str]
    path: Path


def list_templates(root: Path) -> list[DesignTemplate]:
    if not root.exists():
        return []
    plantillas = []
    for pdf_path in sorted(root.glob("*.pdf")):
        plantilla = _read_sidecar(pdf_path)
        if plantilla is not None:
            plantillas.append(plantilla)
    return plantillas


def find_template(root: Path, id: str) -> DesignTemplate | None:
    return next((plantilla for plantilla in list_templates(root) if plantilla.id == id), None)


def _read_sidecar(pdf_path: Path) -> DesignTemplate | None:
    yaml_path = pdf_path.with_suffix(".yaml")
    if not yaml_path.exists():
        return None
    try:
        datos = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return None
    if not isinstance(datos, dict):
        return None
    return DesignTemplate(
        id=pdf_path.stem, name=Bilingual.from_sidecar(datos.get("nombre"), fallback=pdf_path.stem), path=pdf_path
    )
