"""Support form.

Inherits MedAI's support principle: **the message is always saved locally
before anything else is attempted**, and a failure to send it never brings
down the web request. What is not inherited is the SMTP credentials. There,
the server belongs to the author and the password is private; here the app
runs on each user's own computer and **this repository is public**, so
embedding an app password would be handing it out. That is why neither
output carries secrets:

- a pre-filled GitHub issue (the natural open-source route: public,
  searchable, and free),
- or a `mailto:` that opens the user's own email client.

**Profile data is never attached.** Only diagnostics: version, system,
provider, and the error. A person's CV does not travel to a public issue
just to report that a button does not work.

The form distinguishes a **problem** from a **suggestion**: it is the same
pipeline underneath (saved the same way, sent the same way), but the label
changes the subject line that reaches GitHub or the email — and, on screen,
it says explicitly that an idea or a "this wasn't clear to me" is as
welcome as a bug. An open-source project that only seems to listen to
technical complaints invites less feedback, not more.
"""
from __future__ import annotations

import platform
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, urlencode

from flask_babel import gettext as _

from ancla.profile import store

VERSION = "0.1.0"

REPOSITORIO = "https://github.com/DanielVegaRosado/ancla"
CORREO_SOPORTE = "dvegarosado@gmail.com"

CARPETA_SOPORTE = "support"

TIPOS = {
    "problema": "Problema",
    "sugerencia": "Sugerencia",
}
TIPO_POR_DEFECTO = "sugerencia"

# GitHub truncates long URLs, and so does the browser: the body is trimmed
# and the user is told to paste the rest, instead of silently losing it.
MAX_CUERPO_URL = 4000


@dataclass(frozen=True)
class Diagnostic:
    """What is needed to reproduce a failure, and nothing more.

    Built with `recoger()`. No field ever comes from the user's profile:
    check that before adding a new one.
    """

    version: str = VERSION
    sistema: str = ""
    python: str = ""
    proveedor: str = ""
    modelo: str = ""
    error: str = ""

    def as_text(self) -> str:
        lineas = [
            f"- Ancla: {self.version}",
            f"- Sistema: {self.sistema}",
            f"- Python: {self.python}",
        ]
        if self.proveedor:
            lineas.append(f"- Proveedor: {self.proveedor}")
        if self.modelo:
            lineas.append(f"- Modelo: {self.modelo}")
        if self.error:
            lineas.append(f"- Error: {self.error}")
        return "\n".join(lineas)


def collect(proveedor: str = "", modelo: str = "", error: str = "") -> Diagnostic:
    """Environment data. Never touches the profile or settings: the API key
    does not enter here even by accident."""
    return Diagnostic(
        sistema=f"{platform.system()} {platform.release()}",
        python=platform.python_version() or sys.version.split()[0],
        proveedor=proveedor,
        modelo=modelo,
        error=error,
    )


def save_message(
    root: Path,
    asunto: str,
    mensaje: str,
    diagnostico: Diagnostic | None = None,
    tipo: str = TIPO_POR_DEFECTO,
) -> Path:
    """Leaves the message in `profile/support/` and returns its path.

    Done first, before opening the browser or the email client: if the user
    closes the window or has no connection, what they wrote is still there.
    """
    diagnostico = diagnostico or collect()
    momento = datetime.now()
    ruta = (
        Path(root)
        / CARPETA_SOPORTE
        / f"{momento.strftime('%Y-%m-%d_%H%M%S')}.yaml"
    )
    store.write_yaml(
        ruta,
        {
            "fecha": momento.isoformat(timespec="seconds"),
            "tipo": _valid_type(tipo),
            "asunto": asunto.strip(),
            "mensaje": mensaje.strip(),
            "diagnostico": {
                "version": diagnostico.version,
                "sistema": diagnostico.sistema,
                "python": diagnostico.python,
                "proveedor": diagnostico.proveedor,
                "modelo": diagnostico.modelo,
                "error": diagnostico.error,
            },
        },
        comment=(
            "Mensaje de soporte guardado en local. No se ha enviado a ningún "
            "sitio salvo que tú abrieras la incidencia o el correo."
        ),
    )
    return ruta


def _valid_type(tipo: str) -> str:
    """An unknown type is not an error: it is treated as the default."""
    return tipo if tipo in TIPOS else TIPO_POR_DEFECTO


def _translated_label(tipo: str) -> str:
    # Explicit literals, not `_(variable)`: pybabel only extracts strings
    # passed directly to `_()`, not `TIPOS` values resolved at runtime —
    # see the same note in `web/vistas/soporte.py`.
    return _("Problema") if _valid_type(tipo) == "problema" else _("Sugerencia")


def _title(asunto: str, tipo: str) -> str:
    etiqueta = _translated_label(tipo)
    return f"{etiqueta}: {asunto.strip()}" if asunto.strip() else etiqueta


def issue_url(
    asunto: str,
    mensaje: str,
    diagnostico: Diagnostic | None = None,
    tipo: str = TIPO_POR_DEFECTO,
) -> str:
    """GitHub URL with the issue already filled in. The user decides whether to submit it."""
    parametros = {
        "title": _title(asunto, tipo),
        "body": _body(mensaje, diagnostico or collect()),
    }
    return f"{REPOSITORIO}/issues/new?{urlencode(parametros)}"


def email_url(
    asunto: str,
    mensaje: str,
    diagnostico: Diagnostic | None = None,
    tipo: str = TIPO_POR_DEFECTO,
) -> str:
    """`mailto:` for whoever would rather not open anything public."""
    cuerpo = _body(mensaje, diagnostico or collect())
    return (
        f"mailto:{CORREO_SOPORTE}"
        f"?subject={quote(f'[Ancla] {_title(asunto, tipo)}')}&body={quote(cuerpo)}"
    )


def _body(mensaje: str, diagnostico: Diagnostic) -> str:
    cuerpo = f"{mensaje.strip()}\n\n---\n{diagnostico.as_text()}"
    if len(cuerpo) <= MAX_CUERPO_URL:
        return cuerpo
    recorte = MAX_CUERPO_URL - len(diagnostico.as_text()) - 80
    return (
        f"{mensaje.strip()[:max(recorte, 0)]}\n\n"
        "[...] El mensaje era muy largo y se ha recortado; pega aquí el resto.\n\n"
        f"---\n{diagnostico.as_text()}"
    )
