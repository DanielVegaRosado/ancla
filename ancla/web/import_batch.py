"""The candidates from an imported CV currently being reviewed, before
deciding which ones to save into the profile.

Same reason as `borrador.py`: does not fit in a session cookie, so it lives
in a file next to the profile. Not part of `perfil/almacen.py`'s contract
— these are not verified facts yet, they are unconfirmed proposals — which
is why this lives in `web/` and not in `perfil/`.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ancla.profile.model import (
    LANGUAGES,
    AboutMe,
    Bilingual,
    Education,
    Experience,
    Language,
    Skill,
    SpokenLanguage,
)

NOMBRE_FICHERO = ".importacion.json"


@dataclass
class ImportBatch:
    """The candidates plus the languages they are written in.

    `written` starts as the single language the CV was imported in and gains
    the other one once the user asks for the translation. The review screen
    draws a column per language in it, so a field nobody has paid a call for
    is not shown as an empty box the user is meant to fill.
    """

    experiencias: list[Experience] = field(default_factory=list)
    skills: list[Skill] = field(default_factory=list)
    skills_personales: list[Skill] = field(default_factory=list)
    idiomas: list[SpokenLanguage] = field(default_factory=list)
    educacion: list[Education] = field(default_factory=list)
    # Contact and "About me": single values, not lists (see
    # `importer.ImportResult` for why). Empty means the analysis found
    # nothing — `has_contact()` and `sobre_mi is None` are what the review
    # screen checks before showing either card.
    contacto_nombre: str = ""
    contacto_titular: Bilingual[str] = field(default_factory=lambda: Bilingual(es="", en=""))
    contacto_lineas: list[str] = field(default_factory=list)
    sobre_mi: AboutMe | None = None
    avisos: list[str] = field(default_factory=list)
    written: list[Language] = field(default_factory=lambda: ["es"])
    # What the first call left uncut when the CV was too long for one call
    # (`importer.ImportResult.restante`). Lives here rather than in a file of
    # its own or the session cookie for the same reason as the rest of this
    # batch: it is plain CV text, potentially several KB, and it needs to
    # survive exactly as long as the review it belongs to — deleted the same
    # moment the batch is (`delete_import`, or overwritten by a fresh
    # `save_import`), with no separate cleanup to maintain.
    resto: str = ""

    def sections(self) -> list[list]:
        """Every candidate, whatever its category — for the operations that
        do not care which section an entry came from, such as translating
        the whole batch in one call."""
        return [
            self.experiencias, self.skills, self.skills_personales,
            self.idiomas, self.educacion,
        ]

    def has_contact(self) -> bool:
        return bool(
            self.contacto_nombre or self.contacto_lineas
            or self.contacto_titular["es"] or self.contacto_titular["en"]
        )

    def has_content(self) -> bool:
        """Whether there is anything at all to show on the review screen —
        the five list categories, or the two single-value ones."""
        return any(self.sections()) or self.has_contact() or self.sobre_mi is not None


def _path(root: Path) -> Path:
    return root / NOMBRE_FICHERO


def save_import(root: Path, importacion: ImportBatch) -> None:
    root.mkdir(parents=True, exist_ok=True)
    _path(root).write_text(
        json.dumps(asdict(importacion), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_import(root: Path) -> ImportBatch | None:
    ruta = _path(root)
    if not ruta.exists():
        return None
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        return ImportBatch(
            experiencias=[_to_experience(e) for e in datos["experiencias"]],
            skills=[_to_skill(s) for s in datos["skills"]],
            skills_personales=[_to_skill(s) for s in datos.get("skills_personales", [])],
            idiomas=[_to_language(i) for i in datos.get("idiomas", [])],
            educacion=[_to_education(e) for e in datos.get("educacion", [])],
            contacto_nombre=datos.get("contacto_nombre", ""),
            contacto_titular=Bilingual(**datos["contacto_titular"])
            if datos.get("contacto_titular")
            else Bilingual(es="", en=""),
            contacto_lineas=list(datos.get("contacto_lineas", [])),
            sobre_mi=_to_about_me(datos.get("sobre_mi")),
            avisos=list(datos.get("avisos", [])),
            # A batch saved before the import became single-language holds
            # both languages, and reading it as such is what keeps a review
            # already open from losing half its fields.
            written=[
                idioma for idioma in LANGUAGES
                if idioma in datos.get("written", list(LANGUAGES))
            ] or ["es"],
            resto=datos.get("resto", ""),
        )
    except (json.JSONDecodeError, OSError, KeyError, TypeError):
        return None


def delete_import(root: Path) -> None:
    _path(root).unlink(missing_ok=True)


def _to_experience(datos: dict) -> Experience:
    return Experience(
        id=datos["id"],
        title=Bilingual(**datos["title"]),
        period_start=datos["period_start"],
        period_end=datos["period_end"],
        bullets=Bilingual(**datos["bullets"]),
        stack=datos["stack"],
        keywords=list(datos.get("keywords", [])),
        status=datos.get("status", ""),
    )


def _to_skill(datos: dict) -> Skill:
    return Skill(
        id=datos["id"],
        name=Bilingual(**datos["name"]),
        category=Bilingual(**datos["category"]),
        keywords=list(datos.get("keywords", [])),
    )


def _to_education(datos: dict) -> Education:
    return Education(
        id=datos["id"],
        title=Bilingual(**datos["title"]),
        institution=datos["institution"],
        period_start=datos["period_start"],
        period_end=datos["period_end"],
    )


def _to_about_me(datos: dict | None) -> AboutMe | None:
    return AboutMe(template=Bilingual(**datos["template"])) if datos else None


def _to_language(datos: dict) -> SpokenLanguage:
    return SpokenLanguage(
        id=datos["id"],
        name=Bilingual(**datos["name"]),
        level=Bilingual(**datos["level"]),
        keywords=list(datos.get("keywords", [])),
    )
