"""Translation between the YAML format and the data model.

**Everything** that knows how a profile is written to a file lives here;
`almacen` only knows about folders, paths, and backups, and never imports
`yaml` anywhere. The boundary is deliberate: these functions are pure (text
and dictionaries go in, model objects come out), so they can be tested
without touching disk, which is where the hard decisions used to hide.

We are lenient when reading and canonical when writing. A bilingual field can
be written either way, because many titles are identical in both languages
and forcing them to be repeated invites them to drift apart:

    title:                     title: Data Analyst
      es: Analista de datos      (the same text in both languages)
      en: Data Analyst

`source` is the name of the file the data came from. It is passed along only
so it can be named in error messages: without it, "missing title" does not
tell the user which file to open.
"""
from __future__ import annotations

from typing import Any

import yaml
from flask_babel import gettext as _

from ancla.profile.errors import ProfileError
from ancla.profile.model import AboutMe, Bilingual, Experience, Skill, SpokenLanguage


# --------------------------------------------------------------------------
# YAML text <-> dictionary
# --------------------------------------------------------------------------


def read_data(texto: str, origen: str) -> dict[str, Any]:
    """Parses a file's text. An empty file yields an empty dictionary."""
    try:
        datos = yaml.safe_load(texto)
    except yaml.YAMLError as exc:
        raise ProfileError(_format_error(origen, exc)) from exc

    if datos is None:
        return {}
    if not isinstance(datos, dict):
        raise ProfileError(
            _(
                "«%(origen)s» no tiene el formato esperado: se esperaba una lista de "
                "campos como «title:» o «keywords:».",
                origen=origen,
            )
        )
    return datos


def dump_data(datos: dict[str, Any]) -> str:
    """The canonical form: fields in their own order, accents written out,
    and long lines never wrapped (a line we split confuses hand-editing)."""
    return yaml.safe_dump(
        datos,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=4096,
    )


def comment(texto: str) -> str:
    """Turns loose text into YAML comment lines."""
    return "".join(f"# {linea}\n" for linea in texto.splitlines())


def _format_error(origen: str, exc: yaml.YAMLError) -> str:
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
# Dictionary -> model
# --------------------------------------------------------------------------


def parse_experience(datos: dict[str, Any], id: str, origen: str) -> Experience:
    return Experience(
        id=id,
        title=_bilingual_text(datos, "title", origen),
        period=_bilingual_text(datos, "period", origen),
        bullets=_bilingual_list(datos, "bullets", origen),
        stack=_bilingual_text(datos, "stack", origen),
        keywords=_keywords(datos, origen),
        status=_text(datos.get("status")),
    )


def parse_skill(datos: dict[str, Any], id: str, origen: str) -> Skill:
    return Skill(
        id=id,
        name=_bilingual_text(datos, "name", origen),
        category=_text(datos.get("category")),
        keywords=_keywords(datos, origen),
    )


def parse_language(datos: dict[str, Any], id: str, origen: str) -> SpokenLanguage:
    return SpokenLanguage(
        id=id,
        name=_bilingual_text(datos, "name", origen),
        level=_bilingual_text(datos, "level", origen),
        keywords=_keywords(datos, origen),
    )


def parse_about_me(datos: dict[str, Any], origen: str) -> AboutMe:
    return AboutMe(template=_bilingual_text(datos, "template", origen))


# --------------------------------------------------------------------------
# Model -> dictionary
# --------------------------------------------------------------------------


def dump_experience(experiencia: Experience) -> dict[str, Any]:
    return {
        "title": _dump_bilingual(experiencia.title),
        "period": _dump_bilingual(experiencia.period),
        "status": experiencia.status,
        "bullets": {
            "es": [_text(b) for b in experiencia.bullets["es"]],
            "en": [_text(b) for b in experiencia.bullets["en"]],
        },
        "stack": _dump_bilingual(experiencia.stack),
        "keywords": list(experiencia.keywords),
    }


def dump_skill(skill: Skill) -> dict[str, Any]:
    return {
        "name": _dump_bilingual(skill.name),
        "category": skill.category,
        "keywords": list(skill.keywords),
    }


def dump_language(idioma: SpokenLanguage) -> dict[str, Any]:
    return {
        "name": _dump_bilingual(idioma.name),
        "level": _dump_bilingual(idioma.level),
        "keywords": list(idioma.keywords),
    }


def dump_about_me(sobre_mi: AboutMe) -> dict[str, Any]:
    return {"template": _dump_bilingual(sobre_mi.template)}


# --------------------------------------------------------------------------
# Shared pieces
# --------------------------------------------------------------------------


def _text(valor: Any) -> str:
    """Converts whatever is there to text. A `status: no` gets read by YAML as False."""
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return "sí" if valor else "no"
    if isinstance(valor, str):
        return valor
    return str(valor)


def _bilingual_text(datos: dict[str, Any], campo: str, origen: str) -> Bilingual[str]:
    valor = datos.get(campo)
    if valor is None:
        return Bilingual(es="", en="")
    if isinstance(valor, dict):
        return Bilingual(es=_text(valor.get("es")), en=_text(valor.get("en")))
    if isinstance(valor, (list, tuple)):
        raise ProfileError(
            _(
                "En «%(origen)s», el campo «%(campo)s» es una lista y debería ser un "
                "texto, o «es:» y «en:» con un texto cada uno.",
                origen=origen,
                campo=campo,
            )
        )
    return Bilingual(es=_text(valor), en=_text(valor))


def _bilingual_list(
    datos: dict[str, Any], campo: str, origen: str
) -> Bilingual[list[str]]:
    valor = datos.get(campo)
    if valor is None:
        return Bilingual(es=[], en=[])
    if isinstance(valor, dict):
        return Bilingual(
            es=_as_list(valor.get("es"), campo, "es", origen),
            en=_as_list(valor.get("en"), campo, "en", origen),
        )
    elementos = _as_list(valor, campo, None, origen)
    return Bilingual(es=list(elementos), en=list(elementos))


def _as_list(valor: Any, campo: str, idioma: str | None, origen: str) -> list[str]:
    if valor is None:
        return []
    if isinstance(valor, (list, tuple)):
        return [_text(elemento) for elemento in valor]
    sufijo = f" ({idioma})" if idioma else ""
    raise ProfileError(
        _(
            "En «%(origen)s», el campo «%(campo)s»%(sufijo)s debería ser una lista: una "
            "línea por elemento, cada una empezando por «- ».",
            origen=origen,
            campo=campo,
            sufijo=sufijo,
        )
    )


def _keywords(datos: dict[str, Any], origen: str) -> list[str]:
    """Accepts both a list and "a, b, c" on a single line: that is how people
    write it by hand, and splitting it ourselves is cheaper than explaining the format."""
    valor = datos.get("keywords")
    if isinstance(valor, str):
        return [parte.strip() for parte in valor.split(",") if parte.strip()]
    elementos = (_text(x).strip() for x in _as_list(valor, "keywords", None, origen))
    return [palabra for palabra in elementos if palabra]


def _dump_bilingual(dato: Bilingual[str]) -> dict[str, str]:
    return {"es": dato["es"], "en": dato["en"]}
