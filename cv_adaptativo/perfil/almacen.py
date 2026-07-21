"""Lectura y escritura del perfil en disco.

Los datos viven en la carpeta `perfil/` del usuario, en ficheros de texto
legibles y editables a mano. No hay base de datos ni nube: se puede copiar,
respaldar y llevar a otro ordenador.

    perfil/
      experiencia/*.yaml
      skills/*.yaml
      sobre-mi.yaml
      cvs/*.yaml
      cvs/adjuntos/

Este módulo sabe de **carpetas, rutas y respaldos**. Cómo se escribe un perfil
dentro de un fichero es cosa de `serializacion`, que es quien importa `yaml`:
aquí no aparece ni una vez, y esa es la frontera.

El `id` de una experiencia o de una skill es **el nombre del fichero sin
extensión**, nunca un campo de dentro: así no hay dos fuentes de la verdad que
se puedan contradecir.

Regla ante un fichero roto: **si no se puede leer, se avisa; si está incompleto,
se carga igual.** Un YAML mal formado lanza `ErrorPerfil` con un mensaje en
español que nombra el fichero — se le puede enseñar tal cual al usuario. Un
fichero bien formado pero al que le faltan campos se carga con lo que tenga, y
es `validacion.validar_perfil` quien lo cuenta: estar a medias es lo normal
mientras se edita, y perder una experiencia en silencio sería mucho peor que
un aviso.

CONTRATO — implementa el agente A. Las firmas de este módulo son fijas: el
motor, la web y el archivo ya dependen de ellas.
"""
from __future__ import annotations

import os
import re
import zipfile
from pathlib import Path
from typing import Any

from cv_adaptativo.perfil import serializacion
from cv_adaptativo.perfil.errores import ErrorPerfil
from cv_adaptativo.perfil.modelo import Experiencia, Perfil, Skill, SobreMi

# Se reexporta a propósito: quien guarda el perfil quiere capturar su error sin
# tener que saber que vive en otro módulo.
__all__ = [
    "ErrorPerfil",
    "anotar",
    "borrar_experiencia",
    "borrar_skill",
    "cargar_perfil",
    "escribir_yaml",
    "exportar_zip",
    "guardar_experiencia",
    "guardar_skill",
    "guardar_sobre_mi",
    "importar_zip",
    "ruta_experiencia",
    "ruta_skill",
    "ruta_sobre_mi",
]

CARPETA_EXPERIENCIA = "experiencia"
CARPETA_SKILLS = "skills"
CARPETA_CVS = "cvs"
FICHERO_SOBRE_MI = "sobre-mi.yaml"

EXTENSIONES = (".yaml", ".yml")

# Un id acaba siendo un nombre de fichero: si dejamos pasar barras o puntos
# suspensivos, guardar una experiencia escribiría fuera de la carpeta del perfil.
_ID_VALIDO = re.compile(r"^[a-z0-9][a-z0-9._-]*$", re.IGNORECASE)


# --------------------------------------------------------------------------
# Carga
# --------------------------------------------------------------------------


def cargar_perfil(raiz: Path) -> Perfil:
    """Carga el perfil completo. Una carpeta inexistente da un Perfil vacío,
    no un error: es el estado normal la primera vez que se abre la app."""
    raiz = Path(raiz)
    return Perfil(
        experiencias=[
            serializacion.a_experiencia(_leer(ruta), ruta.stem, ruta.name)
            for ruta in _ficheros(raiz / CARPETA_EXPERIENCIA)
        ],
        skills=[
            serializacion.a_skill(_leer(ruta), ruta.stem, ruta.name)
            for ruta in _ficheros(raiz / CARPETA_SKILLS)
        ],
        sobre_mi=_sobre_mi_desde(raiz / FICHERO_SOBRE_MI),
    )


def _sobre_mi_desde(ruta: Path) -> SobreMi | None:
    """Sin fichero no hay "Sobre mí"; es válido, y la validación ya lo dirá."""
    if not ruta.is_file():
        return None
    return serializacion.a_sobre_mi(_leer(ruta), ruta.name)


def _ficheros(carpeta: Path) -> list[Path]:
    """Los YAML de una carpeta, en orden estable. Si no existe, ninguno."""
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


def _leer(ruta: Path) -> dict[str, Any]:
    try:
        texto = ruta.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ErrorPerfil(
            f"«{ruta.name}» no está guardado en UTF-8, así que no se pueden leer "
            "sus acentos. Vuelve a guardarlo con codificación UTF-8."
        ) from exc
    except OSError as exc:
        raise ErrorPerfil(f"No se pudo leer «{ruta.name}»: {exc.strerror}.") from exc
    return serializacion.leer_datos(texto, ruta.name)


# --------------------------------------------------------------------------
# Escritura
# --------------------------------------------------------------------------


def guardar_experiencia(raiz: Path, experiencia: Experiencia) -> None:
    """Escribe (o sobrescribe) `experiencia/<id>.yaml`."""
    escribir_yaml(
        ruta_experiencia(raiz, experiencia.id), serializacion.de_experiencia(experiencia)
    )


def guardar_skill(raiz: Path, skill: Skill) -> None:
    """Escribe (o sobrescribe) `skills/<id>.yaml`."""
    escribir_yaml(ruta_skill(raiz, skill.id), serializacion.de_skill(skill))


def guardar_sobre_mi(raiz: Path, sobre_mi: SobreMi) -> None:
    escribir_yaml(ruta_sobre_mi(raiz), serializacion.de_sobre_mi(sobre_mi))


def borrar_experiencia(raiz: Path, id: str) -> None:
    """Borra el fichero. Solo se llama desde una acción explícita del usuario."""
    _borrar(ruta_experiencia(raiz, id))


def borrar_skill(raiz: Path, id: str) -> None:
    _borrar(ruta_skill(raiz, id))


def _borrar(ruta: Path) -> None:
    """Que ya no esté es justo el resultado buscado, así que no es un fallo."""
    try:
        ruta.unlink()
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise ErrorPerfil(f"No se pudo borrar «{ruta.name}»: {exc.strerror}.") from exc


def escribir_yaml(ruta: Path, datos: dict[str, Any], comentario: str = "") -> None:
    """Vuelca `datos` en `ruta`, creando la carpeta si hace falta.

    Se escribe primero a un temporal y luego se reemplaza de golpe: si la app
    muere a media escritura, el fichero anterior sigue entero. Son los datos
    del usuario y no hay copia en la nube de la que tirar.
    """
    ruta = Path(ruta)
    texto = serializacion.volcar_datos(datos)
    if comentario:
        texto = serializacion.comentario(comentario) + texto
    temporal = ruta.with_name(ruta.name + ".tmp")
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        temporal.write_text(texto, encoding="utf-8", newline="\n")
        os.replace(temporal, ruta)
    except OSError as exc:
        temporal.unlink(missing_ok=True)
        raise ErrorPerfil(f"No se pudo guardar «{ruta.name}»: {exc.strerror}.") from exc


def anotar(ruta: Path, texto: str) -> None:
    """Antepone un comentario a un YAML ya escrito.

    Sirve para no tirar notas que el usuario había dejado escritas y que el
    modelo de datos no representa. Ojo: es un comentario, así que la próxima
    vez que se guarde ese elemento desde la app se pierde.
    """
    ruta = Path(ruta)
    if not texto.strip():
        return
    try:
        ruta.write_text(
            serializacion.comentario(texto) + ruta.read_text(encoding="utf-8"),
            encoding="utf-8",
            newline="\n",
        )
    except OSError as exc:
        raise ErrorPerfil(f"No se pudo anotar «{ruta.name}»: {exc.strerror}.") from exc


# --------------------------------------------------------------------------
# Rutas
# --------------------------------------------------------------------------


def ruta_experiencia(raiz: Path, id: str) -> Path:
    return _ruta(Path(raiz) / CARPETA_EXPERIENCIA, id)


def ruta_skill(raiz: Path, id: str) -> Path:
    return _ruta(Path(raiz) / CARPETA_SKILLS, id)


def ruta_sobre_mi(raiz: Path) -> Path:
    return Path(raiz) / FICHERO_SOBRE_MI


def _ruta(carpeta: Path, id: str) -> Path:
    if not isinstance(id, str) or not _ID_VALIDO.match(id):
        raise ErrorPerfil(
            f"«{id}» no sirve como identificador. Usa solo letras sin acentos, "
            "números, guiones y puntos, por ejemplo «data-analyst-movilidad»."
        )
    return carpeta / f"{id}.yaml"


# --------------------------------------------------------------------------
# Respaldo y mudanza
# --------------------------------------------------------------------------


def exportar_zip(raiz: Path, destino: Path) -> Path:
    """Empaqueta todo el perfil (incluidos adjuntos) para respaldo o mudanza."""
    raiz, destino = Path(raiz), Path(destino)
    if not raiz.is_dir():
        raise ErrorPerfil(
            f"Todavía no hay ningún perfil que exportar: la carpeta «{raiz}» no existe."
        )
    if destino.suffix.lower() != ".zip":
        destino = destino.with_name(destino.name + ".zip")
    destino.parent.mkdir(parents=True, exist_ok=True)

    # Se arma en un temporal y se coloca de golpe, igual que al guardar un YAML:
    # un respaldo a medias que aparenta estar entero es peor que no tenerlo, y
    # solo se descubre el día que hace falta restaurarlo.
    temporal = destino.with_name(destino.name + ".tmp")
    # Si el respaldo se guarda dentro del propio perfil, no debe meterse a sí mismo.
    excluidos = {destino.resolve(), temporal.resolve()}
    try:
        with zipfile.ZipFile(temporal, "w", zipfile.ZIP_DEFLATED) as zip_:
            for ruta in sorted(raiz.rglob("*")):
                if ruta.is_file() and ruta.resolve() not in excluidos:
                    zip_.write(ruta, ruta.relative_to(raiz).as_posix())
        os.replace(temporal, destino)
    except OSError as exc:
        temporal.unlink(missing_ok=True)
        raise ErrorPerfil(f"No se pudo crear el respaldo: {exc.strerror}.") from exc
    return destino


def importar_zip(raiz: Path, origen: Path) -> None:
    """Restaura un perfil exportado. No mezcla: pide carpeta vacía o confirma
    sobrescritura desde la capa web, nunca aquí en silencio."""
    raiz, origen = Path(raiz), Path(origen)
    if not origen.is_file():
        raise ErrorPerfil(f"No se encuentra el fichero de respaldo «{origen}».")
    if raiz.is_dir() and any(raiz.iterdir()):
        raise ErrorPerfil(
            f"La carpeta «{raiz}» ya tiene un perfil dentro. Importa sobre una "
            "carpeta vacía, o borra el perfil actual antes, para no acabar con "
            "una mezcla de los dos."
        )
    try:
        with zipfile.ZipFile(origen) as zip_:
            for miembro in zip_.namelist():
                _comprobar_dentro(raiz, miembro, origen)
            raiz.mkdir(parents=True, exist_ok=True)
            zip_.extractall(raiz)
    except zipfile.BadZipFile as exc:
        raise ErrorPerfil(
            f"«{origen.name}» no es un respaldo válido: no se puede abrir como zip."
        ) from exc
    except OSError as exc:
        raise ErrorPerfil(f"No se pudo restaurar el respaldo: {exc.strerror}.") from exc


def _comprobar_dentro(raiz: Path, miembro: str, origen: Path) -> None:
    """Un zip puede traer rutas tipo `../../algo`; extraerlo tal cual escribiría
    fuera de la carpeta del perfil."""
    destino = (raiz / miembro).resolve()
    if not destino.is_relative_to(raiz.resolve()):
        raise ErrorPerfil(
            f"«{origen.name}» contiene rutas que salen de la carpeta del perfil "
            f"(«{miembro}»). No se ha importado nada."
        )
