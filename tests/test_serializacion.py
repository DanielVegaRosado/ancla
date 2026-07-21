"""Tests de la traducción entre YAML y el modelo.

Todo esto son funciones puras, así que se prueban sin tocar el disco: es la razón
de haberlas sacado de `almacen`. Aquí viven las decisiones finas del formato (qué
se admite al leer, qué sale al escribir); que además funcione sobre ficheros de
verdad lo cubre `test_almacen.py`.
"""
from __future__ import annotations

import pytest

from cv_adaptativo.perfil import serializacion
from cv_adaptativo.perfil.errores import ErrorPerfil
from cv_adaptativo.perfil.modelo import Bilingue, Experiencia, Skill, SobreMi


# --------------------------------------------------------------------------
# Texto YAML -> diccionario
# --------------------------------------------------------------------------


def test_un_fichero_vacio_da_un_diccionario_vacio():
    assert serializacion.leer_datos("", "vacio.yaml") == {}


def test_un_yaml_mal_formado_nombra_el_fichero_y_la_linea():
    texto = "titulo:\n  es: bien\n   en: mal indentado\n"

    with pytest.raises(ErrorPerfil) as error:
        serializacion.leer_datos(texto, "rota.yaml")

    mensaje = str(error.value)
    assert "rota.yaml" in mensaje
    assert "línea 3" in mensaje


def test_un_yaml_que_no_es_un_diccionario_se_explica():
    with pytest.raises(ErrorPerfil, match="lista.yaml"):
        serializacion.leer_datos("- python\n- java\n", "lista.yaml")


# --------------------------------------------------------------------------
# Tolerancia al leer
# --------------------------------------------------------------------------


def test_un_texto_suelto_vale_para_los_dos_idiomas():
    skill = serializacion.a_skill({"nombre": "Java"}, "java", "java.yaml")

    assert skill.nombre["es"] == "Java"
    assert skill.nombre["en"] == "Java"


def test_un_campo_bilingue_a_medias_deja_el_otro_idioma_vacio():
    """Se carga igual; ya avisará la validación. Es lo normal mientras se edita."""
    skill = serializacion.a_skill({"nombre": {"es": "Java"}}, "java", "java.yaml")

    assert skill.nombre["es"] == "Java"
    assert skill.nombre["en"] == ""


@pytest.mark.parametrize(
    "valor",
    ["sql, bases de datos", ["sql", "bases de datos"], ("sql", "bases de datos")],
)
def test_las_keywords_admiten_lista_o_una_linea_con_comas(valor):
    skill = serializacion.a_skill({"keywords": valor}, "sql", "sql.yaml")

    assert skill.keywords == ["sql", "bases de datos"]


def test_las_keywords_en_blanco_no_cuentan():
    skill = serializacion.a_skill({"keywords": "sql, , ,python"}, "x", "x.yaml")

    assert skill.keywords == ["sql", "python"]


def test_un_estado_que_yaml_lee_como_booleano_vuelve_a_ser_texto():
    """`estado: no` lo interpreta YAML como False, y en el CV tiene que poner «no»."""
    experiencia = serializacion.a_experiencia({"estado": False}, "x", "x.yaml")

    assert experiencia.estado == "no"


def test_un_numero_suelto_se_lee_como_texto():
    """`periodo: 2026` es un entero para YAML, pero en el CV es una fecha."""
    experiencia = serializacion.a_experiencia({"periodo": 2026}, "x", "x.yaml")

    assert experiencia.periodo["es"] == "2026"


def test_los_campos_que_faltan_no_revientan():
    experiencia = serializacion.a_experiencia({}, "a-medias", "a-medias.yaml")

    assert experiencia.id == "a-medias"
    assert experiencia.titulo["es"] == ""
    assert experiencia.bullets["en"] == []
    assert experiencia.keywords == []


# --------------------------------------------------------------------------
# Lo que no se admite, se explica
# --------------------------------------------------------------------------


def test_un_texto_donde_iba_una_lista_se_explica_diciendo_el_campo():
    with pytest.raises(ErrorPerfil) as error:
        serializacion.a_experiencia(
            {"bullets": {"es": "esto debería ser una lista"}}, "x", "quantum.yaml"
        )

    mensaje = str(error.value)
    assert "quantum.yaml" in mensaje
    assert "bullets" in mensaje
    assert "(es)" in mensaje


def test_una_lista_donde_iba_un_texto_se_explica():
    with pytest.raises(ErrorPerfil, match="titulo"):
        serializacion.a_experiencia({"titulo": ["uno", "otro"]}, "x", "x.yaml")


# --------------------------------------------------------------------------
# Escritura canónica
# --------------------------------------------------------------------------


def test_al_escribir_se_respeta_el_orden_de_los_campos():
    """Los ficheros son del usuario: se leen de arriba abajo, no por orden alfabético."""
    texto = serializacion.volcar_datos(serializacion.de_skill(_skill()))

    assert texto.index("nombre:") < texto.index("categoria:") < texto.index("keywords:")


def test_los_acentos_se_escriben_no_se_escapan():
    texto = serializacion.volcar_datos({"categoria": "ingeniería"})

    assert "ingeniería" in texto
    assert "\\u" not in texto


def test_un_texto_que_parece_booleano_se_escribe_entrecomillado():
    """Sin comillas, `estado: no` se releería como False y se perdería el texto."""
    texto = serializacion.volcar_datos({"estado": "no"})

    assert serializacion.leer_datos(texto, "x.yaml") == {"estado": "no"}


def test_las_lineas_largas_no_se_parten():
    """Una línea partida por nosotros desconcierta a quien edite el fichero a mano."""
    plantilla = "Estudiante " * 40
    texto = serializacion.volcar_datos({"plantilla": plantilla})

    assert len([linea for linea in texto.splitlines() if linea.strip()]) == 1


def test_comentario_convierte_cada_linea():
    assert serializacion.comentario("una\notra") == "# una\n# otra\n"


# --------------------------------------------------------------------------
# Ida y vuelta
# --------------------------------------------------------------------------


def _skill() -> Skill:
    return Skill(
        id="python",
        nombre=Bilingue(es="Python", en="Python"),
        categoria="lenguaje",
        keywords=["python", "scripting"],
    )


def _experiencia() -> Experiencia:
    return Experiencia(
        id="ml-telco-churn",
        titulo=Bilingue(es="ML Developer", en="ML Developer"),
        periodo=Bilingue(es="2026 - ACTUALIDAD", en="2026 - PRESENT"),
        bullets=Bilingue(
            es=["Pipeline completo: diseño, pruebas y evaluación."],
            en=["Full pipeline: design, testing, evaluation"],
        ),
        stack=Bilingue(es="Python · Optuna", en="Python · Optuna"),
        keywords=["machine learning"],
        estado="actualidad",
    )


def _sobre_mi() -> SobreMi:
    texto = "Sé de {GRUPO_A_1}, {GRUPO_A_2} y {GRUPO_A_3}; uso {GRUPO_B_1}, {GRUPO_B_2} y {GRUPO_B_3}."
    return SobreMi(plantilla=Bilingue(es=texto, en=texto))


@pytest.mark.parametrize(
    ("original", "volcar", "cargar"),
    [
        (_experiencia(), serializacion.de_experiencia, serializacion.a_experiencia),
        (_skill(), serializacion.de_skill, serializacion.a_skill),
    ],
)
def test_ida_y_vuelta_no_altera_nada(original, volcar, cargar):
    """Regla dura del producto: al usuario no se le reescribe ni una coma."""
    texto = serializacion.volcar_datos(volcar(original))

    recuperado = cargar(serializacion.leer_datos(texto, "x.yaml"), original.id, "x.yaml")

    assert recuperado == original


def test_ida_y_vuelta_del_sobre_mi_conserva_los_huecos():
    original = _sobre_mi()

    texto = serializacion.volcar_datos(serializacion.de_sobre_mi(original))
    recuperado = serializacion.a_sobre_mi(serializacion.leer_datos(texto, "x.yaml"), "x.yaml")

    assert recuperado == original
    for hueco in recuperado.huecos():
        assert hueco in recuperado.plantilla["es"]
