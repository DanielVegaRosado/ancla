"""Presentation text shared across templates.

`CVStatus` (in `perfil/modelo.py`) holds domain values; their translated
labels are an interface detail and have no reason to live in the same
place as the model.
"""
from __future__ import annotations

from flask_babel import gettext as _

from ancla.profile.model import CVStatus


def etiquetas_estado() -> dict[CVStatus, str]:
    # A function, not a module-level dict: `_()` only resolves the right
    # language within a request, so this has to be called from inside one
    # (the context processor in `ancla/web/__init__.py` does that on every
    # render) — a dict built once at import time would freeze whichever
    # language happened to be active first.
    return {
        CVStatus.DRAFT: _("Borrador"),
        CVStatus.SENT: _("Enviado"),
        CVStatus.INTERVIEW: _("Entrevista"),
        CVStatus.REJECTED: _("Descartado"),
        CVStatus.ACCEPTED: _("Aceptado"),
    }
