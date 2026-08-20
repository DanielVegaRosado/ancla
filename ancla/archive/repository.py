"""The CV archive: every adaptation is saved.

This is what turns the app into something people come back to. Every job
posting leaves a trace: the base of facts grows, and the archive of
applications grows with it.

The structured proposal is saved, not a PDF: that way it can be reopened,
compared, duplicated for a similar posting, and (in v2) cross-referenced
with real feedback from the company. A PDF would be a dead end.

Only **references by id** to the profile are saved from the proposal, same
as in memory. Fixing one bullet fixes every CV that uses it. The exception
is the "About me" text, which is saved already composed because it is
literally what the user copied and pasted that day.

This module knows about **folders, paths, and attachments**; the shape of
the file itself is `serializacion`'s job. Same boundary as in `perfil/`.
"""
from __future__ import annotations

import dataclasses
import re
import shutil
import unicodedata
from datetime import date
from pathlib import Path

from flask_babel import gettext as _
from werkzeug.utils import secure_filename

from ancla.archive import serialization
from ancla.profile import store
from ancla.profile import serialization as serializacion_perfil
from ancla.profile.errors import ProfileError
from ancla.profile.model import CVStatus, SavedCV
from ancla.text import normalize

CARPETA_CVS = "cvs"
CARPETA_ADJUNTOS = "attachments"

EXTENSIONES = (".yaml", ".yml")

# An id ends up as a file name: without this, a `../` would write outside
# the profile folder.
_ID_VALIDO = re.compile(r"^[a-z0-9][a-z0-9._-]*$", re.IGNORECASE)

MAX_TROZO_ID = 40

_CABECERA = (
    "CV generado por Ancla. Se puede editar a mano.\n"
    "Las experiencias y skills son identificadores del perfil, no textos:\n"
    "si corriges el perfil, este CV se corrige con él."
)


# --------------------------------------------------------------------------
# Save and read
# --------------------------------------------------------------------------


def save(root: Path, cv: SavedCV) -> None:
    """Writes `cvs/<id>.yaml`."""
    store.write_yaml(
        _path(root, cv.id), serialization.dump_cv(cv), comment=_CABECERA
    )


def read(ruta: Path) -> SavedCV:
    """Loads a specific CV. Raises `ErrorPerfil` if the file is broken."""
    ruta = Path(ruta)
    try:
        texto = ruta.read_text(encoding="utf-8")
    except OSError as exc:
        raise ProfileError(
            _("No se pudo leer «%(nombre)s»: %(detalle)s.", nombre=ruta.name, detalle=exc.strerror)
        ) from exc
    datos = serializacion_perfil.read_data(texto, ruta.name)
    return serialization.parse_cv(datos, ruta.stem)


def list_all(root: Path) -> list[SavedCV]:
    """Every archived CV, from the most to the least recent.

    An unreadable file must not bring down the archive screen: it is
    skipped and the rest is shown. Different from the profile, where
    silently skipping an experience would misrepresent the CV — here what
    is lost is one row of a list.
    """
    cvs: list[SavedCV] = []
    for ruta in _files(Path(root) / CARPETA_CVS):
        try:
            cvs.append(read(ruta))
        except ProfileError:
            continue
    return sorted(cvs, key=lambda cv: (cv.date, cv.id), reverse=True)


def find_by_company(root: Path, empresa: str) -> list[SavedCV]:
    """Previous CVs for that company, comparing case- and accent-insensitively.

    Backs the recycling prompt: before spending a call on the model, the
    app warns that a CV for that company already exists and offers to
    reuse it. It only warns — the user decides.
    """
    buscada = normalize(empresa)
    if not buscada:
        return []
    return [cv for cv in list_all(root) if normalize(cv.company) == buscada]


def change_status(root: Path, id: str, estado: CVStatus) -> None:
    cv = read(_path(root, id))
    save(root, dataclasses.replace(cv, status=CVStatus(estado)))


def attach(root: Path, id: str, archivo: Path, nombre_original: str) -> Path:
    """Copies the user's final CV into `cvs/attachments/` and adds it to
    the CV's `attachments` list — it never replaces a previous one, since
    the same posting can end up with several (different templates, a PDF
    alongside its .docx...).

    Any format works (PDF, docx, image). It is neither validated nor
    converted: the design is the user's and their tool's business. Copied
    rather than linked so the profile stays self-contained — when exported
    as a zip, the attachment goes along inside it. `nombre_original` is the
    name to show and store (`archivo` itself may be a throwaway temp path,
    e.g. the upload's temporary file on disk) — it is not read from
    `archivo.name` so the caller is free to stage the upload under any
    temporary name.
    """
    archivo = Path(archivo)
    if not archivo.is_file():
        raise ProfileError(_("No existe el archivo «%(archivo)s».", archivo=archivo))

    cv = read(_path(root, id))
    destino = _unique_attachment_path(root, id, nombre_original)
    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(archivo, destino)
    except OSError as exc:
        raise ProfileError(
            _(
                "No se pudo guardar el adjunto «%(nombre)s»: %(detalle)s.",
                nombre=nombre_original,
                detalle=exc.strerror,
            )
        ) from exc

    save(root, dataclasses.replace(cv, attachments=[*cv.attachments, destino.name]))
    return destino


def remove_attachment(root: Path, id: str, nombre_archivo: str) -> None:
    """Removes one attachment from a CV — the others stay. Missing from
    disk is not an error: the record is what matters, and this is also how
    a broken reference (file deleted by hand outside the app) heals itself."""
    cv = read(_path(root, id))
    if nombre_archivo not in cv.attachments:
        return
    (Path(root) / CARPETA_CVS / CARPETA_ADJUNTOS / nombre_archivo).unlink(missing_ok=True)
    save(root, dataclasses.replace(cv, attachments=[n for n in cv.attachments if n != nombre_archivo]))


def attachment_path(root: Path, cv: SavedCV, nombre_archivo: str) -> Path | None:
    """Where one of a CV's attachments actually lives, or `None` if
    `nombre_archivo` is not actually one of `cv.attachments` — checked
    against the CV's own record, not just built from the name, so this
    doubles as the guard against serving an arbitrary file from the
    shared `attachments/` folder."""
    if nombre_archivo not in cv.attachments:
        return None
    return Path(root) / CARPETA_CVS / CARPETA_ADJUNTOS / nombre_archivo


# --------------------------------------------------------------------------
# Paths and identifiers
# --------------------------------------------------------------------------


def new_id(root: Path, fecha: date, empresa: str, puesto: str) -> str:
    """`2026-07-24_acme_data-engineer`, with a suffix if that name is already taken.

    Carries the date up front so the folder reads itself in order, and the
    company and position because the file name is the first thing seen by
    whoever opens the folder outside the app.
    """
    partes = [fecha.isoformat(), _piece(empresa) or "sin-empresa"]
    if puesto_slug := _piece(puesto):
        partes.append(puesto_slug)

    base = "_".join(partes)
    candidato, siguiente = base, 2
    while _path(root, candidato).exists():
        candidato = f"{base}_{siguiente}"
        siguiente += 1
    return candidato


def _piece(valor: str) -> str:
    """Free text turned into something that works as a file name."""
    descompuesto = unicodedata.normalize("NFKD", valor or "")
    sin_acentos = "".join(c for c in descompuesto if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", sin_acentos.lower()).strip("-")[:MAX_TROZO_ID]


def _path(root: Path, id: str) -> Path:
    return Path(root) / CARPETA_CVS / f"{_validate_id(id)}.yaml"


def _unique_attachment_path(root: Path, id: str, nombre_original: str) -> Path:
    """Every CV's attachments share one flat folder, so the id goes first
    in the file name to keep two different CVs from colliding even if
    both attach a file called the same thing (e.g. two "cv.pdf"). Within
    the same CV, re-attaching a file with a name already used adds a
    counting suffix instead of overwriting it — `attach` never replaces an
    existing attachment.
    """
    carpeta = Path(root) / CARPETA_CVS / CARPETA_ADJUNTOS
    base = Path(secure_filename(nombre_original) or "adjunto")
    candidato = f"{_validate_id(id)}__{base.name}"
    siguiente = 2
    while (carpeta / candidato).exists():
        candidato = f"{_validate_id(id)}__{base.stem} ({siguiente}){base.suffix}"
        siguiente += 1
    return carpeta / candidato


def _validate_id(id: str) -> str:
    if not _ID_VALIDO.fullmatch(id or ""):
        raise ProfileError(
            _("El identificador «%(id)s» no es válido para un CV guardado.", id=id)
        )
    return id


def _files(carpeta: Path) -> list[Path]:
    """The YAML files in the folder, in stable order. None if it does not exist."""
    if not carpeta.is_dir():
        return []
    return sorted(
        ruta
        for ruta in carpeta.iterdir()
        if ruta.is_file() and ruta.suffix.lower() in EXTENSIONES
    )
