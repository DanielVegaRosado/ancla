"""Tests del modelo de datos.

Fijan el contrato antes de que los demás módulos se construyan en paralelo. Si
uno de estos falla, es que alguien ha cambiado el contrato: hay que hablarlo,
no ajustar el test.
"""
from __future__ import annotations

import pytest

from cv_adaptativo.perfil.modelo import (
    N_GRUPO_SOBRE_MI,
    Bilingue,
    Experiencia,
    Perfil,
    Skill,
    SobreMi,
)


def test_bilingue_devuelve_el_idioma_pedido():
    titulo = Bilingue(es="Ingeniero de Datos", en="Data Engineer")
    assert titulo["es"] == "Ingeniero de Datos"
    assert titulo["en"] == "Data Engineer"


def test_bilingue_sirve_para_listas_no_solo_textos():
    bullets = Bilingue(es=["Diseño del pipeline"], en=["Pipeline design"])
    assert bullets["en"] == ["Pipeline design"]


def test_bilingue_rechaza_un_idioma_desconocido():
    with pytest.raises(ValueError):
        Bilingue(es="a", en="b")["fr"]


def _sobre_mi() -> SobreMi:
    texto_es = (
        "Estudiante con conocimientos en {GRUPO_A_1}, {GRUPO_A_2} y {GRUPO_A_3}. "
        "Desarrollo en {GRUPO_B_1}, {GRUPO_B_2} y {GRUPO_B_3}."
    )
    return SobreMi(plantilla=Bilingue(es=texto_es, en=texto_es))


def test_sobre_mi_declara_sus_seis_huecos():
    assert len(_sobre_mi().huecos()) == N_GRUPO_SOBRE_MI * 2


def test_sobre_mi_rellena_los_huecos_y_no_deja_ninguno():
    texto = _sobre_mi().render(
        grupo_a=["machine learning", "LLMs", "sistemas de agentes"],
        grupo_b=["Python", "SQL", "Java"],
        idioma="es",
    )
    assert "machine learning" in texto and "Python" in texto
    assert "{GRUPO_" not in texto


def test_sobre_mi_exige_exactamente_tres_elementos_por_grupo():
    """Mejor fallar que producir un CV con un hueco sin rellenar dentro."""
    with pytest.raises(ValueError):
        _sobre_mi().render(grupo_a=["solo uno"], grupo_b=["a", "b", "c"], idioma="es")


def test_perfil_busca_por_id_y_devuelve_none_si_no_existe():
    experiencia = Experiencia(
        id="ml-telco-churn",
        titulo=Bilingue(es="ML Developer", en="ML Developer"),
        periodo=Bilingue(es="2026 - ACTUALIDAD", en="2026 - PRESENT"),
        bullets=Bilingue(es=["Pipeline completo"], en=["Full pipeline"]),
        stack=Bilingue(es="Python · Optuna", en="Python · Optuna"),
        keywords=["machine learning"],
    )
    skill = Skill(id="python", nombre=Bilingue(es="Python", en="Python"))
    perfil = Perfil(experiencias=[experiencia], skills=[skill])

    assert perfil.experiencia("ml-telco-churn") is experiencia
    assert perfil.skill("python") is skill
    assert perfil.experiencia("no-existe") is None
    assert not perfil.esta_vacio()


def test_perfil_recien_creado_esta_vacio():
    """Es el estado normal la primera vez que se abre la app, no un error."""
    assert Perfil().esta_vacio()
