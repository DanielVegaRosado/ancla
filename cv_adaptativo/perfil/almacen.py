"""Lectura y escritura del perfil en disco (YAML).

Los datos viven en la carpeta `perfil/` del usuario, en ficheros de texto
legibles y editables a mano. No hay base de datos ni nube: se puede copiar,
respaldar y llevar a otro ordenador.

    perfil/
      experiencia/*.yaml
      skills/*.yaml
      sobre-mi.yaml
      cvs/*.yaml
      cvs/adjuntos/

El `id` de una experiencia o de una skill es **el nombre del fichero sin
extensión**, nunca un campo de dentro: así no hay dos fuentes de la verdad que
se puedan contradecir.

Al leer somos tolerantes y al escribir canónicos. Un campo bilingüe se puede
escribir de las dos formas, porque muchos títulos son idénticos en los dos
idiomas y obligar a repetirlos invita a que se desincronicen:

    titulo:                     titulo: Data Analyst
      es: Analista de datos       (el mismo texto en los dos idiomas)
      en: Data Analyst

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

import yaml

from cv_adaptativo.perfil.modelo import Bilingue, Experiencia, Perfil, Skill, SobreMi

CARPETA_EXPERIENCIA = "experiencia"
CARPETA_SKILLS = "skills"
CARPETA_CVS = "cvs"
FICHERO_SOBRE_MI = "sobre-mi.yaml"

EXTENSIONES = (".yaml", ".yml")

# Un id acaba siendo un nombre de fichero: si dejamos pasar barras o puntos
# suspensivos, guardar una experiencia escribiría fuera de la carpeta del perfil.
_ID_VALIDO = re.compile(r"^[a-z0-9][a-z0-9._-]*$", re.IGNORECASE)


class ErrorPerfil(Exception):
    """Fallo leyendo o escribiendo el perfil, con un mensaje para el usuario.

    El texto va en español y nombra el fichero: la capa web lo enseña tal cual,
    nunca una traza de Python.
    """


# --------------------------------------------------------------------------
# Carga
# --------------------------------------------------------------------------


def cargar_perfil(raiz: Path) -> Perfil:
    """Carga el perfil completo. Una carpeta inexistente da un Perfil vacío,
    no un error: es el estado normal la primera vez que se abre la app."""
    raiz = Path(raiz)
    return Perfil(
        experiencias=[
            _experiencia_desde(ruta) for ruta in _ficheros(raiz / CARPETA_EXPERIENCIA)
        ],
        skills=[_skill_desde(ruta) for ruta in _ficheros(raiz / CARPETA_SKILLS)],
        sobre_mi=_sobre_mi_desde(raiz / FICHERO_SOBRE_MI),
    )


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


def _experiencia_desde(ruta: Path) -> Experiencia:
    datos = _leer_yaml(ruta)
    return Experiencia(
        id=ruta.stem,
        titulo=_bilingue_texto(datos, "titulo", ruta),
        periodo=_bilingue_texto(datos, "periodo", ruta),
        bullets=_bilingue_lista(datos, "bullets", ruta),
        stack=_bilingue_texto(datos, "stack", ruta),
        keywords=_keywords(datos, ruta),
        estado=_texto(datos.get("estado")),
    )


def _skill_desde(ruta: Path) -> Skill:
    datos = _leer_yaml(ruta)
    return Skill(
        id=ruta.stem,
        nombre=_bilingue_texto(datos, "nombre", ruta),
        categoria=_texto(datos.get("categoria")),
        keywords=_keywords(datos, ruta),
    )


def _sobre_mi_desde(ruta: Path) -> SobreMi | None:
    """Sin fichero no hay "Sobre mí"; es válido, y la validación ya lo dirá."""
    if not ruta.is_file():
        return None
    datos = _leer_yaml(ruta)
    return SobreMi(plantilla=_bilingue_texto(datos, "plantilla", ruta))


# --------------------------------------------------------------------------
# Escritura
# --------------------------------------------------------------------------


def guardar_experiencia(raiz: Path, experiencia: Experiencia) -> None:
    """Escribe (o sobrescribe) `experiencia/<id>.yaml`."""
    escribir_yaml(
        ruta_experiencia(raiz, experiencia.id),
        {
            "titulo": _volcar_bilingue(experiencia.titulo),
            "periodo": _volcar_bilingue(experiencia.periodo),
            "estado": experiencia.estado,
            "bullets": {
                "es": [_texto(b) for b in experiencia.bullets["es"]],
                "en": [_texto(b) for b in experiencia.bullets["en"]],
            },
            "stack": _volcar_bilingue(experiencia.stack),
            "keywords": list(experiencia.keywords),
        },
    )


def guardar_skill(raiz: Path, skill: Skill) -> None:
    """Escribe (o sobrescribe) `skills/<id>.yaml`."""
    escribir_yaml(
        ruta_skill(raiz, skill.id),
        {
            "nombre": _volcar_bilingue(skill.nombre),
            "categoria": skill.categoria,
            "keywords": list(skill.keywords),
        },
    )


def guardar_sobre_mi(raiz: Path, sobre_mi: SobreMi) -> None:
    escribir_yaml(
        ruta_sobre_mi(raiz), {"plantilla": _volcar_bilingue(sobre_mi.plantilla)}
    )


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

    # Si el respaldo se guarda dentro del propio perfil, no debe meterse a sí mismo.
    salida = destino.resolve()
    try:
        with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as zip_:
            for ruta in sorted(raiz.rglob("*")):
                if ruta.is_file() and ruta.resolve() != salida:
                    zip_.write(ruta, ruta.relative_to(raiz).as_posix())
    except OSError as exc:
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


# --------------------------------------------------------------------------
# YAML: leer con tolerancia, escribir en canónico
# --------------------------------------------------------------------------


def escribir_yaml(ruta: Path, datos: dict[str, Any], comentario: str = "") -> None:
    """Vuelca `datos` en `ruta`, creando la carpeta si hace falta.

    Se escribe primero a un temporal y luego se reemplaza de golpe: si la app
    muere a media escritura, el fichero anterior sigue entero. Son los datos
    del usuario y no hay copia en la nube de la que tirar.
    """
    ruta = Path(ruta)
    texto = yaml.safe_dump(
        datos,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=4096,
    )
    if comentario:
        texto = _comentar(comentario) + texto
    temporal = ruta.with_name(ruta.name + ".tmp")
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        temporal.write_text(texto, encoding="utf-8", newline="\n")
        os.replace(temporal, ruta)
    except OSError as exc:
        temporal.unlink(missing_ok=True)
        raise ErrorPerfil(f"No se pudo guardar «{ruta.name}»: {exc.strerror}.") from exc


def anotar(ruta: Path, comentario: str) -> None:
    """Antepone un comentario `#` a un YAML ya escrito.

    Sirve para no tirar notas que el usuario había dejado escritas y que el
    modelo de datos no representa. Ojo: es un comentario, así que la próxima
    vez que se guarde ese elemento desde la app se pierde.
    """
    ruta = Path(ruta)
    if not comentario.strip():
        return
    try:
        ruta.write_text(
            _comentar(comentario) + ruta.read_text(encoding="utf-8"),
            encoding="utf-8",
            newline="\n",
        )
    except OSError as exc:
        raise ErrorPerfil(f"No se pudo anotar «{ruta.name}»: {exc.strerror}.") from exc


def _comentar(texto: str) -> str:
    return "".join(f"# {linea}\n" for linea in texto.splitlines())


def _leer_yaml(ruta: Path) -> dict[str, Any]:
    try:
        texto = ruta.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ErrorPerfil(
            f"«{ruta.name}» no está guardado en UTF-8, así que no se pueden leer "
            "sus acentos. Vuelve a guardarlo con codificación UTF-8."
        ) from exc
    except OSError as exc:
        raise ErrorPerfil(f"No se pudo leer «{ruta.name}»: {exc.strerror}.") from exc

    try:
        datos = yaml.safe_load(texto)
    except yaml.YAMLError as exc:
        raise ErrorPerfil(_error_de_formato(ruta, exc)) from exc

    if datos is None:
        return {}
    if not isinstance(datos, dict):
        raise ErrorPerfil(
            f"«{ruta.name}» no tiene el formato esperado: se esperaba una lista de "
            "campos como «titulo:» o «keywords:»."
        )
    return datos


def _error_de_formato(ruta: Path, exc: yaml.YAMLError) -> str:
    marca = getattr(exc, "problem_mark", None)
    donde = f" en la línea {marca.line + 1}" if marca is not None else ""
    return (
        f"«{ruta.name}» tiene un error de formato{donde}. Suele ser un espacio de "
        "más al principio de una línea, o un texto con «:» sin comillas."
    )


def _texto(valor: Any) -> str:
    """Convierte a texto lo que haya. Un `estado: no` lo lee YAML como False."""
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return "sí" if valor else "no"
    if isinstance(valor, str):
        return valor
    return str(valor)


def _bilingue_texto(datos: dict[str, Any], campo: str, ruta: Path) -> Bilingue[str]:
    valor = datos.get(campo)
    if valor is None:
        return Bilingue(es="", en="")
    if isinstance(valor, dict):
        return Bilingue(es=_texto(valor.get("es")), en=_texto(valor.get("en")))
    if isinstance(valor, (list, tuple)):
        raise ErrorPerfil(
            f"En «{ruta.name}», el campo «{campo}» es una lista y debería ser un "
            "texto, o «es:» y «en:» con un texto cada uno."
        )
    return Bilingue(es=_texto(valor), en=_texto(valor))


def _bilingue_lista(
    datos: dict[str, Any], campo: str, ruta: Path
) -> Bilingue[list[str]]:
    valor = datos.get(campo)
    if valor is None:
        return Bilingue(es=[], en=[])
    if isinstance(valor, dict):
        return Bilingue(
            es=_lista(valor.get("es"), campo, "es", ruta),
            en=_lista(valor.get("en"), campo, "en", ruta),
        )
    elementos = _lista(valor, campo, None, ruta)
    return Bilingue(es=list(elementos), en=list(elementos))


def _lista(valor: Any, campo: str, idioma: str | None, ruta: Path) -> list[str]:
    if valor is None:
        return []
    if isinstance(valor, (list, tuple)):
        return [_texto(elemento) for elemento in valor]
    sufijo = f" ({idioma})" if idioma else ""
    raise ErrorPerfil(
        f"En «{ruta.name}», el campo «{campo}»{sufijo} debería ser una lista: una "
        "línea por elemento, cada una empezando por «- »."
    )


def _keywords(datos: dict[str, Any], ruta: Path) -> list[str]:
    """Se admite la lista y también «a, b, c» en una sola línea: es como se
    escriben a mano, y separarlas nosotros cuesta menos que explicar el formato."""
    valor = datos.get("keywords")
    if isinstance(valor, str):
        return [parte.strip() for parte in valor.split(",") if parte.strip()]
    elementos = (_texto(x).strip() for x in _lista(valor, "keywords", None, ruta))
    return [palabra for palabra in elementos if palabra]


def _volcar_bilingue(dato: Bilingue[str]) -> dict[str, str]:
    return {"es": dato["es"], "en": dato["en"]}
