"""Reading and writing the profile on disk.

The data lives in the user's `profile/` folder, in plain text files that are
readable and editable by hand. There is no database and no cloud: it can be
copied, backed up, and carried over to another computer.

    profile/
      experience/*.yaml
      skills/*.yaml
      personal-skills/*.yaml
      languages/*.yaml
      about-me.yaml
      cvs/*.yaml
      cvs/attachments/

`personal-skills/` and `languages/` are separate catalogs, in the same file
format as `skills/` (plus a `level:` for languages). `selection/engine.py`
never touches them: in the Proposal they are always shown in full, with no
AI selection — that is what guarantees they can never sneak into "About me"
nor among the technical skills.

This module only knows about **folders, paths, and backups**. How a profile
is written inside a file is `serializacion`'s job, which is the one that
imports `yaml`: it never appears here, and that is the boundary.

The `id` of an experience or a skill is **the file name without its
extension**, never a field inside it: that way there are never two sources
of truth that could contradict each other.

Rule for a broken file: **if it cannot be read, warn; if it is incomplete,
load it anyway.** Malformed YAML raises `ProfileError` with a message in
Spanish naming the file — it can be shown to the user as-is. A well-formed
file missing some fields loads with whatever it has, and it is
`validacion.validar_perfil` that reports it: being half-done is normal while
editing, and silently losing an experience would be far worse than a
warning.

CONTRACT — implemented by agent A. This module's signatures are fixed: the
engine, the web layer, and the archive already depend on them.
"""
from __future__ import annotations

import os
import re
import zipfile
from pathlib import Path
from typing import Any

from flask_babel import gettext as _

from ancla.profile import serialization, zip_safety
from ancla.profile.errors import ProfileError
from ancla.profile.model import AboutMe, Experience, Profile, Skill, SpokenLanguage

# A zip can claim a huge uncompressed size while staying small on disk (zip
# bomb). This bounds what a restored backup is allowed to expand to.
MAX_BYTES_DESCOMPRIMIDOS_ZIP = 200 * 1024 * 1024  # 200 MB

# Re-exported on purpose: whoever saves the profile wants to catch its error
# without needing to know it lives in another module.
__all__ = [
    "ErrorPerfil",
    "anotar",
    "borrar_experiencia",
    "borrar_idioma",
    "borrar_skill",
    "borrar_skill_personal",
    "borrar_todas_experiencias",
    "borrar_todas_skills",
    "borrar_todas_skills_personales",
    "borrar_todos_idiomas",
    "cargar_perfil",
    "escribir_yaml",
    "exportar_zip",
    "guardar_experiencia",
    "guardar_idioma",
    "guardar_skill",
    "guardar_skill_personal",
    "guardar_sobre_mi",
    "importar_zip",
    "ruta_experiencia",
    "ruta_idioma",
    "ruta_skill",
    "ruta_skill_personal",
    "ruta_sobre_mi",
]

CARPETA_EXPERIENCIA = "experience"
CARPETA_SKILLS = "skills"
CARPETA_SKILLS_PERSONALES = "personal-skills"
CARPETA_IDIOMAS = "languages"
CARPETA_CVS = "cvs"
FICHERO_SOBRE_MI = "about-me.yaml"

EXTENSIONES = (".yaml", ".yml")

# An id ends up as a file name: if we let slashes or ellipses through, saving
# an experience would write outside the profile folder.
_ID_VALIDO = re.compile(r"^[a-z0-9][a-z0-9._-]*$", re.IGNORECASE)


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------


def load_profile(root: Path) -> Profile:
    """Loads the full profile. A missing folder yields an empty Profile,
    not an error: that is the normal state the first time the app is opened."""
    root = Path(root)
    return Profile(
        experiences=[
            serialization.parse_experience(_read(ruta), ruta.stem, ruta.name)
            for ruta in _files(root / CARPETA_EXPERIENCIA)
        ],
        skills=[
            serialization.parse_skill(_read(ruta), ruta.stem, ruta.name)
            for ruta in _files(root / CARPETA_SKILLS)
        ],
        personal_skills=[
            serialization.parse_skill(_read(ruta), ruta.stem, ruta.name)
            for ruta in _files(root / CARPETA_SKILLS_PERSONALES)
        ],
        languages=[
            serialization.parse_language(_read(ruta), ruta.stem, ruta.name)
            for ruta in _files(root / CARPETA_IDIOMAS)
        ],
        about_me=_about_me_from(root / FICHERO_SOBRE_MI),
    )


def _about_me_from(ruta: Path) -> AboutMe | None:
    """No file means no "About me"; that is valid, and validation will say so."""
    if not ruta.is_file():
        return None
    return serialization.parse_about_me(_read(ruta), ruta.name)


def _files(carpeta: Path) -> list[Path]:
    """The YAML files in a folder, in stable order. None if it does not exist."""
    if not carpeta.is_dir():
        return []
    return sorted(
        (
            ruta
            for ruta in carpeta.iterdir()
            if ruta.is_file() and ruta.suffix.lower() in EXTENSIONES
        ),
        key=lambda ruta: ruta.name,
    )


def _read(ruta: Path) -> dict[str, Any]:
    try:
        texto = ruta.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ProfileError(
            _(
                "«%(nombre)s» no está guardado en UTF-8, así que no se pueden leer "
                "sus acentos. Vuelve a guardarlo con codificación UTF-8.",
                nombre=ruta.name,
            )
        ) from exc
    except OSError as exc:
        raise ProfileError(
            _("No se pudo leer «%(nombre)s»: %(detalle)s.", nombre=ruta.name, detalle=exc.strerror)
        ) from exc
    return serialization.read_data(texto, ruta.name)


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------


def save_experience(root: Path, experiencia: Experience) -> None:
    """Writes (or overwrites) `experience/<id>.yaml`."""
    write_yaml(
        experience_path(root, experiencia.id), serialization.dump_experience(experiencia)
    )


def save_skill(root: Path, skill: Skill) -> None:
    """Writes (or overwrites) `skills/<id>.yaml`."""
    write_yaml(skill_path(root, skill.id), serialization.dump_skill(skill))


def save_personal_skill(root: Path, skill: Skill) -> None:
    """Writes (or overwrites) `personal-skills/<id>.yaml`.

    Same `Skill` type as the technical ones: what separates them is the
    folder they live in, not the shape of the data.
    """
    write_yaml(personal_skill_path(root, skill.id), serialization.dump_skill(skill))


def save_language(root: Path, idioma: SpokenLanguage) -> None:
    """Writes (or overwrites) `languages/<id>.yaml`."""
    write_yaml(language_path(root, idioma.id), serialization.dump_language(idioma))


def save_about_me(root: Path, sobre_mi: AboutMe) -> None:
    write_yaml(about_me_path(root), serialization.dump_about_me(sobre_mi))


def delete_experience(root: Path, id: str) -> None:
    """Deletes the file. Only ever called from an explicit user action."""
    _delete(experience_path(root, id))


def delete_skill(root: Path, id: str) -> None:
    _delete(skill_path(root, id))


def delete_personal_skill(root: Path, id: str) -> None:
    _delete(personal_skill_path(root, id))


def delete_language(root: Path, id: str) -> None:
    _delete(language_path(root, id))


def delete_all_experiences(root: Path) -> None:
    """Deletes every file in `experience/`. A whole-section action, not a
    one-by-one loop — same "not present is not a failure" logic."""
    _delete_folder(Path(root) / CARPETA_EXPERIENCIA)


def delete_all_skills(root: Path) -> None:
    _delete_folder(Path(root) / CARPETA_SKILLS)


def delete_all_personal_skills(root: Path) -> None:
    _delete_folder(Path(root) / CARPETA_SKILLS_PERSONALES)


def delete_all_languages(root: Path) -> None:
    _delete_folder(Path(root) / CARPETA_IDIOMAS)


def _delete_folder(carpeta: Path) -> None:
    for ruta in _files(carpeta):
        _delete(ruta)


def _delete(ruta: Path) -> None:
    """No longer being there is exactly the intended outcome, so it is not a failure."""
    try:
        ruta.unlink()
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise ProfileError(
            _("No se pudo borrar «%(nombre)s»: %(detalle)s.", nombre=ruta.name, detalle=exc.strerror)
        ) from exc


def write_yaml(ruta: Path, datos: dict[str, Any], comment: str = "") -> None:
    """Dumps `datos` into `ruta`, creating the folder if needed.

    Written to a temp file first, then swapped in atomically: if the app
    dies mid-write, the previous file stays intact. This is the user's data
    and there is no cloud copy to fall back on.
    """
    ruta = Path(ruta)
    texto = serialization.dump_data(datos)
    if comment:
        texto = serialization.comment(comment) + texto
    temporal = ruta.with_name(ruta.name + ".tmp")
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        temporal.write_text(texto, encoding="utf-8", newline="\n")
        os.replace(temporal, ruta)
    except OSError as exc:
        temporal.unlink(missing_ok=True)
        raise ProfileError(
            _("No se pudo guardar «%(nombre)s»: %(detalle)s.", nombre=ruta.name, detalle=exc.strerror)
        ) from exc


def annotate(ruta: Path, texto: str) -> None:
    """Prepends a comment to an already-written YAML file.

    Used to avoid throwing away notes the user had written that the data
    model does not represent. Careful: it is a comment, so it is lost the
    next time that item is saved from the app.
    """
    ruta = Path(ruta)
    if not texto.strip():
        return
    try:
        ruta.write_text(
            serialization.comment(texto) + ruta.read_text(encoding="utf-8"),
            encoding="utf-8",
            newline="\n",
        )
    except OSError as exc:
        raise ProfileError(
            _("No se pudo anotar «%(nombre)s»: %(detalle)s.", nombre=ruta.name, detalle=exc.strerror)
        ) from exc


# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------


def experience_path(root: Path, id: str) -> Path:
    return _path(Path(root) / CARPETA_EXPERIENCIA, id)


def skill_path(root: Path, id: str) -> Path:
    return _path(Path(root) / CARPETA_SKILLS, id)


def personal_skill_path(root: Path, id: str) -> Path:
    return _path(Path(root) / CARPETA_SKILLS_PERSONALES, id)


def language_path(root: Path, id: str) -> Path:
    return _path(Path(root) / CARPETA_IDIOMAS, id)


def about_me_path(root: Path) -> Path:
    return Path(root) / FICHERO_SOBRE_MI


def _path(carpeta: Path, id: str) -> Path:
    if not isinstance(id, str) or not _ID_VALIDO.match(id):
        raise ProfileError(
            _(
                "«%(id)s» no sirve como identificador. Usa solo letras sin acentos, "
                "números, guiones y puntos, por ejemplo «data-analyst-movilidad».",
                id=id,
            )
        )
    return carpeta / f"{id}.yaml"


# --------------------------------------------------------------------------
# Backup and migration
# --------------------------------------------------------------------------


def export_zip(root: Path, destino: Path) -> Path:
    """Packages the whole profile (attachments included) for backup or migration."""
    root, destino = Path(root), Path(destino)
    if not root.is_dir():
        raise ProfileError(
            _(
                "Todavía no hay ningún perfil que exportar: la carpeta «%(raiz)s» no existe.",
                raiz=root,
            )
        )
    if destino.suffix.lower() != ".zip":
        destino = destino.with_name(destino.name + ".zip")
    destino.parent.mkdir(parents=True, exist_ok=True)

    # Built in a temp file and swapped in atomically, same as when saving a
    # YAML file: a half-written backup that looks complete is worse than no
    # backup at all, and it is only ever discovered the day it is needed.
    temporal = destino.with_name(destino.name + ".tmp")
    # If the backup is saved inside the profile itself, it must not include itself.
    excluidos = {destino.resolve(), temporal.resolve()}
    try:
        with zipfile.ZipFile(temporal, "w", zipfile.ZIP_DEFLATED) as zip_:
            for ruta in sorted(root.rglob("*")):
                if ruta.is_file() and ruta.resolve() not in excluidos:
                    zip_.write(ruta, ruta.relative_to(root).as_posix())
        os.replace(temporal, destino)
    except OSError as exc:
        temporal.unlink(missing_ok=True)
        raise ProfileError(
            _("No se pudo crear el respaldo: %(detalle)s.", detalle=exc.strerror)
        ) from exc
    return destino


def import_zip(root: Path, origen: Path) -> None:
    """Restores an exported profile. It never merges: it requires an empty
    folder or an explicit overwrite confirmation from the web layer, never
    silently here."""
    root, origen = Path(root), Path(origen)
    if not origen.is_file():
        raise ProfileError(
            _("No se encuentra el fichero de respaldo «%(origen)s».", origen=origen)
        )
    if root.is_dir() and any(root.iterdir()):
        raise ProfileError(
            _(
                "La carpeta «%(raiz)s» ya tiene un perfil dentro. Importa sobre una "
                "carpeta vacía, o borra el perfil actual antes, para no acabar con "
                "una mezcla de los dos.",
                raiz=root,
            )
        )
    try:
        with zipfile.ZipFile(origen) as zip_:
            for miembro in zip_.namelist():
                _check_within(root, miembro, origen)
            tamano_descomprimido = zip_safety.uncompressed_size(zip_)
            if tamano_descomprimido > MAX_BYTES_DESCOMPRIMIDOS_ZIP:
                raise ProfileError(
                    _(
                        "«%(nombre)s» ocupa demasiado al descomprimirlo. No se ha "
                        "importado nada.",
                        nombre=origen.name,
                    )
                )
            root.mkdir(parents=True, exist_ok=True)
            zip_.extractall(root)
    except zipfile.BadZipFile as exc:
        raise ProfileError(
            _(
                "«%(nombre)s» no es un respaldo válido: no se puede abrir como zip.",
                nombre=origen.name,
            )
        ) from exc
    except OSError as exc:
        raise ProfileError(
            _("No se pudo restaurar el respaldo: %(detalle)s.", detalle=exc.strerror)
        ) from exc


def _check_within(root: Path, miembro: str, origen: Path) -> None:
    """A zip can carry paths like `../../something`; extracting it as-is
    would write outside the profile folder."""
    destino = (root / miembro).resolve()
    if not destino.is_relative_to(root.resolve()):
        raise ProfileError(
            _(
                "«%(nombre)s» contiene rutas que salen de la carpeta del perfil "
                "(«%(miembro)s»). No se ha importado nada.",
                nombre=origen.name,
                miembro=miembro,
            )
        )
