"""Discovers the HTML print templates a CV can be laid out with.

Same sidecar rule as the `.docx` templates (`ancla/export/templates.py`):
a `<name>.html` Jinja fragment, its `<name>.css` print stylesheet and a
`<name>.yaml` describing the visible name and how many experiences the
design was drawn for. Adding a template is dropping those files into
`html-templates/` — never a code change.

Nothing about the page geometry is declared here, unlike the `.docx`
sidecar: a browser measures its own text, so there is no line-wrapping to
estimate and no density to solve for. What a `.yaml` here declares instead
is a *range* — `capacidad_experiencias_min`/`_max` — because a browser can
measure text but not judge taste: too few experiences and a design like
Minimalista Cálida looks sparse, too many and the layout no longer fits the
one page it was drawn for. Unlike the `.docx` path (which spills onto a
second page rather than lose anything), the printable HTML preview cannot
let more than `capacity_max` through — see `ancla/web/views/cv_preview.py`.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ancla.export.templates import read_yaml_sidecar
from ancla.profile.model import Bilingual

CARPETA_POR_DEFECTO = "html-templates"


@dataclass(frozen=True)
class HtmlTemplate:
    id: str
    name: Bilingual[str]
    path: Path
    # The range of experiences the design was drawn for. A sidecar that
    # doesn't declare `capacidad_experiencias_min`/`_max` (or declares a
    # non-positive value) falls back to 3/5 — the standard range every
    # current template already states explicitly — rather than crashing or
    # going unbounded.
    capacity_min: int
    capacity_max: int

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
    """`None` for a template whose sidecar is missing, unreadable, or
    declares a range that makes no sense (a minimum above its own maximum):
    one someone is still preparing is skipped, the same way the `.docx`
    side does it, instead of breaking the Proposal screen for everyone
    else."""
    datos = read_yaml_sidecar(html_path)
    if datos is None:
        return None
    capacidad_min = _entero_positivo(datos.get("capacidad_experiencias_min"), por_defecto=3)
    capacidad_max = _entero_positivo(datos.get("capacidad_experiencias_max"), por_defecto=5)
    if capacidad_max and capacidad_min > capacidad_max:
        return None
    return HtmlTemplate(
        id=html_path.stem,
        name=Bilingual.from_sidecar(datos.get("nombre"), fallback=html_path.stem),
        path=html_path,
        capacity_min=capacidad_min,
        capacity_max=capacidad_max,
    )


def _entero_positivo(valor: object, *, por_defecto: int) -> int:
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        return por_defecto
    return numero if numero > 0 else por_defecto
