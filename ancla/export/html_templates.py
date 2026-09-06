"""Discovers the HTML print templates a CV can be laid out with.

Same sidecar rule as the `.docx` templates (`ancla/export/templates.py`):
a `<name>.html` Jinja fragment, its `<name>.css` print stylesheet and a
`<name>.yaml` describing the visible name and how many experiences the
design was drawn for. Adding a template is dropping those files into
`html-templates/` — never a code change.

Nothing about the page geometry is declared here, unlike the `.docx`
sidecar: a browser measures its own text, so there is no line-wrapping to
estimate and no density to solve for. `capacidad_experiencias` survives for
a different reason — it is the number of experiences the design was drawn
around, which the user is told about and can override; it never trims
anything.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from ancla.profile.model import Bilingual

CARPETA_POR_DEFECTO = "html-templates"


@dataclass(frozen=True)
class HtmlTemplate:
    id: str
    name: Bilingual[str]
    path: Path
    capacity_experiences: int

    @property
    def stylesheet_path(self) -> Path:
        return self.path.with_suffix(".css")

    def has_stylesheet(self) -> bool:
        return self.stylesheet_path.is_file()


def list_templates(root: Path) -> list[HtmlTemplate]:
    if not root.exists():
        return []
    plantillas = (_read_sidecar(ruta) for ruta in sorted(root.glob("*.html")))
    return [plantilla for plantilla in plantillas if plantilla is not None]


def find_template(root: Path, id: str) -> HtmlTemplate | None:
    return next((plantilla for plantilla in list_templates(root) if plantilla.id == id), None)


def _read_sidecar(html_path: Path) -> HtmlTemplate | None:
    """`None` for a template whose sidecar is missing or unreadable: one
    someone is still preparing is skipped, the same way the `.docx` side
    does it, instead of breaking the Proposal screen for everyone else."""
    yaml_path = html_path.with_suffix(".yaml")
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
    return HtmlTemplate(
        id=html_path.stem,
        name=Bilingual.from_sidecar(datos.get("nombre"), fallback=html_path.stem),
        path=html_path,
        capacity_experiences=capacidad,
    )
