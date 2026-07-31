"""Traducción entre el formato YAML y el modelo de datos.

Aquí vive **todo** lo que sabe cómo se escribe un perfil en un fichero; `almacen`
solo sabe de carpetas, rutas y respaldos y no importa `yaml` por ningún lado. La
frontera es a propósito: estas funciones son puras (texto y diccionarios entran,
objetos del modelo salen) y por eso se pueden probar sin tocar el disco, que es
donde estaban antes escondidas las decisiones difíciles.

Al leer somos tolerantes y al escribir canónicos. Un campo bilingüe se puede
escribir de las dos formas, porque muchos títulos son idénticos en los dos
idiomas y obligar a repetirlos invita a que se desincronicen:

    titulo:                     titulo: Data Analyst
      es: Analista de datos       (el mismo texto en los dos idiomas)
      en: Data Analyst

`origen` es el nombre del fichero del que salieron los datos. Se pasa solo para
poder nombrarlo en los mensajes de error: sin él, "falta el título" no le dice
al usuario qué fichero abrir.
"""
from __future__ import annotations

from typing import Any

import yaml
from flask_babel import gettext as _

from cv_adaptativo.perfil.errores import ErrorPerfil
from cv_adaptativo.perfil.modelo import Bilingue, Experiencia, IdiomaHablado, Skill, SobreMi


# --------------------------------------------------------------------------
# Texto YAML <-> diccionario
# --------------------------------------------------------------------------


def leer_datos(texto: str, origen: str) -> dict[str, Any]:
    """Interpreta el texto de un fichero. Vacío da un diccionario vacío."""
    try:
        datos = yaml.safe_load(texto)
    except yaml.YAMLError as exc:
        raise ErrorPerfil(_error_de_formato(origen, exc)) from exc

    if datos is None:
        return {}
    if not isinstance(datos, dict):
        raise ErrorPerfil(
            _(
                "«%(origen)s» no tiene el formato esperado: se esperaba una lista de "
                "campos como «titulo:» o «keywords:».",
                origen=origen,
            )
        )
    return datos


def volcar_datos(datos: dict[str, Any]) -> str:
    """La forma canónica: campos en su orden, acentos escritos y sin recortar
    líneas largas (una línea partida por nosotros confunde al editarla a mano)."""
    return yaml.safe_dump(
        datos,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=4096,
    )


def comentario(texto: str) -> str:
    """Convierte un texto suelto en líneas de comentario YAML."""
    return "".join(f"# {linea}\n" for linea in texto.splitlines())


def _error_de_formato(origen: str, exc: yaml.YAMLError) -> str:
    marca = getattr(exc, "problem_mark", None)
    if marca is not None:
        return _(
            "«%(origen)s» tiene un error de formato en la línea %(linea)s. Suele ser "
            "un espacio de más al principio de una línea, o un texto con «:» sin "
            "comillas.",
            origen=origen,
            linea=marca.line + 1,
        )
    return _(
        "«%(origen)s» tiene un error de formato. Suele ser un espacio de "
        "más al principio de una línea, o un texto con «:» sin comillas.",
        origen=origen,
    )


# --------------------------------------------------------------------------
# Diccionario -> modelo
# --------------------------------------------------------------------------


def a_experiencia(datos: dict[str, Any], id: str, origen: str) -> Experiencia:
    return Experiencia(
        id=id,
        titulo=_bilingue_texto(datos, "titulo", origen),
        periodo=_bilingue_texto(datos, "periodo", origen),
        bullets=_bilingue_lista(datos, "bullets", origen),
        stack=_bilingue_texto(datos, "stack", origen),
        keywords=_keywords(datos, origen),
        estado=_texto(datos.get("estado")),
    )


def a_skill(datos: dict[str, Any], id: str, origen: str) -> Skill:
    return Skill(
        id=id,
        nombre=_bilingue_texto(datos, "nombre", origen),
        categoria=_texto(datos.get("categoria")),
        keywords=_keywords(datos, origen),
    )


def a_idioma(datos: dict[str, Any], id: str, origen: str) -> IdiomaHablado:
    return IdiomaHablado(
        id=id,
        nombre=_bilingue_texto(datos, "nombre", origen),
        nivel=_bilingue_texto(datos, "nivel", origen),
        keywords=_keywords(datos, origen),
    )


def a_sobre_mi(datos: dict[str, Any], origen: str) -> SobreMi:
    return SobreMi(plantilla=_bilingue_texto(datos, "plantilla", origen))


# --------------------------------------------------------------------------
# Modelo -> diccionario
# --------------------------------------------------------------------------


def de_experiencia(experiencia: Experiencia) -> dict[str, Any]:
    return {
        "titulo": _volcar_bilingue(experiencia.titulo),
        "periodo": _volcar_bilingue(experiencia.periodo),
        "estado": experiencia.estado,
        "bullets": {
            "es": [_texto(b) for b in experiencia.bullets["es"]],
            "en": [_texto(b) for b in experiencia.bullets["en"]],
        },
        "stack": _volcar_bilingue(experiencia.stack),
        "keywords": list(experiencia.keywords),
    }


def de_skill(skill: Skill) -> dict[str, Any]:
    return {
        "nombre": _volcar_bilingue(skill.nombre),
        "categoria": skill.categoria,
        "keywords": list(skill.keywords),
    }


def de_idioma(idioma: IdiomaHablado) -> dict[str, Any]:
    return {
        "nombre": _volcar_bilingue(idioma.nombre),
        "nivel": _volcar_bilingue(idioma.nivel),
        "keywords": list(idioma.keywords),
    }


def de_sobre_mi(sobre_mi: SobreMi) -> dict[str, Any]:
    return {"plantilla": _volcar_bilingue(sobre_mi.plantilla)}


# --------------------------------------------------------------------------
# Piezas comunes
# --------------------------------------------------------------------------


def _texto(valor: Any) -> str:
    """Convierte a texto lo que haya. Un `estado: no` lo lee YAML como False."""
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return "sí" if valor else "no"
    if isinstance(valor, str):
        return valor
    return str(valor)


def _bilingue_texto(datos: dict[str, Any], campo: str, origen: str) -> Bilingue[str]:
    valor = datos.get(campo)
    if valor is None:
        return Bilingue(es="", en="")
    if isinstance(valor, dict):
        return Bilingue(es=_texto(valor.get("es")), en=_texto(valor.get("en")))
    if isinstance(valor, (list, tuple)):
        raise ErrorPerfil(
            _(
                "En «%(origen)s», el campo «%(campo)s» es una lista y debería ser un "
                "texto, o «es:» y «en:» con un texto cada uno.",
                origen=origen,
                campo=campo,
            )
        )
    return Bilingue(es=_texto(valor), en=_texto(valor))


def _bilingue_lista(
    datos: dict[str, Any], campo: str, origen: str
) -> Bilingue[list[str]]:
    valor = datos.get(campo)
    if valor is None:
        return Bilingue(es=[], en=[])
    if isinstance(valor, dict):
        return Bilingue(
            es=_lista(valor.get("es"), campo, "es", origen),
            en=_lista(valor.get("en"), campo, "en", origen),
        )
    elementos = _lista(valor, campo, None, origen)
    return Bilingue(es=list(elementos), en=list(elementos))


def _lista(valor: Any, campo: str, idioma: str | None, origen: str) -> list[str]:
    if valor is None:
        return []
    if isinstance(valor, (list, tuple)):
        return [_texto(elemento) for elemento in valor]
    sufijo = f" ({idioma})" if idioma else ""
    raise ErrorPerfil(
        _(
            "En «%(origen)s», el campo «%(campo)s»%(sufijo)s debería ser una lista: una "
            "línea por elemento, cada una empezando por «- ».",
            origen=origen,
            campo=campo,
            sufijo=sufijo,
        )
    )


def _keywords(datos: dict[str, Any], origen: str) -> list[str]:
    """Se admite la lista y también «a, b, c» en una sola línea: es como se
    escriben a mano, y separarlas nosotros cuesta menos que explicar el formato."""
    valor = datos.get("keywords")
    if isinstance(valor, str):
        return [parte.strip() for parte in valor.split(",") if parte.strip()]
    elementos = (_texto(x).strip() for x in _lista(valor, "keywords", None, origen))
    return [palabra for palabra in elementos if palabra]


def _volcar_bilingue(dato: Bilingue[str]) -> dict[str, str]:
    return {"es": dato["es"], "en": dato["en"]}
