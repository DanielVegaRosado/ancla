"""Tests de las comprobaciones deterministas del banco de pruebas.

Se prueban en los dos sentidos: que aprueban una propuesta correcta y que
**detectan** cada fallo concreto. Una comprobación que nunca falla no comprueba
nada, y sería peor que no tenerla porque da una falsa sensación de control.
"""
from __future__ import annotations

import pytest

from cv_adaptativo.perfil.modelo import (
    Bilingue,
    Experiencia,
    ExperienciaSeleccionada,
    Perfil,
    Propuesta,
    SeleccionSobreMi,
    Skill,
)
from evaluacion.comprobaciones import comprobar


def _skill(id: str, nombre: str, keywords: list[str] | None = None) -> Skill:
    return Skill(
        id=id,
        nombre=Bilingue(es=nombre, en=nombre),
        categoria="lenguaje",
        keywords=keywords or [],
    )


def _experiencia(id: str) -> Experiencia:
    return Experiencia(
        id=id,
        titulo=Bilingue(es=id, en=id),
        periodo=Bilingue(es="2026", en="2026"),
        bullets=Bilingue(es=["algo"], en=["something"]),
        stack=Bilingue(es="Python", en="Python"),
        keywords=["python"],
    )


@pytest.fixture
def perfil() -> Perfil:
    return Perfil(
        experiencias=[_experiencia("uno"), _experiencia("dos")],
        skills=[_skill("python", "Python"), _skill("sql", "SQL")],
    )


def _propuesta(**cambios) -> Propuesta:
    base = dict(
        idioma="es",
        sobre_mi=SeleccionSobreMi(
            grupo_a=["Python"],
            grupo_b=["SQL"],
            texto="Estudiante que domina Python y SQL.",
            motivo="Son lo que pide la vacante.",
        ),
        skills=["python", "sql"],
        motivo_skills="Los dos requisitos explícitos.",
        experiencias=[
            ExperienciaSeleccionada(id="uno", motivo="Cubre el pipeline de datos."),
            ExperienciaSeleccionada(id="dos", motivo="Cubre la parte de modelado."),
        ],
        huecos=["Kubernetes"],
    )
    return Propuesta(**{**base, **cambios})


def _fallidas(propuesta: Propuesta, perfil: Perfil) -> set[str]:
    return {c.nombre for c in comprobar(propuesta, perfil, 2, 2) if not c.correcta}


def test_una_propuesta_correcta_pasa_todas(perfil):
    assert _fallidas(_propuesta(), perfil) == set()


def test_detecta_una_experiencia_que_no_esta_en_el_perfil(perfil):
    """El fallo más grave posible: algo inventado llegando al CV."""
    propuesta = _propuesta(
        experiencias=[ExperienciaSeleccionada(id="inventada", motivo="x")]
    )
    assert "todo_del_catalogo" in _fallidas(propuesta, perfil)


def test_detecta_una_skill_que_no_esta_en_el_perfil(perfil):
    assert "todo_del_catalogo" in _fallidas(_propuesta(skills=["rust"]), perfil)


def test_detecta_elementos_repetidos(perfil):
    propuesta = _propuesta(skills=["python", "python"])
    assert "sin_repetidos" in _fallidas(propuesta, perfil)


def test_detecta_que_faltan_elementos(perfil):
    assert "cantidades" in _fallidas(_propuesta(skills=["python"]), perfil)


def test_detecta_un_motivo_vacio(perfil):
    propuesta = _propuesta(
        experiencias=[ExperienciaSeleccionada(id="uno", motivo="   ")]
    )
    assert "todo_lleva_motivo" in _fallidas(propuesta, perfil)


def test_detecta_un_hueco_sin_rellenar_en_el_sobre_mi(perfil):
    """Un `{GRUPO_A_1}` se copiaría tal cual al CV del usuario."""
    propuesta = _propuesta(
        sobre_mi=SeleccionSobreMi(
            grupo_a=["Python"],
            grupo_b=["SQL"],
            texto="Estudiante que domina {GRUPO_A_1} y SQL.",
            motivo="x",
        )
    )
    assert "sobre_mi_sin_huecos" in _fallidas(propuesta, perfil)


def test_detecta_la_misma_skill_en_los_dos_grupos(perfil):
    propuesta = _propuesta(
        sobre_mi=SeleccionSobreMi(
            grupo_a=["Python"], grupo_b=["python"], texto="Domino Python.", motivo="x"
        )
    )
    assert "grupos_sin_solaparse" in _fallidas(propuesta, perfil)


def test_detecta_un_hueco_falso(perfil):
    """Decirle al usuario que le falta algo que tiene documentado destruye la
    confianza en los huecos, que es justo donde el producto es más útil."""
    assert "huecos_no_estan_en_el_perfil" in _fallidas(_propuesta(huecos=["Python"]), perfil)


def test_un_hueco_falso_tambien_se_detecta_por_keyword(perfil):
    perfil_con_keyword = Perfil(
        experiencias=perfil.experiencias,
        skills=[_skill("python", "Python", keywords=["scripting"])],
    )
    propuesta = _propuesta(skills=["python"], huecos=["Scripting"])
    fallidas = {
        c.nombre
        for c in comprobar(propuesta, perfil_con_keyword, 2, 1)
        if not c.correcta
    }
    assert "huecos_no_estan_en_el_perfil" in fallidas


def test_menos_elementos_en_el_perfil_que_los_pedidos_no_es_un_fallo(perfil):
    """Devolver los que haya es lo correcto; rellenar inventando sería el fallo."""
    perfil_corto = Perfil(experiencias=[_experiencia("uno")], skills=[_skill("python", "Python")])
    propuesta = _propuesta(
        skills=["python"],
        experiencias=[ExperienciaSeleccionada(id="uno", motivo="Cubre el pipeline.")],
        huecos=[],
        sobre_mi=SeleccionSobreMi(
            grupo_a=["Python"], grupo_b=["SQL"], texto="Domino Python.", motivo="x"
        ),
    )
    fallidas = {
        c.nombre for c in comprobar(propuesta, perfil_corto, 4, 9) if not c.correcta
    }
    assert "cantidades" not in fallidas
