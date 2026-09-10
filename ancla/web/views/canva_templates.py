"""Templates screen: a discreet link in the footer nav, outside the five
main screens — same pattern as Support.

The templates are design references (PDFs, exported manually from Canva
which cannot export an editable format), not profile data: they live in
`canva-templates/` rather than in `perfil/`, because they are not something
the user edits from the app nor something that varies between installations.
Shown inline, full-page — never a redirect out to canva.com, so the app
stays the only place a user needs to be to see them.

The gallery card preview is a PNG of the PDF's first page, not the PDF
embedded directly: `<embed>` follows Chrome/Acrobat's viewer conventions
(fragment params like `#toolbar=0`, an implicit margin some viewers add
around the page), which Firefox's own PDF viewer does not honour the same
way. A rendered image has no viewer chrome to disagree about. It is built
with pypdfium2 (bundled with the app, no system dependency — an earlier
version shelled out to `pdftoppm`, which a plain desktop install has no
reason to have installed) the first time it is requested, then cached as
`<id>.png` — regenerated only if the PDF is newer than the cached image, so
replacing a template's PDF by hand is enough to refresh its preview without
touching code. See `_preview_cache_dir` for where that cache lives, which
is not always next to the source PDF.
"""
from __future__ import annotations

from pathlib import Path

import pypdfium2 as pdfium
from flask import abort, render_template, send_file

from ancla.design import gallery
from ancla.design.gallery import DesignTemplate
from ancla.web import context
from ancla.web.blueprint import bp
from ancla.web.routes import is_packaged

_RESOLUCION_VISTA_PREVIA = 150


@bp.route("/plantillas")
def canva_templates():
    plantillas = gallery.list_templates(context.canva_templates_root())
    return render_template("canva_templates.html", canva_templates=plantillas, idioma=context.current_language())


@bp.route("/plantillas/<id>")
def canva_template_detail(id: str):
    plantilla = gallery.find_template(context.canva_templates_root(), id)
    if plantilla is None:
        abort(404)
    return render_template("canva_template_detail.html", plantilla=plantilla, idioma=context.current_language())


@bp.route("/plantillas/<id>/archivo")
def canva_template_file(id: str):
    plantilla = gallery.find_template(context.canva_templates_root(), id)
    if plantilla is None:
        abort(404)
    return send_file(plantilla.path)


@bp.route("/plantillas/<id>/vista-previa.png")
def canva_template_preview(id: str):
    plantilla = gallery.find_template(context.canva_templates_root(), id)
    if plantilla is None:
        abort(404)
    return send_file(_ensure_preview(plantilla), mimetype="image/png")


def _ensure_preview(plantilla: DesignTemplate) -> Path:
    """Renders the PDF's first page to a cached PNG, unless a cached one
    already exists and is not older than the PDF itself."""
    preview_path = _preview_cache_dir(plantilla.path) / f"{plantilla.path.stem}.png"
    if not preview_path.exists() or preview_path.stat().st_mtime < plantilla.path.stat().st_mtime:
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        pagina = pdfium.PdfDocument(str(plantilla.path))[0]
        pagina.render(scale=_RESOLUCION_VISTA_PREVIA / 72).to_pil().save(preview_path)
    return preview_path


def _preview_cache_dir(plantilla_path: Path) -> Path:
    """Next to the source PDF only when running from source. A packaged
    app's templates folder is read-only (the Flatpak's `/app`, the macOS
    bundle) or may be (`Program Files` on Windows), so the cache goes to
    the writable data folder instead.
    """
    if not is_packaged():
        return plantilla_path.parent
    return context.root().parent / "cache" / "plantillas"
