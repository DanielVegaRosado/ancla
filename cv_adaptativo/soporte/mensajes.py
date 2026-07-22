"""Formulario de soporte.

Hereda el principio del soporte de MedAI: **el mensaje se guarda siempre en
local antes de intentar nada**, y un fallo al enviarlo jamás tira la petición
web. Lo que no se hereda son las credenciales SMTP. Allí el servidor es del
autor y la contraseña es privada; aquí la app corre en el ordenador de cada
usuario y **este repositorio es público**, así que meter una contraseña de
aplicación sería regalarla. Por eso las dos salidas no llevan secretos:

- una incidencia de GitHub ya rellenada (lo natural en open source: pública,
  buscable y gratis),
- o un `mailto:` que abre el correo del propio usuario.

**Nunca se adjuntan datos del perfil.** Solo diagnóstico: versión, sistema,
proveedor y el error. El CV de una persona no viaja a una incidencia pública
por querer contar que un botón no funciona.

El formulario distingue **problema** de **sugerencia**: es la misma tubería
por debajo (se guarda igual, se manda igual), pero la etiqueta cambia el
asunto que llega a GitHub o al correo — y, en la pantalla, dice explícitamente
que una idea o un "esto no me quedó claro" es tan bienvenido como un bug. Un
proyecto open source que solo parece escuchar quejas técnicas invita a menos
feedback, no a más.
"""
from __future__ import annotations

import platform
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, urlencode

from cv_adaptativo.perfil import almacen

VERSION = "0.1.0"

# TODO(Daniel): el nombre del repositorio ("cv-adaptativo") todavía no está
# decidido — actualiza esto cuando lo esté. El usuario ya está confirmado.
REPOSITORIO = "https://github.com/DanielVegaRosado/cv-adaptativo"
CORREO_SOPORTE = "dvegarosado@gmail.com"

CARPETA_SOPORTE = "soporte"

TIPOS = {
    "problema": "Problema",
    "sugerencia": "Sugerencia",
}
TIPO_POR_DEFECTO = "sugerencia"

# GitHub corta las URL largas y el navegador también: el cuerpo se recorta y se
# le dice al usuario que pegue el resto, en vez de perderlo en silencio.
MAX_CUERPO_URL = 4000


@dataclass(frozen=True)
class Diagnostico:
    """Lo que hace falta para reproducir un fallo, y nada más.

    Se construye con `recoger()`. Ningún campo sale del perfil del usuario:
    revisa eso antes de añadir uno nuevo.
    """

    version: str = VERSION
    sistema: str = ""
    python: str = ""
    proveedor: str = ""
    modelo: str = ""
    error: str = ""

    def como_texto(self) -> str:
        lineas = [
            f"- CV Adaptativo: {self.version}",
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


def recoger(proveedor: str = "", modelo: str = "", error: str = "") -> Diagnostico:
    """Datos del entorno. No toca el perfil ni los ajustes: la clave de API no
    entra aquí ni por descuido."""
    return Diagnostico(
        sistema=f"{platform.system()} {platform.release()}",
        python=platform.python_version() or sys.version.split()[0],
        proveedor=proveedor,
        modelo=modelo,
        error=error,
    )


def guardar_mensaje(
    raiz: Path,
    asunto: str,
    mensaje: str,
    diagnostico: Diagnostico | None = None,
    tipo: str = TIPO_POR_DEFECTO,
) -> Path:
    """Deja el mensaje en `perfil/soporte/` y devuelve su ruta.

    Es lo primero que se hace, antes de abrir el navegador o el correo: si el
    usuario cierra la ventana o no tiene conexión, lo que escribió sigue ahí.
    """
    diagnostico = diagnostico or recoger()
    momento = datetime.now()
    ruta = (
        Path(raiz)
        / CARPETA_SOPORTE
        / f"{momento.strftime('%Y-%m-%d_%H%M%S')}.yaml"
    )
    almacen.escribir_yaml(
        ruta,
        {
            "fecha": momento.isoformat(timespec="seconds"),
            "tipo": _tipo_valido(tipo),
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
        comentario=(
            "Mensaje de soporte guardado en local. No se ha enviado a ningún "
            "sitio salvo que tú abrieras la incidencia o el correo."
        ),
    )
    return ruta


def _tipo_valido(tipo: str) -> str:
    """Un tipo desconocido no es un error: se trata como el por defecto."""
    return tipo if tipo in TIPOS else TIPO_POR_DEFECTO


def _titulo(asunto: str, tipo: str) -> str:
    etiqueta = TIPOS[_tipo_valido(tipo)]
    return f"{etiqueta}: {asunto.strip()}" if asunto.strip() else etiqueta


def url_incidencia(
    asunto: str,
    mensaje: str,
    diagnostico: Diagnostico | None = None,
    tipo: str = TIPO_POR_DEFECTO,
) -> str:
    """URL de GitHub con la incidencia ya rellenada. El usuario decide si la envía."""
    parametros = {
        "title": _titulo(asunto, tipo),
        "body": _cuerpo(mensaje, diagnostico or recoger()),
    }
    return f"{REPOSITORIO}/issues/new?{urlencode(parametros)}"


def url_correo(
    asunto: str,
    mensaje: str,
    diagnostico: Diagnostico | None = None,
    tipo: str = TIPO_POR_DEFECTO,
) -> str:
    """`mailto:` para quien prefiera no abrir nada público."""
    cuerpo = _cuerpo(mensaje, diagnostico or recoger())
    return (
        f"mailto:{CORREO_SOPORTE}"
        f"?subject={quote(f'[CV Adaptativo] {_titulo(asunto, tipo)}')}&body={quote(cuerpo)}"
    )


def _cuerpo(mensaje: str, diagnostico: Diagnostico) -> str:
    cuerpo = f"{mensaje.strip()}\n\n---\n{diagnostico.como_texto()}"
    if len(cuerpo) <= MAX_CUERPO_URL:
        return cuerpo
    recorte = MAX_CUERPO_URL - len(diagnostico.como_texto()) - 80
    return (
        f"{mensaje.strip()[:max(recorte, 0)]}\n\n"
        "[...] El mensaje era muy largo y se ha recortado; pega aquí el resto.\n\n"
        f"---\n{diagnostico.como_texto()}"
    )
