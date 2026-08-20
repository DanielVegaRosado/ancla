"""Discovers `.docx` export templates from a folder.

Each template is a `<nombre>.docx` file paired with a sibling
`<nombre>.yaml` describing its visible name (`nombre: Texto` for the same
name in both languages, or `nombre: {es: ..., en: ...}` for a different
one per interface language), how many experiences fit, and optionally the
page geometry `ancla/export/fill.py` needs to loosen its experience block
when there are fewer. Adding a template never touches code: drop the two
files in `docx-templates/` and it shows up. A `.docx` without its `.yaml`,
or with one that fails to parse, is skipped rather than crashing the
Proposal screen — a template someone is still preparing should not break
the app for everyone else's.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ancla.profile.model import Bilingual

CARPETA_POR_DEFECTO = "docx-templates"


@dataclass(frozen=True)
class TemplateGeometry:
    """The page measurements a template's experience block needs to
    estimate line-wrapping and solve for a density scale — see
    `fill.py::_escala_necesaria`. Design values specific to one template's
    layout, not business parameters; a template's own build script is
    responsible for writing them to its `.yaml` (see
    `herramientas/construir-corporativa-clasica.py`), so they only ever get
    typed by hand once, in one place.
    """

    ancho_columna: float
    # The experience title shares its row with the date, in a narrower
    # column than the rest of the block (`MAIN_TEXT_W - DATE_W`, not just
    # the bullet hanging indent) — using the wider `ancho_columna` for it
    # underestimates how often a long title actually wraps to a second
    # line, which is exactly the kind of real, per-experience height this
    # whole model exists to measure instead of guess.
    ancho_columna_titulo: float
    alto_pagina: float
    margen_inferior_seguridad: float
    # Fixed chrome above the experience block: top margin, spacing around
    # the name/role, the "Experience" header's own text/spacing/rule.
    # Nothing here depends on the proposal's actual content — the name and
    # role themselves are measured separately below, from their real text,
    # precisely because *those* do vary per profile.
    altura_hasta_experiencia: float
    # Fixed chrome below the experience block for whatever the design puts
    # after it — its section header, spacing, and rule, NOT the paragraph
    # of text itself (Corporativa Clásica has nothing there: 0. Minimalista
    # Cálida has "About me" below Experience instead of above it).
    altura_tras_experiencia: float
    # Font size/line-spacing for text `fill.py` measures from its real
    # content instead of assuming a fixed length — a name, a role, or an
    # "About me" paragraph all vary per profile/proposal, so a flat guess
    # either overshoots (blank gap) or undershoots (spills to a second
    # page) depending on how long this particular one turned out. 0 means
    # this template has no such text in that slot (e.g. Corporativa
    # Clásica's `tamano_texto_tras_experiencia`, since nothing follows).
    tamano_nombre_primero: float
    tamano_nombre_resto: float
    tamano_titular: float
    # "About me" (or any long free-text block) can sit either before the
    # experience block (Corporativa Clásica) or after it (Minimalista
    # Cálida) depending on the design — both slots are always measured
    # from the same text (`fill.py` doesn't need to know which template
    # puts it where); the template that doesn't use a slot declares 0
    # there and it contributes nothing.
    tamano_texto_antes_experiencia: float
    linea_texto_antes_experiencia: float
    tamano_texto_tras_experiencia: float
    linea_texto_tras_experiencia: float
    tamano_titulo: float
    tamano_cuerpo: float
    tamano_stack: float
    espacio_titulo: float
    espacio_bullet: float
    linea_bullet: float
    calibracion: float
    # Name of the font this template's build script used — which real
    # character-width table `fill.py` has to use to estimate line-wrapping.
    # Different fonts have different average glyph widths (Montserrat is
    # noticeably wider than Aileron), so this can't be assumed or shared
    # across templates.
    fuente: str


@dataclass(frozen=True)
class ExportTemplate:
    id: str
    name: Bilingual[str]
    path: Path
    capacity_experiences: int
    # None for a template that doesn't opt into density adjustment — either
    # it wasn't built with `_ajustar_densidad_experiencias`'s table
    # structure in mind, or its `.yaml` simply doesn't declare `geometria`.
    geometry: TemplateGeometry | None = None


def list_templates(root: Path) -> list[ExportTemplate]:
    if not root.exists():
        return []
    plantillas = []
    for docx_path in sorted(root.glob("*.docx")):
        plantilla = _read_sidecar(docx_path)
        if plantilla is not None:
            plantillas.append(plantilla)
    return plantillas


def find_template(root: Path, id: str) -> ExportTemplate | None:
    return next((plantilla for plantilla in list_templates(root) if plantilla.id == id), None)


def _read_sidecar(docx_path: Path) -> ExportTemplate | None:
    yaml_path = docx_path.with_suffix(".yaml")
    if not yaml_path.exists():
        return None
    try:
        datos = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return None
    if not isinstance(datos, dict):
        return None
    try:
        capacidad = int(datos.get("capacidad_experiencias", 0))
    except (TypeError, ValueError):
        capacidad = 0
    return ExportTemplate(
        id=docx_path.stem,
        name=Bilingual.from_sidecar(datos.get("nombre"), fallback=docx_path.stem),
        path=docx_path,
        capacity_experiences=capacidad,
        geometry=_read_geometry(datos.get("geometria")),
    )


def _read_geometry(datos: Any) -> TemplateGeometry | None:
    if not isinstance(datos, dict):
        return None
    try:
        campos_numericos = {
            campo: float(datos[campo]) for campo in TemplateGeometry.__dataclass_fields__ if campo != "fuente"
        }
        fuente = str(datos["fuente"])
        return TemplateGeometry(**campos_numericos, fuente=fuente)
    except (TypeError, ValueError, KeyError):
        # Missing or non-numeric field: same "skip, don't crash" rule as
        # the rest of the sidecar — this template just renders without the
        # density adjustment.
        return None
