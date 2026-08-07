"""The app's single `Blueprint`, in its own module.

Every screen registers its routes here (`ancla/web/vistas/*.py`) instead of
having one blueprint per screen: endpoint names (`ancla.ver_perfil`, etc.)
stay the same as always, so no template using `url_for` has to change.
Lives in its own file so views can import it without depending on each
other or creating a cycle with `ancla.web.views`.
"""
from __future__ import annotations

from flask import Blueprint

bp = Blueprint("ancla", __name__)
