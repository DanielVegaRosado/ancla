"""Tests for the evaluation harness's deterministic checks.

Tested in both directions: that they pass a correct proposal and that they
**detect** each specific failure. A check that never fails checks nothing,
and would be worse than not having it because it gives a false sense of control.
"""
from __future__ import annotations

import pytest

from ancla.profile.model import (
    Bilingual,
    Experience,
    Profile,
    Proposal,
    SelectedAboutMe,
    SelectedExperience,
    Skill,
)
from evaluacion.checks import check


def _skill(id: str, nombre: str, keywords: list[str] | None = None) -> Skill:
    return Skill(
        id=id,
        name=Bilingual(es=nombre, en=nombre),
        category="lenguaje",
        keywords=keywords or [],
    )


def _experiencia(id: str) -> Experience:
    return Experience(
        id=id,
        title=Bilingual(es=id, en=id),
        period=Bilingual(es="2026", en="2026"),
        bullets=Bilingual(es=["algo"], en=["something"]),
        stack=Bilingual(es="Python", en="Python"),
        keywords=["python"],
    )


@pytest.fixture
def perfil() -> Profile:
    return Profile(
        experiences=[_experiencia("uno"), _experiencia("dos")],
        skills=[_skill("python", "Python"), _skill("sql", "SQL")],
    )


def _propuesta(**cambios) -> Proposal:
    base = dict(
        language="es",
        about_me=SelectedAboutMe(
            group_a=["Python"],
            group_b=["SQL"],
            text="Estudiante que domina Python y SQL.",
            reason="Son lo que pide la vacante.",
        ),
        skills=["python", "sql"],
        skills_reason="Los dos requisitos explícitos.",
        experiences=[
            SelectedExperience(id="uno", reason="Cubre el pipeline de datos."),
            SelectedExperience(id="dos", reason="Cubre la parte de modelado."),
        ],
        gaps=["Kubernetes"],
    )
    return Proposal(**{**base, **cambios})


def _fallidas(propuesta: Proposal, perfil: Profile) -> set[str]:
    return {c.nombre for c in check(propuesta, perfil, 2, 2) if not c.correcta}


def test_una_propuesta_correcta_pasa_todas(perfil):
    assert _fallidas(_propuesta(), perfil) == set()


def test_detecta_una_experiencia_que_no_esta_en_el_perfil(perfil):
    """The worst possible failure: something invented reaching the CV."""
    propuesta = _propuesta(
        experiences=[SelectedExperience(id="inventada", reason="x")]
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
        experiences=[SelectedExperience(id="uno", reason="   ")]
    )
    assert "todo_lleva_motivo" in _fallidas(propuesta, perfil)


def test_detecta_un_hueco_sin_rellenar_en_el_sobre_mi(perfil):
    """A `{GROUP_A_1}` would be copied into the user's CV as-is."""
    propuesta = _propuesta(
        about_me=SelectedAboutMe(
            group_a=["Python"],
            group_b=["SQL"],
            text="Estudiante que domina {GROUP_A_1} y SQL.",
            reason="x",
        )
    )
    assert "sobre_mi_sin_huecos" in _fallidas(propuesta, perfil)


def test_detecta_la_misma_skill_en_los_dos_grupos(perfil):
    propuesta = _propuesta(
        about_me=SelectedAboutMe(
            group_a=["Python"], group_b=["python"], text="Domino Python.", reason="x"
        )
    )
    assert "grupos_sin_solaparse" in _fallidas(propuesta, perfil)


def test_detecta_un_hueco_falso(perfil):
    """Telling the user they are missing something they have documented
    destroys trust in the gaps, which is exactly where the product is most useful."""
    assert "huecos_no_estan_en_el_perfil" in _fallidas(_propuesta(gaps=["Python"]), perfil)


def test_un_hueco_falso_tambien_se_detecta_por_keyword(perfil):
    perfil_con_keyword = Profile(
        experiences=perfil.experiences,
        skills=[_skill("python", "Python", keywords=["scripting"])],
    )
    propuesta = _propuesta(skills=["python"], gaps=["Scripting"])
    fallidas = {
        c.nombre
        for c in check(propuesta, perfil_con_keyword, 2, 1)
        if not c.correcta
    }
    assert "huecos_no_estan_en_el_perfil" in fallidas


def test_menos_elementos_en_el_perfil_que_los_pedidos_no_es_un_fallo(perfil):
    """Returning whatever there is is correct; filling the gap by inventing
    would be the failure."""
    perfil_corto = Profile(experiences=[_experiencia("uno")], skills=[_skill("python", "Python")])
    propuesta = _propuesta(
        skills=["python"],
        experiences=[SelectedExperience(id="uno", reason="Cubre el pipeline.")],
        gaps=[],
        about_me=SelectedAboutMe(
            group_a=["Python"], group_b=["SQL"], text="Domino Python.", reason="x"
        ),
    )
    fallidas = {
        c.nombre for c in check(propuesta, perfil_corto, 4, 9) if not c.correcta
    }
    assert "cantidades" not in fallidas
