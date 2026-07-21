"""Conversión entre un `CVGuardado` y el diccionario que va al YAML.

Misma frontera que en `perfil/serializacion`: `repositorio` sabe de carpetas,
rutas y adjuntos; este módulo sabe de la **forma** del fichero. Separarlos
permite cambiar el formato en disco sin tocar la persistencia, y al revés.

Al leer se es tolerante y al escribir canónico: el fichero se puede editar a
mano, así que un campo ausente o con el tipo cambiado da un valor vacío en vez
de una excepción. Lo único que no se perdona es la fecha, porque es la que
ordena el archivo entero.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from cv_adaptativo.perfil.errores import ErrorPerfil
from cv_adaptativo.perfil.modelo import (
    CVGuardado,
    EstadoCV,
    ExperienciaSeleccionada,
    Propuesta,
    SeleccionSobreMi,
)
from cv_adaptativo.texto import a_texto, a_textos


def de_cv(cv: CVGuardado) -> dict[str, Any]:
    """El CV como diccionario, listo para volcar a YAML."""
    return {
        "fecha": cv.fecha.isoformat(),
        "empresa": cv.empresa,
        "puesto": cv.puesto,
        "estado": cv.estado.value,
        "adjunto": cv.adjunto or "",
        "notas": cv.notas,
        "vacante": cv.vacante,
        "propuesta": _de_propuesta(cv.propuesta),
    }


def a_cv(datos: dict[str, Any], id: str) -> CVGuardado:
    """Reconstruye el CV. Lanza `ErrorPerfil` si la fecha no se entiende."""
    return CVGuardado(
        id=id,
        fecha=_a_fecha(datos.get("fecha"), id),
        empresa=a_texto(datos.get("empresa")),
        puesto=a_texto(datos.get("puesto")),
        vacante=a_texto(datos.get("vacante")),
        estado=_a_estado(datos.get("estado")),
        adjunto=a_texto(datos.get("adjunto")) or None,
        notas=a_texto(datos.get("notas")),
        propuesta=_a_propuesta(_diccionario(datos.get("propuesta"))),
    )


# --------------------------------------------------------------------------


def _de_propuesta(propuesta: Propuesta) -> dict[str, Any]:
    return {
        "idioma": propuesta.idioma,
        "sobre_mi": {
            "grupo_a": list(propuesta.sobre_mi.grupo_a),
            "grupo_b": list(propuesta.sobre_mi.grupo_b),
            "texto": propuesta.sobre_mi.texto,
            "motivo": propuesta.sobre_mi.motivo,
        },
        "skills": list(propuesta.skills),
        "motivo_skills": propuesta.motivo_skills,
        "experiencias": [
            {"id": exp.id, "motivo": exp.motivo} for exp in propuesta.experiencias
        ],
        "huecos": list(propuesta.huecos),
    }


def _a_propuesta(datos: dict[str, Any]) -> Propuesta:
    sobre_mi = _diccionario(datos.get("sobre_mi"))
    return Propuesta(
        idioma="en" if a_texto(datos.get("idioma")) == "en" else "es",
        sobre_mi=SeleccionSobreMi(
            grupo_a=a_textos(sobre_mi.get("grupo_a")),
            grupo_b=a_textos(sobre_mi.get("grupo_b")),
            texto=a_texto(sobre_mi.get("texto")),
            motivo=a_texto(sobre_mi.get("motivo")),
        ),
        skills=a_textos(datos.get("skills")),
        motivo_skills=a_texto(datos.get("motivo_skills")),
        experiencias=_a_experiencias(datos.get("experiencias")),
        huecos=a_textos(datos.get("huecos")),
    )


def _a_experiencias(valor: Any) -> list[ExperienciaSeleccionada]:
    """Una experiencia sin id no referencia a nada del perfil: se descarta."""
    if not isinstance(valor, list):
        return []
    elementos = (_diccionario(elemento) for elemento in valor)
    return [
        ExperienciaSeleccionada(id=id_exp, motivo=a_texto(datos.get("motivo")))
        for datos in elementos
        if (id_exp := a_texto(datos.get("id")))
    ]


def _a_fecha(valor: Any, id: str) -> date:
    """PyYAML ya devuelve `date` si la fecha va sin comillas; si no, se parsea."""
    if isinstance(valor, date):
        return valor
    try:
        return date.fromisoformat(str(valor))
    except (TypeError, ValueError) as exc:
        raise ErrorPerfil(
            f"El CV «{id}» no tiene una fecha válida (esperaba algo como 2026-07-24)."
        ) from exc


def _a_estado(valor: Any) -> EstadoCV:
    """Un estado desconocido no invalida el CV: se trata como borrador."""
    try:
        return EstadoCV(a_texto(valor))
    except ValueError:
        return EstadoCV.BORRADOR


def _diccionario(valor: Any) -> dict[str, Any]:
    return valor if isinstance(valor, dict) else {}
