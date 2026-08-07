"""Presentation text shared across templates.

`CVStatus` (in `perfil/modelo.py`) holds domain values; their Spanish
labels are an interface detail and have no reason to live in the same
place as the model.
"""
from __future__ import annotations

from ancla.profile.model import CVStatus

ETIQUETAS_ESTADO = {
    CVStatus.DRAFT: "Borrador",
    CVStatus.SENT: "Enviado",
    CVStatus.INTERVIEW: "Entrevista",
    CVStatus.REJECTED: "Descartado",
    CVStatus.ACCEPTED: "Aceptado",
}
