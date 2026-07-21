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
"""
from __future__ import annotations

import re
import shutil
import unicodedata
from datetime import date
from pathlib import Path
from typing import Any

from cv_adaptativo.perfil import almacen, serializacion
from cv_adaptativo.perfil.errores import ErrorPerfil
from cv_adaptativo.perfil.modelo import (
    CVGuardado,
    EstadoCV,
    ExperienciaSeleccionada,
    Propuesta,
    SeleccionSobreMi,
)
from cv_adaptativo.texto import normalizar

CARPETA_CVS = "cvs"
CARPETA_ADJUNTOS = "adjuntos"

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
    almacen.escribir_yaml(_ruta(raiz, cv.id), _volcar(cv), comentario=_CABECERA)


def listar(raiz: Path) -> list[CVGuardado]:
    """Todos los CV archivados, del más reciente al más antiguo.

    Un fichero ilegible no puede tumbar la pantalla del archivo: se omite y el
    resto se enseña. Es distinto del perfil, donde saltarse una experiencia en
    silencio falsearía el CV — aquí lo que se pierde es una fila de una lista.
    """
    carpeta = Path(raiz) / CARPETA_CVS
    if not carpeta.is_dir():
        return []

    cvs: list[CVGuardado] = []
    for ruta in sorted(carpeta.iterdir()):
        if not ruta.is_file() or ruta.suffix.lower() not in (".yaml", ".yml"):
            continue
        try:
            cvs.append(leer(ruta))
        except ErrorPerfil:
            continue
    return sorted(cvs, key=lambda cv: (cv.fecha, cv.id), reverse=True)


def leer(ruta: Path) -> CVGuardado:
    """Carga un CV concreto. Lanza `ErrorPerfil` si el fichero está roto."""
    ruta = Path(ruta)
    try:
        texto = ruta.read_text(encoding="utf-8")
    except OSError as exc:
        raise ErrorPerfil(f"No se pudo leer «{ruta.name}»: {exc.strerror}.") from exc
    return _cargar(serializacion.leer_datos(texto, ruta.name), ruta.stem)


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
    ruta = _ruta(raiz, id)
    cv = leer(ruta)
    guardar(raiz, _con(cv, estado=EstadoCV(estado)))


def adjuntar(raiz: Path, id: str, archivo: Path) -> Path:
    """Copia el CV final del usuario a `cvs/adjuntos/` y devuelve su ruta.

    Cualquier formato vale (PDF, docx, imagen). No se valida ni se convierte:
    el diseño es cosa del usuario y de su herramienta. Se copia en vez de
    enlazar para que el perfil siga siendo autocontenido — al exportarlo en
    zip, el adjunto va dentro.
    """
    archivo = Path(archivo)
    if not archivo.is_file():
        raise ErrorPerfil(f"No existe el archivo «{archivo}».")

    cv = leer(_ruta(raiz, id))
    destino = Path(raiz) / CARPETA_CVS / CARPETA_ADJUNTOS / f"{id}{archivo.suffix.lower()}"
    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(archivo, destino)
    except OSError as exc:
        raise ErrorPerfil(
            f"No se pudo guardar el adjunto «{archivo.name}»: {exc.strerror}."
        ) from exc

    guardar(raiz, _con(cv, adjunto=destino.name))
    return destino


# --------------------------------------------------------------------------
# Identificador
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
    candidato, n = base, 2
    while _ruta(raiz, candidato).exists():
        candidato = f"{base}_{n}"
        n += 1
    return candidato


def _trozo(valor: str) -> str:
    sin_acentos = "".join(
        c
        for c in unicodedata.normalize("NFKD", valor or "")
        if not unicodedata.combining(c)
    )
    return re.sub(r"[^a-z0-9]+", "-", sin_acentos.lower()).strip("-")[:40]


def _ruta(raiz: Path, id: str) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", id or "", re.IGNORECASE):
        # Un id acaba siendo un nombre de fichero: sin esto, un `../` escribiría
        # fuera de la carpeta del perfil.
        raise ErrorPerfil(f"El identificador «{id}» no es válido para un CV guardado.")
    return Path(raiz) / CARPETA_CVS / f"{id}.yaml"


def _con(cv: CVGuardado, **cambios: Any) -> CVGuardado:
    """`CVGuardado` es inmutable; esto devuelve una copia con lo cambiado."""
    campos = {
        "id": cv.id,
        "fecha": cv.fecha,
        "empresa": cv.empresa,
        "puesto": cv.puesto,
        "vacante": cv.vacante,
        "propuesta": cv.propuesta,
        "estado": cv.estado,
        "adjunto": cv.adjunto,
        "notas": cv.notas,
    }
    return CVGuardado(**{**campos, **cambios})


# --------------------------------------------------------------------------
# Serialización
# --------------------------------------------------------------------------


def _volcar(cv: CVGuardado) -> dict[str, Any]:
    return {
        "fecha": cv.fecha.isoformat(),
        "empresa": cv.empresa,
        "puesto": cv.puesto,
        "estado": cv.estado.value,
        "adjunto": cv.adjunto or "",
        "notas": cv.notas,
        "vacante": cv.vacante,
        "propuesta": {
            "idioma": cv.propuesta.idioma,
            "sobre_mi": {
                "grupo_a": list(cv.propuesta.sobre_mi.grupo_a),
                "grupo_b": list(cv.propuesta.sobre_mi.grupo_b),
                "texto": cv.propuesta.sobre_mi.texto,
                "motivo": cv.propuesta.sobre_mi.motivo,
            },
            "skills": list(cv.propuesta.skills),
            "motivo_skills": cv.propuesta.motivo_skills,
            "experiencias": [
                {"id": exp.id, "motivo": exp.motivo} for exp in cv.propuesta.experiencias
            ],
            "huecos": list(cv.propuesta.huecos),
        },
    }


def _cargar(datos: dict[str, Any], id: str) -> CVGuardado:
    propuesta = datos.get("propuesta") or {}
    if not isinstance(propuesta, dict):
        propuesta = {}
    sobre_mi = propuesta.get("sobre_mi") or {}
    if not isinstance(sobre_mi, dict):
        sobre_mi = {}

    return CVGuardado(
        id=id,
        fecha=_fecha(datos.get("fecha"), id),
        empresa=_texto(datos.get("empresa")),
        puesto=_texto(datos.get("puesto")),
        vacante=_texto(datos.get("vacante")),
        estado=_estado(datos.get("estado")),
        adjunto=_texto(datos.get("adjunto")) or None,
        notas=_texto(datos.get("notas")),
        propuesta=Propuesta(
            idioma="en" if _texto(propuesta.get("idioma")) == "en" else "es",
            sobre_mi=SeleccionSobreMi(
                grupo_a=_textos(sobre_mi.get("grupo_a")),
                grupo_b=_textos(sobre_mi.get("grupo_b")),
                texto=_texto(sobre_mi.get("texto")),
                motivo=_texto(sobre_mi.get("motivo")),
            ),
            skills=_textos(propuesta.get("skills")),
            motivo_skills=_texto(propuesta.get("motivo_skills")),
            experiencias=[
                ExperienciaSeleccionada(
                    id=_texto(elemento.get("id")), motivo=_texto(elemento.get("motivo"))
                )
                for elemento in propuesta.get("experiencias") or []
                if isinstance(elemento, dict) and _texto(elemento.get("id"))
            ],
            huecos=_textos(propuesta.get("huecos")),
        ),
    )


def _fecha(valor: Any, id: str) -> date:
    if isinstance(valor, date):
        return valor
    try:
        return date.fromisoformat(str(valor))
    except (TypeError, ValueError) as exc:
        raise ErrorPerfil(
            f"El CV «{id}» no tiene una fecha válida (esperaba algo como 2026-07-24)."
        ) from exc


def _estado(valor: Any) -> EstadoCV:
    """Un estado desconocido no invalida el CV: se trata como borrador."""
    try:
        return EstadoCV(_texto(valor))
    except ValueError:
        return EstadoCV.BORRADOR


def _texto(valor: Any) -> str:
    return valor.strip() if isinstance(valor, str) else ""


def _textos(valor: Any) -> list[str]:
    if not isinstance(valor, list):
        return []
    return [elemento.strip() for elemento in valor if isinstance(elemento, str) and elemento.strip()]
