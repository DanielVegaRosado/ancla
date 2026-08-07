"""Conversion from the old text format to the YAML profile.

Before the app existed, the base of facts was maintained by hand in `.txt`
files with uppercase fields:

    relevant_experience/<id>.txt   ID, TITULO_ES/EN, PERIODO_ES/EN, ESTADO,
                                   BULLETS_ES/EN, STACK_ES/EN, KEYWORDS
    technical-skills/<id>.txt      NOMBRE_ES/EN, CATEGORIA, KEYWORDS
    about-me-template.txt          the ES: and EN: blocks of the template

That worked because a single person maintained it and knew the format. It
is migrated to YAML for that very reason: as soon as anyone writes it from
the app, a homemade parser becomes a constant source of failures.

Two guarantees, in this order of importance:

1. **The source folder is never touched.** Nothing in it is modified, moved,
   or deleted. It is a person's real data, and it stays their good copy
   until they decide otherwise. This module only ever reads it.
2. **Never overwrites an already-migrated file** unless `sobrescribir=True`
   is requested. Whatever is skipped is counted in the report, never done
   silently.

Usage:

    python -m ancla.profile.migrator <source-folder> <profile-folder>
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from ancla.profile import store, validation
from ancla.profile.model import AboutMe, Bilingual, Experience, Skill

CARPETA_EXPERIENCIA_ORIGEN = "relevant_experience"
CARPETA_SKILLS_ORIGEN = "technical-skills"
FICHERO_SOBRE_MI_ORIGEN = "about-me-template.txt"

# A "KEY: value" line. Bullets start with "- ", so they never match, and
# neither does ordinary prose: the key is all uppercase and hugs the colon.
_CAMPO = re.compile(r"^([A-Z][A-Z0-9_]*):[ \t]?(.*)$")


@dataclass
class MigrationReport:
    """What got migrated, and what is worth a manual look afterwards."""

    experiencias: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    sobre_mi: bool = False
    omitidos: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lineas = [
            f"Experiencias migradas: {len(self.experiencias)}",
            f"Skills migradas: {len(self.skills)}",
            f"«Sobre mí»: {'sí' if self.sobre_mi else 'no encontrado'}",
        ]
        if self.omitidos:
            lineas.append("")
            lineas.append("Omitidos (ya existían, no se han tocado):")
            lineas += [f"  - {texto}" for texto in self.omitidos]
        if self.avisos:
            lineas.append("")
            lineas.append("Avisos:")
            lineas += [f"  - {texto}" for texto in self.avisos]
        return "\n".join(lineas)


def migrate(origen: Path, destino: Path, sobrescribir: bool = False) -> MigrationReport:
    """Converts the `.txt` folder at `origen` into a YAML profile at `destino`.

    `origen` is opened read-only. Returns the report; prints nothing.
    """
    origen, destino = Path(origen), Path(destino)
    informe = MigrationReport()
    if not origen.is_dir():
        informe.avisos.append(f"La carpeta de origen «{origen}» no existe.")
        return informe

    _migrate_experiences(origen, destino, sobrescribir, informe)
    _migrate_skills(origen, destino, sobrescribir, informe)
    _migrate_about_me(origen, destino, sobrescribir, informe)
    return informe


# --------------------------------------------------------------------------
# Experience
# --------------------------------------------------------------------------


def _migrate_experiences(
    origen: Path, destino: Path, sobrescribir: bool, informe: MigrationReport
) -> None:
    for fichero in _txt_files(origen / CARPETA_EXPERIENCIA_ORIGEN):
        campos = _read_fields(fichero)
        id_ = campos.get("ID", "").strip() or fichero.stem
        if id_ != fichero.stem:
            informe.avisos.append(
                f"«{fichero.name}» declara el id «{id_}», distinto del nombre del "
                f"fichero. Se ha guardado como «{id_}.yaml»."
            )

        experiencia = Experience(
            id=id_,
            title=_bilingual(campos, "TITULO"),
            period=_bilingual(campos, "PERIODO"),
            bullets=Bilingual(
                es=_as_list(campos, "BULLETS_ES"), en=_as_list(campos, "BULLETS_EN")
            ),
            stack=_bilingual(campos, "STACK"),
            keywords=_words(campos.get("KEYWORDS", "")),
            status=campos.get("ESTADO", "").strip(),
        )
        try:
            ruta = store.experience_path(destino, experiencia.id)
        except store.ProfileError as exc:
            # An id that does not work takes down that one item, not the
            # whole migration: the other dozen files are not at fault.
            informe.avisos.append(f"{fichero.name} → {exc}")
            continue
        if not _can_write(ruta, sobrescribir, informe, fichero):
            continue

        store.save_experience(destino, experiencia)
        _keep_note(ruta, campos, fichero, informe)
        informe.experiencias.append(experiencia.id)
        informe.avisos += _problems(validation.validate_experience(experiencia), fichero)


# --------------------------------------------------------------------------
# Skills
# --------------------------------------------------------------------------


def _migrate_skills(
    origen: Path, destino: Path, sobrescribir: bool, informe: MigrationReport
) -> None:
    for fichero in _txt_files(origen / CARPETA_SKILLS_ORIGEN):
        campos = _read_fields(fichero)
        skill = Skill(
            id=fichero.stem,
            name=_bilingual(campos, "NOMBRE"),
            category=campos.get("CATEGORIA", "").strip(),
            keywords=_words(campos.get("KEYWORDS", "")),
        )
        try:
            ruta = store.skill_path(destino, skill.id)
        except store.ProfileError as exc:
            informe.avisos.append(f"{fichero.name} → {exc}")
            continue
        if not _can_write(ruta, sobrescribir, informe, fichero):
            continue

        store.save_skill(destino, skill)
        _keep_note(ruta, campos, fichero, informe)
        informe.skills.append(skill.id)
        informe.avisos += _problems(validation.validate_skill(skill), fichero)


# --------------------------------------------------------------------------
# About me
# --------------------------------------------------------------------------


def _migrate_about_me(
    origen: Path, destino: Path, sobrescribir: bool, informe: MigrationReport
) -> None:
    fichero = origen / FICHERO_SOBRE_MI_ORIGEN
    if not fichero.is_file():
        informe.avisos.append(
            f"No se encontró «{FICHERO_SOBRE_MI_ORIGEN}»: el perfil se queda sin "
            "«Sobre mí» y habrá que escribirlo en la app."
        )
        return

    # The file opens with a paragraph of instructions that is not a field;
    # it is ignored on its own, because none of its lines look like "KEY: value".
    campos = _read_fields(fichero)
    sobre_mi = AboutMe(
        template=Bilingual(es=campos.get("ES", ""), en=campos.get("EN", ""))
    )
    ruta = store.about_me_path(destino)
    if not _can_write(ruta, sobrescribir, informe, fichero):
        return

    store.save_about_me(destino, sobre_mi)
    _keep_note(ruta, campos, fichero, informe)
    informe.sobre_mi = True
    informe.avisos += _problems(validation.validate_about_me(sobre_mi), fichero)


# --------------------------------------------------------------------------
# Shared pieces
# --------------------------------------------------------------------------


def _txt_files(carpeta: Path) -> list[Path]:
    if not carpeta.is_dir():
        return []
    return sorted(
        (ruta for ruta in carpeta.iterdir() if ruta.is_file() and ruta.suffix == ".txt"),
        key=lambda ruta: ruta.name,
    )


def _read_fields(fichero: Path) -> dict[str, str]:
    """Reads the old format into a field -> text dictionary.

    A field can come in three shapes, and all three show up in real files:
    on the same line (`ESTADO: actualidad`), as a list of lines starting
    with `- ` (the bullets), or as a paragraph beneath its key (the `ES:`
    and `EN:` blocks). A blank line closes whichever field is open.
    """
    campos: dict[str, str] = {}
    actual: str | None = None
    for linea in fichero.read_text(encoding="utf-8").splitlines():
        if not linea.strip():
            actual = None
            continue
        coincidencia = _CAMPO.match(linea)
        if coincidencia:
            actual = coincidencia.group(1)
            campos[actual] = coincidencia.group(2).strip()
            continue
        if actual is None:
            continue  # Loose text before the first field: not data.
        # Continuation: a multi-line note, a bullet, or the paragraph right
        # below its key.
        campos[actual] = f"{campos[actual]}\n{linea.strip()}".strip()
    return campos


def _bilingual(campos: dict[str, str], prefijo: str) -> Bilingual[str]:
    return Bilingual(
        es=campos.get(f"{prefijo}_ES", "").strip(),
        en=campos.get(f"{prefijo}_EN", "").strip(),
    )


def _as_list(campos: dict[str, str], campo: str) -> list[str]:
    """The `- ...` lines of a bullet block, exactly as the user wrote them.
    Nothing is rewritten or trimmed: that is the product's rule."""
    elementos: list[str] = []
    for cruda in campos.get(campo, "").splitlines():
        linea = cruda.strip()
        if not linea:
            continue
        if linea.startswith("- "):
            elementos.append(linea[2:].strip())
        elif elementos:
            # A long bullet split across two lines is still one bullet.
            elementos[-1] = f"{elementos[-1]} {linea}"
        else:
            elementos.append(linea)
    return elementos


def _words(bruto: str) -> list[str]:
    return [palabra.strip() for palabra in bruto.split(",") if palabra.strip()]


def _can_write(
    ruta: Path, sobrescribir: bool, informe: MigrationReport, fichero: Path
) -> bool:
    if ruta.exists() and not sobrescribir:
        informe.omitidos.append(f"{ruta.name} (venía de {fichero.name})")
        return False
    return True


def _keep_note(
    ruta: Path, campos: dict[str, str], fichero: Path, informe: MigrationReport
) -> None:
    """The old format allowed a free-form `NOTA:` field and the data model
    has nowhere to put it. It is saved as a YAML comment so it is not lost,
    and flagged: it is a decision pending from the user, not CV data."""
    nota = campos.get("NOTA", "").strip()
    if not nota:
        return
    store.annotate(ruta, f"NOTA heredada de {fichero.name}:\n{nota}")
    informe.avisos.append(
        f"«{fichero.name}» tenía una NOTA que el modelo no representa. Se ha "
        f"copiado como comentario al principio de «{ruta.name}», pero se perderá "
        "la próxima vez que guardes ese elemento desde la app."
    )


def _problems(problemas: list[str], fichero: Path) -> list[str]:
    return [f"{fichero.name} → {problema}" for problema in problemas]


# --------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------


def main(argumentos: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convierte el perfil en .txt del formato antiguo a YAML. "
        "La carpeta de origen no se modifica nunca."
    )
    parser.add_argument("origen", type=Path, help="carpeta con los .txt originales")
    parser.add_argument("destino", type=Path, help="carpeta del perfil (se crea)")
    parser.add_argument(
        "--sobrescribir",
        action="store_true",
        help="pisa los ficheros del perfil que ya existan (por defecto se saltan)",
    )
    opciones = parser.parse_args(argumentos)

    informe = migrate(opciones.origen, opciones.destino, opciones.sobrescribir)
    print(informe.summary())
    return 0 if (informe.experiencias or informe.skills or informe.sobre_mi) else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
