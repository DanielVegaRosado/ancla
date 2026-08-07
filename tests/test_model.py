"""Data model tests.

Fix the contract before the other modules get built in parallel. If one of
these fails, someone changed the contract: that needs to be discussed, not
worked around by adjusting the test.
"""
from __future__ import annotations

import pytest

from ancla.profile.model import (
    N_ABOUT_ME_GROUP,
    AboutMe,
    Bilingual,
    Experience,
    Profile,
    Skill,
)


def test_bilingue_devuelve_el_idioma_pedido():
    titulo = Bilingual(es="Ingeniero de Datos", en="Data Engineer")
    assert titulo["es"] == "Ingeniero de Datos"
    assert titulo["en"] == "Data Engineer"


def test_bilingue_sirve_para_listas_no_solo_textos():
    bullets = Bilingual(es=["Diseño del pipeline"], en=["Pipeline design"])
    assert bullets["en"] == ["Pipeline design"]


def test_bilingue_rechaza_un_idioma_desconocido():
    with pytest.raises(ValueError):
        Bilingual(es="a", en="b")["fr"]


def _sobre_mi() -> AboutMe:
    texto_es = (
        "Estudiante con conocimientos en {GROUP_A_1}, {GROUP_A_2} y {GROUP_A_3}. "
        "Desarrollo en {GROUP_B_1}, {GROUP_B_2} y {GROUP_B_3}."
    )
    return AboutMe(template=Bilingual(es=texto_es, en=texto_es))


def test_sobre_mi_declara_sus_seis_huecos():
    assert len(_sobre_mi().gaps()) == N_ABOUT_ME_GROUP * 2


def test_sobre_mi_rellena_los_huecos_y_no_deja_ninguno():
    texto = _sobre_mi().render(
        group_a=["machine learning", "LLMs", "sistemas de agentes"],
        group_b=["Python", "SQL", "Java"],
        language="es",
    )
    assert "machine learning" in texto and "Python" in texto
    assert "{GROUP_" not in texto


def test_sobre_mi_exige_exactamente_tres_elementos_por_grupo():
    """Better to fail than to produce a CV with an unfilled gap inside."""
    with pytest.raises(ValueError):
        _sobre_mi().render(group_a=["solo uno"], group_b=["a", "b", "c"], language="es")


def test_perfil_busca_por_id_y_devuelve_none_si_no_existe():
    experiencia = Experience(
        id="ml-telco-churn",
        title=Bilingual(es="ML Developer", en="ML Developer"),
        period=Bilingual(es="2026 - ACTUALIDAD", en="2026 - PRESENT"),
        bullets=Bilingual(es=["Pipeline completo"], en=["Full pipeline"]),
        stack=Bilingual(es="Python · Optuna", en="Python · Optuna"),
        keywords=["machine learning"],
    )
    skill = Skill(id="python", name=Bilingual(es="Python", en="Python"))
    perfil = Profile(experiences=[experiencia], skills=[skill])

    assert perfil.experience("ml-telco-churn") is experiencia
    assert perfil.skill("python") is skill
    assert perfil.experience("no-existe") is None
    assert not perfil.is_empty()


def test_perfil_recien_creado_esta_vacio():
    """This is the normal state the first time the app is opened, not an error."""
    assert Profile().is_empty()
