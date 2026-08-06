"""Tests HTTP de skills personales, idiomas y su reflejo en Propuesta.

El motivo de todo esto: skills personales e idiomas nunca pasan por el motor
de selección, así que la única forma de comprobar de verdad que la interfaz
los deja fuera de "Sobre mí" y de las skills técnicas —tal como pidió Daniel—
es probarlo a través de las rutas reales, no solo a nivel de `formato.py`.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from ancla.perfil import almacen
from ancla.perfil.modelo import (
    Bilingue,
    Experiencia,
    IdiomaHablado,
    Propuesta,
    SeleccionSobreMi,
    Skill,
)
from ancla.web import borrador as modulo_borrador
from ancla.web import crear_app


@pytest.fixture
def cliente_web(tmp_path: Path):
    app = crear_app(raiz_perfil=tmp_path / "perfil", ruta_ajustes=tmp_path / "ajustes.json")
    app.config["TESTING"] = True
    return app.test_client()


# --------------------------------------------------------------------------
# Skills personales
# --------------------------------------------------------------------------


def test_crear_skill_personal_la_deja_ver_en_mi_perfil(cliente_web):
    respuesta = cliente_web.post(
        "/perfil/skills-personales/nueva",
        data={"nombre_es": "Trabajo en equipo", "nombre_en": "Teamwork", "keywords": "team player"},
        follow_redirects=True,
    )
    assert respuesta.status_code == 200
    assert "Trabajo en equipo".encode("utf-8") in respuesta.data


def test_crear_skill_personal_sin_nombre_en_ingles_muestra_el_error(cliente_web):
    respuesta = cliente_web.post(
        "/perfil/skills-personales/nueva",
        data={"nombre_es": "Trabajo en equipo", "keywords": "team player"},
    )
    assert respuesta.status_code == 200  # se queda en el formulario, no redirige
    assert "falta el nombre en inglés".encode("utf-8") in respuesta.data


def test_crear_skill_personal_no_pide_categoria(cliente_web):
    """A diferencia del formulario de skills técnicas."""
    respuesta = cliente_web.get("/perfil/skills-personales/nueva")
    assert b'name="categoria"' not in respuesta.data


def test_editar_skill_personal_conserva_el_id(cliente_web, tmp_path: Path):
    cliente_web.post(
        "/perfil/skills-personales/nueva",
        data={"nombre_es": "Liderazgo", "nombre_en": "Leadership", "keywords": "lead"},
    )
    cliente_web.post(
        "/perfil/skills-personales/liderazgo/editar",
        data={"nombre_es": "Liderazgo de equipos", "nombre_en": "Team leadership", "keywords": "lead"},
    )
    perfil = almacen.cargar_perfil(tmp_path / "perfil")
    assert perfil.skill_personal("liderazgo").nombre["es"] == "Liderazgo de equipos"


def test_borrar_skill_personal_la_quita_del_perfil(cliente_web, tmp_path: Path):
    cliente_web.post(
        "/perfil/skills-personales/nueva",
        data={"nombre_es": "Empatía", "nombre_en": "Empathy", "keywords": "empathy"},
    )
    cliente_web.post("/perfil/skills-personales/empatia/borrar")
    perfil = almacen.cargar_perfil(tmp_path / "perfil")
    assert perfil.skill_personal("empatia") is None


def test_una_skill_personal_con_id_repetido_da_error_claro(cliente_web):
    cliente_web.post(
        "/perfil/skills-personales/nueva",
        data={"id": "empatia", "nombre_es": "Empatía", "nombre_en": "Empathy", "keywords": "x"},
    )
    respuesta = cliente_web.post(
        "/perfil/skills-personales/nueva",
        data={"id": "empatia", "nombre_es": "Otra cosa", "nombre_en": "Other", "keywords": "x"},
    )
    assert "Ya existe una skill personal".encode("utf-8") in respuesta.data


# --------------------------------------------------------------------------
# Idiomas
# --------------------------------------------------------------------------


def test_crear_idioma_lo_deja_ver_en_mi_perfil(cliente_web):
    respuesta = cliente_web.post(
        "/perfil/idiomas/nuevo",
        data={
            "nombre_es": "Inglés",
            "nombre_en": "English",
            "nivel_es": "C1 — Avanzado",
            "nivel_en": "C1 — Advanced",
            "keywords": "advanced english",
        },
        follow_redirects=True,
    )
    assert respuesta.status_code == 200
    assert "Inglés".encode("utf-8") in respuesta.data
    assert "C1".encode("utf-8") in respuesta.data


def test_crear_idioma_sin_nivel_muestra_el_error(cliente_web):
    respuesta = cliente_web.post(
        "/perfil/idiomas/nuevo",
        data={"nombre_es": "Francés", "nombre_en": "French", "nivel_es": "", "nivel_en": "B2"},
    )
    assert "falta el nivel en español".encode("utf-8") in respuesta.data


def test_borrar_idioma_lo_quita_del_perfil(cliente_web, tmp_path: Path):
    cliente_web.post(
        "/perfil/idiomas/nuevo",
        data={
            "nombre_es": "Alemán", "nombre_en": "German",
            "nivel_es": "A2", "nivel_en": "A2", "keywords": "german",
        },
    )
    cliente_web.post("/perfil/idiomas/aleman/borrar")
    perfil = almacen.cargar_perfil(tmp_path / "perfil")
    assert perfil.idioma("aleman") is None


def test_editar_un_idioma_que_no_existe_avisa_y_redirige(cliente_web):
    respuesta = cliente_web.get("/perfil/idiomas/no-existe/editar", follow_redirects=True)
    assert "No existe el idioma".encode("utf-8") in respuesta.data


# --------------------------------------------------------------------------
# Borrado masivo: borrar una sección entera de golpe, no solo uno a uno
# --------------------------------------------------------------------------


def test_borrar_todas_las_experiencias_las_quita_todas(cliente_web, tmp_path: Path):
    raiz = tmp_path / "perfil"
    almacen.guardar_experiencia(
        raiz,
        Experiencia(
            id="proyecto-1",
            titulo=Bilingue(es="Proyecto 1", en="Project 1"),
            periodo=Bilingue(es="2024", en="2024"),
            bullets=Bilingue(es=["Hecho 1"], en=["Done 1"]),
            stack=Bilingue(es="Python", en="Python"),
        ),
    )
    almacen.guardar_experiencia(
        raiz,
        Experiencia(
            id="proyecto-2",
            titulo=Bilingue(es="Proyecto 2", en="Project 2"),
            periodo=Bilingue(es="2025", en="2025"),
            bullets=Bilingue(es=["Hecho 2"], en=["Done 2"]),
            stack=Bilingue(es="SQL", en="SQL"),
        ),
    )

    respuesta = cliente_web.post("/perfil/experiencias/borrar-todas", follow_redirects=True)

    assert respuesta.status_code == 200
    assert "2 experiencia(s) borradas".encode("utf-8") in respuesta.data
    assert almacen.cargar_perfil(raiz).experiencias == []


def test_borrar_todas_las_skills_tecnicas_no_toca_las_personales(cliente_web, tmp_path: Path):
    raiz = tmp_path / "perfil"
    almacen.guardar_skill(raiz, Skill(id="python", nombre=Bilingue(es="Python", en="Python")))
    almacen.guardar_skill_personal(
        raiz, Skill(id="empatia", nombre=Bilingue(es="Empatía", en="Empathy"))
    )

    cliente_web.post("/perfil/skills/borrar-todas")

    perfil = almacen.cargar_perfil(raiz)
    assert perfil.skills == []
    assert perfil.skill_personal("empatia") is not None


def test_borrar_todas_las_skills_personales_las_quita_todas(cliente_web, tmp_path: Path):
    raiz = tmp_path / "perfil"
    almacen.guardar_skill_personal(
        raiz, Skill(id="empatia", nombre=Bilingue(es="Empatía", en="Empathy"))
    )

    respuesta = cliente_web.post(
        "/perfil/skills-personales/borrar-todas", follow_redirects=True
    )

    assert "1 skill(s) personal(es) borradas".encode("utf-8") in respuesta.data
    assert almacen.cargar_perfil(raiz).skills_personales == []


def test_borrar_todos_los_idiomas_los_quita_todos(cliente_web, tmp_path: Path):
    raiz = tmp_path / "perfil"
    almacen.guardar_idioma(
        raiz,
        IdiomaHablado(
            id="ingles",
            nombre=Bilingue(es="Inglés", en="English"),
            nivel=Bilingue(es="C1", en="C1"),
        ),
    )

    respuesta = cliente_web.post("/perfil/idiomas/borrar-todos", follow_redirects=True)

    assert "1 idioma(s) borrados".encode("utf-8") in respuesta.data
    assert almacen.cargar_perfil(raiz).idiomas == []


def test_borrar_todas_sobre_una_seccion_vacia_avisa_sin_fallar(cliente_web):
    respuesta = cliente_web.post("/perfil/experiencias/borrar-todas", follow_redirects=True)
    assert "No había ninguna experiencia que borrar".encode("utf-8") in respuesta.data


def test_borrar_todas_las_experiencias_no_aparece_si_no_hay_ninguna(cliente_web):
    respuesta = cliente_web.get("/perfil")
    assert "Borrar todas".encode("utf-8") not in respuesta.data


# --------------------------------------------------------------------------
# Propuesta: los dos bloques nunca dependen de la selección de IA
# --------------------------------------------------------------------------


def _propuesta_de_prueba() -> Propuesta:
    return Propuesta(
        idioma="es",
        sobre_mi=SeleccionSobreMi(grupo_a=["a", "b", "c"], grupo_b=["d", "e", "f"], texto="Texto."),
        skills=[],
        experiencias=[],
    )


def test_la_propuesta_no_muestra_secciones_vacias(cliente_web, tmp_path: Path):
    modulo_borrador.guardar_borrador(
        tmp_path / "perfil",
        modulo_borrador.Borrador(
            vacante="vacante", empresa="ACME", puesto="Dev", propuesta=_propuesta_de_prueba()
        ),
    )
    respuesta = cliente_web.get("/propuesta")
    assert "Skills personales".encode("utf-8") not in respuesta.data
    assert "Idiomas".encode("utf-8") not in respuesta.data


def test_la_propuesta_muestra_skills_personales_e_idiomas_del_perfil(cliente_web, tmp_path: Path):
    raiz = tmp_path / "perfil"
    almacen.guardar_skill_personal(
        raiz, Skill(id="equipo", nombre=Bilingue(es="Trabajo en equipo", en="Teamwork"))
    )
    from ancla.perfil.modelo import IdiomaHablado

    almacen.guardar_idioma(
        raiz,
        IdiomaHablado(
            id="ingles",
            nombre=Bilingue(es="Inglés", en="English"),
            nivel=Bilingue(es="C1", en="C1"),
        ),
    )
    modulo_borrador.guardar_borrador(
        raiz,
        modulo_borrador.Borrador(
            vacante="vacante", empresa="ACME", puesto="Dev", propuesta=_propuesta_de_prueba()
        ),
    )

    respuesta = cliente_web.get("/propuesta")
    html = respuesta.data.decode("utf-8")
    assert "Skills personales" in html and "Trabajo en equipo" in html
    assert "Idiomas" in html and "Inglés" in html and "C1" in html


def test_skills_personales_e_idiomas_no_aparecen_entre_las_opciones_de_ajuste_de_skill(
    cliente_web, tmp_path: Path
):
    """El desplegable de «Cambiar» skill técnica en Propuesta solo puede
    ofrecer skills técnicas — si ofreciera una personal, el usuario podría
    colarla ahí con un clic, rompiendo la separación."""
    raiz = tmp_path / "perfil"
    almacen.guardar_skill(raiz, Skill(id="python", nombre=Bilingue(es="Python", en="Python")))
    almacen.guardar_skill_personal(
        raiz, Skill(id="liderazgo", nombre=Bilingue(es="Liderazgo", en="Leadership"))
    )
    propuesta = Propuesta(
        idioma="es",
        sobre_mi=SeleccionSobreMi(grupo_a=["a", "b", "c"], grupo_b=["d", "e", "f"], texto="Texto."),
        skills=["python"],
        experiencias=[],
    )
    modulo_borrador.guardar_borrador(
        raiz, modulo_borrador.Borrador(vacante="v", empresa="ACME", puesto="Dev", propuesta=propuesta)
    )

    respuesta = cliente_web.get("/propuesta")
    html = respuesta.data.decode("utf-8")
    # "Liderazgo" solo puede aparecer en el bloque de solo lectura de skills
    # personales, nunca dentro de un <option> del selector de ajuste.
    assert 'value="liderazgo"' not in html


# --------------------------------------------------------------------------
# Guardar en Mis CVs: captura la hora, no solo la fecha
# --------------------------------------------------------------------------


def test_guardar_la_propuesta_captura_la_hora(cliente_web, tmp_path: Path):
    raiz = tmp_path / "perfil"
    modulo_borrador.guardar_borrador(
        raiz,
        modulo_borrador.Borrador(
            vacante="vacante", empresa="ACME", puesto="Dev", propuesta=_propuesta_de_prueba()
        ),
    )

    cliente_web.post("/propuesta/guardar", data={"empresa": "ACME", "puesto": "Dev"})

    from ancla.archivo import repositorio

    guardados = repositorio.listar(raiz)
    assert len(guardados) == 1
    assert guardados[0].hora is not None


# --------------------------------------------------------------------------
# Plantillas: pantalla secundaria, enlazada desde el pie y desde Propuesta
# --------------------------------------------------------------------------


def test_la_pantalla_de_plantillas_enlaza_las_dos_plantillas(cliente_web):
    from ancla.web.vistas.plantillas import (
        URL_CORPORATIVA_CLASICA,
        URL_MINIMALISTA_CALIDA,
    )

    respuesta = cliente_web.get("/plantillas")
    assert respuesta.status_code == 200
    html = respuesta.data.decode("utf-8")
    assert URL_MINIMALISTA_CALIDA in html
    assert URL_CORPORATIVA_CLASICA in html


def test_el_encabezado_de_cualquier_pantalla_enlaza_a_plantillas(cliente_web):
    respuesta = cliente_web.get("/perfil")
    assert b'href="/plantillas"' in respuesta.data


def test_el_pie_ya_no_repite_los_enlaces_del_encabezado(cliente_web):
    """Estaban duplicados y podían confundir: ahora solo viven en la cabecera."""
    respuesta = cliente_web.get("/perfil")
    assert b"Contactar soporte" not in respuesta.data
    assert "Plantillas de Canva".encode("utf-8") not in respuesta.data


def test_la_propuesta_enlaza_a_plantillas_junto_a_copiar_todo(cliente_web, tmp_path: Path):
    modulo_borrador.guardar_borrador(
        tmp_path / "perfil",
        modulo_borrador.Borrador(
            vacante="vacante", empresa="ACME", puesto="Dev", propuesta=_propuesta_de_prueba()
        ),
    )
    respuesta = cliente_web.get("/propuesta")
    assert b'href="/plantillas"' in respuesta.data
