"""Tests de la validación del perfil.

Lo que se comprueba no es solo *que* detecte el fallo, sino que el mensaje sirva:
en español, diciendo qué elemento es y sin jerga de Python. El usuario lo lee en
pantalla y tiene que saber qué fichero abrir.
"""
from __future__ import annotations

import pytest

from cv_adaptativo.perfil import validacion
from cv_adaptativo.perfil.modelo import Bilingue, Experiencia, Perfil, Skill, SobreMi

PLANTILLA = (
    "Estudiante con conocimientos en {GRUPO_A_1}, {GRUPO_A_2} y {GRUPO_A_3}. "
    "Desarrollo en {GRUPO_B_1}, {GRUPO_B_2} y {GRUPO_B_3}."
)


def _experiencia(**cambios) -> Experiencia:
    base = dict(
        id="ml-telco-churn",
        titulo=Bilingue(es="ML Developer", en="ML Developer"),
        periodo=Bilingue(es="2026 - ACTUALIDAD", en="2026 - PRESENT"),
        bullets=Bilingue(es=["Pipeline completo"], en=["Full pipeline"]),
        stack=Bilingue(es="Python · Optuna", en="Python · Optuna"),
        keywords=["machine learning"],
    )
    return Experiencia(**{**base, **cambios})


def _skill(**cambios) -> Skill:
    base = dict(
        id="python",
        nombre=Bilingue(es="Python", en="Python"),
        categoria="lenguaje",
        keywords=["python"],
    )
    return Skill(**{**base, **cambios})


def _sobre_mi(es: str = PLANTILLA, en: str = PLANTILLA) -> SobreMi:
    return SobreMi(plantilla=Bilingue(es=es, en=en))


def _perfil_completo() -> Perfil:
    return Perfil(
        experiencias=[_experiencia()], skills=[_skill()], sobre_mi=_sobre_mi()
    )


# --------------------------------------------------------------------------
# Lo correcto no da problemas
# --------------------------------------------------------------------------


def test_un_perfil_completo_no_tiene_ningun_problema():
    assert validacion.validar_perfil(_perfil_completo()) == []


def test_una_experiencia_completa_no_tiene_ningun_problema():
    assert validacion.validar_experiencia(_experiencia()) == []


def test_una_skill_completa_no_tiene_ningun_problema():
    assert validacion.validar_skill(_skill()) == []


# --------------------------------------------------------------------------
# Experiencias
# --------------------------------------------------------------------------


def test_detecta_que_falta_la_traduccion_al_ingles():
    problemas = validacion.validar_experiencia(
        _experiencia(titulo=Bilingue(es="ML Developer", en="   "))
    )

    assert len(problemas) == 1
    assert "inglés" in problemas[0]
    assert "ml-telco-churn" in problemas[0]


def test_detecta_una_experiencia_sin_puntos():
    problemas = validacion.validar_experiencia(
        _experiencia(bullets=Bilingue(es=[], en=["Full pipeline"]))
    )

    assert any("no tiene ningún punto" in p and "español" in p for p in problemas)


def test_detecta_un_punto_en_blanco():
    problemas = validacion.validar_experiencia(
        _experiencia(bullets=Bilingue(es=["Pipeline", "  "], en=["Full pipeline"]))
    )

    assert any("punto vacío" in p for p in problemas)


def test_avisa_de_una_experiencia_sin_palabras_clave():
    """No rompe nada: simplemente no se elegiría nunca, y eso no se ve."""
    problemas = validacion.validar_experiencia(_experiencia(keywords=[]))

    assert any("palabras clave" in p for p in problemas)


def test_los_mensajes_van_en_castellano_y_sin_jerga():
    problemas = validacion.validar_experiencia(
        Experiencia(
            id="a-medias",
            titulo=Bilingue(es="", en=""),
            periodo=Bilingue(es="", en=""),
            bullets=Bilingue(es=[], en=[]),
            stack=Bilingue(es="", en=""),
        )
    )

    assert problemas
    for problema in problemas:
        assert "a-medias" in problema
        assert problema[-1] == "."
        for jerga in ("None", "Traceback", "Exception", "NotImplemented"):
            assert jerga not in problema


# --------------------------------------------------------------------------
# Skills
# --------------------------------------------------------------------------


def test_detecta_una_skill_sin_categoria_ni_palabras_clave():
    problemas = validacion.validar_skill(_skill(categoria="", keywords=[]))

    assert len(problemas) == 2
    assert any("categoría" in p for p in problemas)
    assert any("palabras clave" in p for p in problemas)


# --------------------------------------------------------------------------
# Sobre mí
# --------------------------------------------------------------------------


def test_detecta_que_falta_un_hueco_en_el_sobre_mi():
    problemas = validacion.validar_sobre_mi(
        _sobre_mi(es=PLANTILLA.replace("{GRUPO_B_3}", "Java"))
    )

    assert len(problemas) == 1
    assert "{GRUPO_B_3}" in problemas[0]
    assert "español" in problemas[0]


def test_detecta_un_hueco_inventado_que_nadie_va_a_rellenar():
    """Un {GRUPO_C_1} se quedaría escrito tal cual en el CV final."""
    problemas = validacion.validar_sobre_mi(
        _sobre_mi(en=PLANTILLA + " Además {GRUPO_C_1}.")
    )

    assert any("{GRUPO_C_1}" in p for p in problemas)


def test_detecta_un_sobre_mi_vacio():
    problemas = validacion.validar_sobre_mi(_sobre_mi(es=""))

    assert len(problemas) == 1
    assert "vacío" in problemas[0]


# --------------------------------------------------------------------------
# El conjunto
# --------------------------------------------------------------------------


def test_un_perfil_vacio_lo_dice_una_sola_vez():
    problemas = validacion.validar_perfil(Perfil())

    assert any("está vacío" in p for p in problemas)
    assert any("Sobre mí" in p for p in problemas)
    assert not any("No hay ninguna experiencia" in p for p in problemas)


def test_un_perfil_sin_skills_pero_con_experiencia_avisa_de_las_skills():
    problemas = validacion.validar_perfil(
        Perfil(experiencias=[_experiencia()], sobre_mi=_sobre_mi())
    )

    assert any("No hay ninguna skill" in p for p in problemas)


def test_detecta_ids_repetidos():
    """Los CV guardados referencian por id: repetirlo rompe el archivo histórico."""
    perfil = Perfil(
        experiencias=[_experiencia(), _experiencia()],
        skills=[_skill()],
        sobre_mi=_sobre_mi(),
    )

    problemas = validacion.validar_perfil(perfil)

    assert any("mismo identificador" in p and "ml-telco-churn" in p for p in problemas)


def test_el_perfil_junta_los_problemas_de_cada_elemento():
    perfil = Perfil(
        experiencias=[_experiencia(keywords=[])],
        skills=[_skill(categoria="")],
        sobre_mi=_sobre_mi(),
    )

    problemas = validacion.validar_perfil(perfil)

    assert any("ml-telco-churn" in p for p in problemas)
    assert any("python" in p for p in problemas)


def test_falta_el_sobre_mi():
    problemas = validacion.validar_perfil(
        Perfil(experiencias=[_experiencia()], skills=[_skill()])
    )

    assert any("Falta el «Sobre mí»" in p for p in problemas)
