"""El archivo de CVs: cada adaptación queda guardada.

Es lo que convierte la app en algo a lo que se vuelve. Cada vacante deja poso:
la base de hechos crece y el archivo de candidaturas crece con ella.

Se guarda la propuesta estructurada, no un PDF: así se puede reabrir, comparar,
duplicar para una vacante parecida y (en v2) cruzar con el feedback real de la
empresa. Un PDF sería un callejón sin salida.

De la propuesta solo se guardan **referencias por id** al perfil, igual que en
memoria. Corregir un bullet arregla todos los CV que lo usan. La excepción es
el texto del "Sobre mí", que se guarda ya compuesto porque es literalmente lo
que el usuario copió y pegó ese día.

Este módulo sabe de **carpetas, rutas y adjuntos**; qué forma tiene el fichero
por dentro es cosa de `serializacion`. Misma frontera que en `perfil/`.
"""
from __future__ import annotations

import dataclasses
import re
import shutil
import unicodedata
from datetime import date
from pathlib import Path

from flask_babel import gettext as _

from cv_adaptativo.archivo import serializacion
from cv_adaptativo.perfil import almacen
from cv_adaptativo.perfil import serializacion as serializacion_perfil
from cv_adaptativo.perfil.errores import ErrorPerfil
from cv_adaptativo.perfil.modelo import CVGuardado, EstadoCV
from cv_adaptativo.texto import normalizar

CARPETA_CVS = "cvs"
CARPETA_ADJUNTOS = "adjuntos"

EXTENSIONES = (".yaml", ".yml")

# Un id acaba siendo un nombre de fichero: sin esto, un `../` escribiría fuera
# de la carpeta del perfil.
_ID_VALIDO = re.compile(r"^[a-z0-9][a-z0-9._-]*$", re.IGNORECASE)

MAX_TROZO_ID = 40

_CABECERA = (
    "CV generado por CV Adaptativo. Se puede editar a mano.\n"
    "Las experiencias y skills son identificadores del perfil, no textos:\n"
    "si corriges el perfil, este CV se corrige con él."
)


# --------------------------------------------------------------------------
# Guardar y leer
# --------------------------------------------------------------------------


def guardar(raiz: Path, cv: CVGuardado) -> None:
    """Escribe `cvs/<id>.yaml`."""
    almacen.escribir_yaml(
        _ruta(raiz, cv.id), serializacion.de_cv(cv), comentario=_CABECERA
    )


def leer(ruta: Path) -> CVGuardado:
    """Carga un CV concreto. Lanza `ErrorPerfil` si el fichero está roto."""
    ruta = Path(ruta)
    try:
        texto = ruta.read_text(encoding="utf-8")
    except OSError as exc:
        raise ErrorPerfil(
            _("No se pudo leer «%(nombre)s»: %(detalle)s.", nombre=ruta.name, detalle=exc.strerror)
        ) from exc
    datos = serializacion_perfil.leer_datos(texto, ruta.name)
    return serializacion.a_cv(datos, ruta.stem)


def listar(raiz: Path) -> list[CVGuardado]:
    """Todos los CV archivados, del más reciente al más antiguo.

    Un fichero ilegible no puede tumbar la pantalla del archivo: se omite y el
    resto se enseña. Es distinto del perfil, donde saltarse una experiencia en
    silencio falsearía el CV — aquí lo que se pierde es una fila de una lista.
    """
    cvs: list[CVGuardado] = []
    for ruta in _ficheros(Path(raiz) / CARPETA_CVS):
        try:
            cvs.append(leer(ruta))
        except ErrorPerfil:
            continue
    return sorted(cvs, key=lambda cv: (cv.fecha, cv.id), reverse=True)


def buscar_por_empresa(raiz: Path, empresa: str) -> list[CVGuardado]:
    """CV previos de esa empresa, comparando sin distinguir mayúsculas ni acentos.

    Sostiene el aviso de reciclaje: antes de gastar una llamada al modelo, la
    app avisa de que ya existe un CV para esa empresa y ofrece reutilizarlo.
    Solo avisa — decide el usuario.
    """
    buscada = normalizar(empresa)
    if not buscada:
        return []
    return [cv for cv in listar(raiz) if normalizar(cv.empresa) == buscada]


def cambiar_estado(raiz: Path, id: str, estado: EstadoCV) -> None:
    cv = leer(_ruta(raiz, id))
    guardar(raiz, dataclasses.replace(cv, estado=EstadoCV(estado)))


def adjuntar(raiz: Path, id: str, archivo: Path) -> Path:
    """Copia el CV final del usuario a `cvs/adjuntos/` y devuelve su ruta.

    Cualquier formato vale (PDF, docx, imagen). No se valida ni se convierte:
    el diseño es cosa del usuario y de su herramienta. Se copia en vez de
    enlazar para que el perfil siga siendo autocontenido — al exportarlo en
    zip, el adjunto va dentro.
    """
    archivo = Path(archivo)
    if not archivo.is_file():
        raise ErrorPerfil(_("No existe el archivo «%(archivo)s».", archivo=archivo))

    cv = leer(_ruta(raiz, id))
    destino = _ruta_adjunto(raiz, id, archivo.suffix)
    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(archivo, destino)
    except OSError as exc:
        raise ErrorPerfil(
            _(
                "No se pudo guardar el adjunto «%(nombre)s»: %(detalle)s.",
                nombre=archivo.name,
                detalle=exc.strerror,
            )
        ) from exc

    guardar(raiz, dataclasses.replace(cv, adjunto=destino.name))
    return destino


# --------------------------------------------------------------------------
# Rutas e identificadores
# --------------------------------------------------------------------------


def nuevo_id(raiz: Path, fecha: date, empresa: str, puesto: str) -> str:
    """`2026-07-24_acme_data-engineer`, con sufijo si ese nombre ya está usado.

    Lleva la fecha delante para que la carpeta se lea sola en orden, y empresa
    y puesto porque el nombre del fichero es lo primero que ve quien abre la
    carpeta por fuera de la app.
    """
    partes = [fecha.isoformat(), _trozo(empresa) or "sin-empresa"]
    if puesto_slug := _trozo(puesto):
        partes.append(puesto_slug)

    base = "_".join(partes)
    candidato, siguiente = base, 2
    while _ruta(raiz, candidato).exists():
        candidato = f"{base}_{siguiente}"
        siguiente += 1
    return candidato


def _trozo(valor: str) -> str:
    """Un texto libre convertido en algo que valga como nombre de fichero."""
    descompuesto = unicodedata.normalize("NFKD", valor or "")
    sin_acentos = "".join(c for c in descompuesto if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", sin_acentos.lower()).strip("-")[:MAX_TROZO_ID]


def _ruta(raiz: Path, id: str) -> Path:
    return Path(raiz) / CARPETA_CVS / f"{_validar_id(id)}.yaml"


def _ruta_adjunto(raiz: Path, id: str, extension: str) -> Path:
    nombre = f"{_validar_id(id)}{extension.lower()}"
    return Path(raiz) / CARPETA_CVS / CARPETA_ADJUNTOS / nombre


def _validar_id(id: str) -> str:
    if not _ID_VALIDO.fullmatch(id or ""):
        raise ErrorPerfil(
            _("El identificador «%(id)s» no es válido para un CV guardado.", id=id)
        )
    return id


def _ficheros(carpeta: Path) -> list[Path]:
    """Los YAML de la carpeta, en orden estable. Si no existe, ninguno."""
    if not carpeta.is_dir():
        return []
    return sorted(
        ruta
        for ruta in carpeta.iterdir()
        if ruta.is_file() and ruta.suffix.lower() in EXTENSIONES
    )
