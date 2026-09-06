"""Lays a proposal out as printable HTML — the browser-rendered
counterpart of `fill.py`'s `.docx`.

The field catalog is not redefined here: it is `fill.build_context` itself,
so anything a `.docx` template can show an HTML one can show too, and the
two can never drift apart. What changes is who measures the text. A `.docx`
cannot be measured without rendering it, which is why `fill.py` estimates
line wrapping from character-width tables; a browser knows the height of
every line it draws, so the page break is expressed as a rule
(`break-inside: avoid`) instead of being solved for.

Templates render in their own Jinja environment, rooted at the templates
folder and deliberately separate from the app's own
(`ancla/web/templates/`): a CV design is a document, not a screen. It must
not be able to extend `base.html`, and a file dropped into
`html-templates/` must never shadow one of the interface's screens.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ancla.export import fill
from ancla.export.html_templates import HtmlTemplate
from ancla.profile.model import Experience, Profile, Proposal


def render(
    plantilla: HtmlTemplate,
    propuesta: Proposal,
    perfil: Profile,
    experiencias: list[Experience],
    nombre: str,
    photo_url: str = "",
) -> str:
    """The template's own markup, filled with the proposal's content. Not a
    whole page: the preview screen wraps it, so a template only ever
    describes the CV itself."""
    contexto = fill.build_context(propuesta, perfil, experiencias, nombre, photo_url)
    return _environment(plantilla.path.parent).get_template(plantilla.path.name).render(contexto)


@lru_cache(maxsize=None)
def _environment(root: Path) -> Environment:
    return Environment(loader=FileSystemLoader(root), autoescape=select_autoescape(["html"]))
