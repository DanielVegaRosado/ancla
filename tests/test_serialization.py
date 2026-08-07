"""Tests for the translation between YAML and the model.

All of this is pure functions, so they are tested without touching disk:
that is the reason they were pulled out of `almacen`. This is where the
format's fine-grained decisions live (what is accepted when reading, what
comes out when writing); that it also works against real files is covered
by `test_almacen.py`.
"""
from __future__ import annotations

import pytest

from ancla.profile import serialization
from ancla.profile.errors import ProfileError
from ancla.profile.model import AboutMe, Bilingual, Experience, Skill


# --------------------------------------------------------------------------
# YAML text -> dictionary
# --------------------------------------------------------------------------


def test_un_fichero_vacio_da_un_diccionario_vacio():
    assert serialization.read_data("", "vacio.yaml") == {}


def test_un_yaml_mal_formado_nombra_el_fichero_y_la_linea():
    texto = "title:\n  es: bien\n   en: mal indentado\n"

    with pytest.raises(ProfileError) as error:
        serialization.read_data(texto, "rota.yaml")

    mensaje = str(error.value)
    assert "rota.yaml" in mensaje
    assert "línea 3" in mensaje


def test_un_yaml_que_no_es_un_diccionario_se_explica():
    with pytest.raises(ProfileError, match="lista.yaml"):
        serialization.read_data("- python\n- java\n", "lista.yaml")


# --------------------------------------------------------------------------
# Leniency when reading
# --------------------------------------------------------------------------


def test_un_texto_suelto_vale_para_los_dos_idiomas():
    skill = serialization.parse_skill({"name": "Java"}, "java", "java.yaml")

    assert skill.name["es"] == "Java"
    assert skill.name["en"] == "Java"


def test_un_campo_bilingue_a_medias_deja_el_otro_idioma_vacio():
    """Loads the same way; validation will flag it. Normal while editing."""
    skill = serialization.parse_skill({"name": {"es": "Java"}}, "java", "java.yaml")

    assert skill.name["es"] == "Java"
    assert skill.name["en"] == ""


@pytest.mark.parametrize(
    "valor",
    ["sql, bases de datos", ["sql", "bases de datos"], ("sql", "bases de datos")],
)
def test_las_keywords_admiten_lista_o_una_linea_con_comas(valor):
    skill = serialization.parse_skill({"keywords": valor}, "sql", "sql.yaml")

    assert skill.keywords == ["sql", "bases de datos"]


def test_las_keywords_en_blanco_no_cuentan():
    skill = serialization.parse_skill({"keywords": "sql, , ,python"}, "x", "x.yaml")

    assert skill.keywords == ["sql", "python"]


def test_un_estado_que_yaml_lee_como_booleano_vuelve_a_ser_texto():
    """`status: no` gets read by YAML as False, and the CV needs "no" as text."""
    experiencia = serialization.parse_experience({"status": False}, "x", "x.yaml")

    assert experiencia.status == "no"


def test_un_numero_suelto_se_lee_como_texto():
    """`period: 2026` is an integer to YAML, but on the CV it is a date."""
    experiencia = serialization.parse_experience({"period": 2026}, "x", "x.yaml")

    assert experiencia.period["es"] == "2026"


def test_los_campos_que_faltan_no_revientan():
    experiencia = serialization.parse_experience({}, "a-medias", "a-medias.yaml")

    assert experiencia.id == "a-medias"
    assert experiencia.title["es"] == ""
    assert experiencia.bullets["en"] == []
    assert experiencia.keywords == []


# --------------------------------------------------------------------------
# What is not accepted is explained
# --------------------------------------------------------------------------


def test_un_texto_donde_iba_una_lista_se_explica_diciendo_el_campo():
    with pytest.raises(ProfileError) as error:
        serialization.parse_experience(
            {"bullets": {"es": "esto debería ser una lista"}}, "x", "quantum.yaml"
        )

    mensaje = str(error.value)
    assert "quantum.yaml" in mensaje
    assert "bullets" in mensaje
    assert "(es)" in mensaje


def test_una_lista_donde_iba_un_texto_se_explica():
    with pytest.raises(ProfileError, match="title"):
        serialization.parse_experience({"title": ["uno", "otro"]}, "x", "x.yaml")


# --------------------------------------------------------------------------
# Canonical writing
# --------------------------------------------------------------------------


def test_al_escribir_se_respeta_el_orden_de_los_campos():
    """The files belong to the user: read top to bottom, not alphabetically."""
    texto = serialization.dump_data(serialization.dump_skill(_skill()))

    assert texto.index("name:") < texto.index("category:") < texto.index("keywords:")


def test_los_acentos_se_escriben_no_se_escapan():
    texto = serialization.dump_data({"category": "ingeniería"})

    assert "ingeniería" in texto
    assert "\\u" not in texto


def test_un_texto_que_parece_booleano_se_escribe_entrecomillado():
    """Without quotes, `status: no` would be re-read as False and the text would be lost."""
    texto = serialization.dump_data({"status": "no"})

    assert serialization.read_data(texto, "x.yaml") == {"status": "no"}


def test_las_lineas_largas_no_se_parten():
    """A line we split confuses anyone hand-editing the file."""
    plantilla = "Estudiante " * 40
    texto = serialization.dump_data({"template": plantilla})

    assert len([linea for linea in texto.splitlines() if linea.strip()]) == 1


def test_comentario_convierte_cada_linea():
    assert serialization.comment("una\notra") == "# una\n# otra\n"


# --------------------------------------------------------------------------
# Round trip
# --------------------------------------------------------------------------


def _skill() -> Skill:
    return Skill(
        id="python",
        name=Bilingual(es="Python", en="Python"),
        category="lenguaje",
        keywords=["python", "scripting"],
    )


def _experiencia() -> Experience:
    return Experience(
        id="ml-telco-churn",
        title=Bilingual(es="ML Developer", en="ML Developer"),
        period=Bilingual(es="2026 - ACTUALIDAD", en="2026 - PRESENT"),
        bullets=Bilingual(
            es=["Pipeline completo: diseño, pruebas y evaluación."],
            en=["Full pipeline: design, testing, evaluation"],
        ),
        stack=Bilingual(es="Python · Optuna", en="Python · Optuna"),
        keywords=["machine learning"],
        status="actualidad",
    )


def _sobre_mi() -> AboutMe:
    texto = "Sé de {GROUP_A_1}, {GROUP_A_2} y {GROUP_A_3}; uso {GROUP_B_1}, {GROUP_B_2} y {GROUP_B_3}."
    return AboutMe(template=Bilingual(es=texto, en=texto))


@pytest.mark.parametrize(
    ("original", "volcar", "cargar"),
    [
        (_experiencia(), serialization.dump_experience, serialization.parse_experience),
        (_skill(), serialization.dump_skill, serialization.parse_skill),
    ],
)
def test_ida_y_vuelta_no_altera_nada(original, volcar, cargar):
    """Hard product rule: not a single comma of the user's is ever rewritten."""
    texto = serialization.dump_data(volcar(original))

    recuperado = cargar(serialization.read_data(texto, "x.yaml"), original.id, "x.yaml")

    assert recuperado == original


def test_ida_y_vuelta_del_sobre_mi_conserva_los_huecos():
    original = _sobre_mi()

    texto = serialization.dump_data(serialization.dump_about_me(original))
    recuperado = serialization.parse_about_me(serialization.read_data(texto, "x.yaml"), "x.yaml")

    assert recuperado == original
    for hueco in recuperado.gaps():
        assert hueco in recuperado.template["es"]
