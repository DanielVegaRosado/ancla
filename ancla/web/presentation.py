"""Presentation text shared across templates.

`CVStatus` (in `perfil/modelo.py`) holds domain values; their translated
labels are an interface detail and have no reason to live in the same
place as the model.
"""
from __future__ import annotations

from datetime import date

from flask_babel import gettext as _

from ancla.profile.model import CVStatus, PERIOD_FINISHED, PERIOD_ONGOING


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


# The list stops at the current year: a period that has not happened yet is
# not something a CV states, and offering years into the 2030s only made the
# useful ones harder to reach. A degree still running is said with the
# "ongoing" marker, not with the year it is expected to end.
ANIOS_HACIA_ATRAS = 50


def years_for_period() -> list[str]:
    """The years offered in a period, most recent first: the entry someone
    is adding is almost always a recent one."""
    actual = date.today().year
    return [str(anio) for anio in range(actual, actual - ANIOS_HACIA_ATRAS, -1)]


def period_marker_labels() -> list[tuple[str, str]]:
    """The end-of-period markers as (stored value, label to show).

    The label is translated for the interface, while what gets stored is the
    marker itself — the word that reaches the CV is written later, in the
    language of the CV, not in whichever language the user happens to be
    reading the form in.
    """
    return [
        (PERIOD_ONGOING, _("Actualidad")),
        (PERIOD_FINISHED, _("Finalizado")),
    ]
