"""Conversion between a `SavedCV` and the dictionary that goes into YAML.

Same boundary as in `perfil/serializacion`: `repositorio` knows about
folders, paths, and attachments; this module knows about the file's
**shape**. Keeping them apart lets the on-disk format change without
touching persistence, and vice versa.

Lenient when reading, canonical when writing: the file can be edited by
hand, so a missing field or one with the wrong type yields an empty value
instead of an exception. The one thing that is never forgiven is the date,
because it is what orders the whole archive.
"""
from __future__ import annotations

from datetime import date, time
from typing import Any

from flask_babel import gettext as _

from ancla.profile.errors import ProfileError
from ancla.profile.model import (
    CVStatus,
    Proposal,
    SavedCV,
    SelectedAboutMe,
    SelectedExperience,
)
from ancla.text import to_text, to_texts


def dump_cv(cv: SavedCV) -> dict[str, Any]:
    """The CV as a dictionary, ready to dump to YAML."""
    return {
        "date": cv.date.isoformat(),
        "time": cv.time.isoformat(timespec="seconds") if cv.time else "",
        "company": cv.company,
        "position": cv.position,
        "status": cv.status.value,
        "attachments": list(cv.attachments),
        "notes": cv.notes,
        "posting": cv.posting,
        "proposal": _dump_proposal(cv.proposal),
    }


def parse_cv(datos: dict[str, Any], id: str) -> SavedCV:
    """Rebuilds the CV. Raises `ErrorPerfil` if the date cannot be parsed."""
    return SavedCV(
        id=id,
        date=_parse_date(datos.get("date"), id),
        time=_parse_time(datos.get("time")),
        company=to_text(datos.get("company")),
        position=to_text(datos.get("position")),
        posting=to_text(datos.get("posting")),
        status=_parse_status(datos.get("status")),
        attachments=_parse_attachments(datos),
        notes=to_text(datos.get("notes")),
        proposal=_parse_proposal(_as_dict(datos.get("proposal"))),
    )


# --------------------------------------------------------------------------


def _dump_proposal(propuesta: Proposal) -> dict[str, Any]:
    return {
        "language": propuesta.language,
        "about_me": {
            "group_a": list(propuesta.about_me.group_a),
            "group_b": list(propuesta.about_me.group_b),
            "text": propuesta.about_me.text,
            "reason": propuesta.about_me.reason,
        },
        "skills": list(propuesta.skills),
        "skills_reason": propuesta.skills_reason,
        "experiences": [
            {"id": exp.id, "reason": exp.reason} for exp in propuesta.experiences
        ],
        "gaps": list(propuesta.gaps),
    }


def _parse_proposal(datos: dict[str, Any]) -> Proposal:
    sobre_mi = _as_dict(datos.get("about_me"))
    return Proposal(
        language="en" if to_text(datos.get("language")) == "en" else "es",
        about_me=SelectedAboutMe(
            group_a=to_texts(sobre_mi.get("group_a")),
            group_b=to_texts(sobre_mi.get("group_b")),
            text=to_text(sobre_mi.get("text")),
            reason=to_text(sobre_mi.get("reason")),
        ),
        skills=to_texts(datos.get("skills")),
        skills_reason=to_text(datos.get("skills_reason")),
        experiences=_parse_experiences(datos.get("experiences")),
        gaps=to_texts(datos.get("gaps")),
    )


def _parse_experiences(valor: Any) -> list[SelectedExperience]:
    """An experience with no id does not reference anything in the profile: dropped."""
    if not isinstance(valor, list):
        return []
    elementos = (_as_dict(elemento) for elemento in valor)
    return [
        SelectedExperience(id=id_exp, reason=to_text(datos.get("reason")))
        for datos in elementos
        if (id_exp := to_text(datos.get("id")))
    ]


def _parse_date(valor: Any, id: str) -> date:
    """PyYAML already returns a `date` when the date is unquoted; otherwise it is parsed."""
    if isinstance(valor, date):
        return valor
    try:
        return date.fromisoformat(str(valor))
    except (TypeError, ValueError) as exc:
        raise ProfileError(
            _(
                "El CV «%(id)s» no tiene una fecha válida (esperaba algo como 2026-07-24).",
                id=id,
            )
        ) from exc


def _parse_time(valor: Any) -> time | None:
    """No time is valid: CVs saved before this field existed do not have one,
    and that is not a broken file, just a piece of data that was not captured then."""
    if not isinstance(valor, time):
        if not isinstance(valor, str) or not valor.strip():
            return None
        try:
            return time.fromisoformat(valor.strip())
        except ValueError:
            return None
    return valor


def _parse_attachments(datos: dict[str, Any]) -> list[str]:
    """`attachments` (a list) replaced the old single `attachment` field —
    a CV saved before that change still has just the one, and reads fine
    as a one-item list until the CV is saved again."""
    lista = datos.get("attachments")
    if isinstance(lista, list):
        return [nombre for nombre in to_texts(lista) if nombre]
    antiguo = to_text(datos.get("attachment"))
    return [antiguo] if antiguo else []


def _parse_status(valor: Any) -> CVStatus:
    """An unknown status does not invalidate the CV: it is treated as a draft."""
    try:
        return CVStatus(to_text(valor))
    except ValueError:
        return CVStatus.DRAFT


def _as_dict(valor: Any) -> dict[str, Any]:
    return valor if isinstance(valor, dict) else {}
