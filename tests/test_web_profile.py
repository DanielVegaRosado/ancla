"""HTTP tests for personal skills, languages, and how they show up in
Proposal.

The reason for all this: personal skills and languages never go through
the selection engine, so the only way to really check that the interface
keeps them out of "About me" and out of technical skills —just as Daniel
asked— is to test it through the real routes, not only at the
`formato.py` level.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from ancla.profile import store
from ancla.profile.model import (
    Bilingual,
    Experience,
    SpokenLanguage,
    Proposal,
    SelectedAboutMe,
    Skill,
)
from ancla.web import draft as modulo_borrador
from ancla.web import create_app


@pytest.fixture
def cliente_web(tmp_path: Path):
    app = create_app(raiz_perfil=tmp_path / "perfil", settings_path=tmp_path / "ajustes.json")
    app.config["TESTING"] = True
    return app.test_client()


# --------------------------------------------------------------------------
# Personal skills
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
    """Unlike the technical-skills form."""
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
    perfil = store.load_profile(tmp_path / "perfil")
    assert perfil.personal_skill("liderazgo").name["es"] == "Liderazgo de equipos"


def test_borrar_skill_personal_la_quita_del_perfil(cliente_web, tmp_path: Path):
    cliente_web.post(
        "/perfil/skills-personales/nueva",
        data={"nombre_es": "Empatía", "nombre_en": "Empathy", "keywords": "empathy"},
    )
    cliente_web.post("/perfil/skills-personales/empatia/borrar")
    perfil = store.load_profile(tmp_path / "perfil")
    assert perfil.personal_skill("empatia") is None


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
# Languages
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
    perfil = store.load_profile(tmp_path / "perfil")
    assert perfil.language("aleman") is None


def test_editar_un_idioma_que_no_existe_avisa_y_redirige(cliente_web):
    respuesta = cliente_web.get("/perfil/idiomas/no-existe/editar", follow_redirects=True)
    assert "No existe el idioma".encode("utf-8") in respuesta.data


# --------------------------------------------------------------------------
# Education
# --------------------------------------------------------------------------


def test_crear_educacion_la_deja_ver_en_mi_perfil(cliente_web):
    respuesta = cliente_web.post(
        "/perfil/educacion/nueva",
        data={
            "titulo_es": "Grado en Ingeniería Informática",
            "titulo_en": "BSc in Computer Engineering",
            "centro_es": "UEMC",
            "centro_en": "UEMC",
            "periodo_es": "2023 — 2027",
            "periodo_en": "2023 — 2027",
        },
        follow_redirects=True,
    )
    assert respuesta.status_code == 200
    assert "Ingeniería Informática".encode("utf-8") in respuesta.data


def test_crear_educacion_sin_centro_muestra_el_error(cliente_web):
    respuesta = cliente_web.post(
        "/perfil/educacion/nueva",
        data={
            "titulo_es": "Grado", "titulo_en": "Degree",
            "centro_es": "", "centro_en": "UEMC",
            "periodo_es": "2023", "periodo_en": "2023",
        },
    )
    assert "falta el centro en español".encode("utf-8") in respuesta.data


def test_borrar_educacion_la_quita_del_perfil(cliente_web, tmp_path: Path):
    cliente_web.post(
        "/perfil/educacion/nueva",
        data={
            "titulo_es": "Máster", "titulo_en": "Master's", "id": "master",
            "centro_es": "UEMC", "centro_en": "UEMC",
            "periodo_es": "2027", "periodo_en": "2027",
        },
    )
    cliente_web.post("/perfil/educacion/master/borrar")
    perfil = store.load_profile(tmp_path / "perfil")
    assert perfil.education_entry("master") is None


def test_editar_una_educacion_que_no_existe_avisa_y_redirige(cliente_web):
    respuesta = cliente_web.get("/perfil/educacion/no-existe/editar", follow_redirects=True)
    assert "No existe la educación".encode("utf-8") in respuesta.data


# --------------------------------------------------------------------------
# Contact
# --------------------------------------------------------------------------


def test_guardar_contacto_lo_deja_ver_en_mi_perfil(cliente_web, tmp_path: Path):
    respuesta = cliente_web.post(
        "/perfil/contacto",
        data={
            "nombre": "Daniel Vega",
            "titular_es": "Ingeniero Informático",
            "titular_en": "Computer Engineer",
            "lineas": "+34 600 000 000\ntu@email.com",
        },
        follow_redirects=True,
    )
    assert respuesta.status_code == 200
    perfil = store.load_profile(tmp_path / "perfil")
    assert perfil.name == "Daniel Vega"
    assert perfil.contact == ["+34 600 000 000", "tu@email.com"]
    assert perfil.headline == Bilingual(es="Ingeniero Informático", en="Computer Engineer")
    assert "tu@email.com".encode("utf-8") in respuesta.data
    assert "Ingeniero Inform".encode("utf-8") in respuesta.data
    assert "Daniel Vega".encode("utf-8") in respuesta.data


# --------------------------------------------------------------------------
# Photo
# --------------------------------------------------------------------------


def test_subir_foto_la_guarda_en_el_perfil(cliente_web, tmp_path: Path):
    from io import BytesIO

    respuesta = cliente_web.post(
        "/perfil/foto",
        data={"foto": (BytesIO(b"contenido-de-imagen-falso"), "mi-foto.png")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert respuesta.status_code == 200
    perfil = store.load_profile(tmp_path / "perfil")
    assert perfil.photo == "photo.png"


def test_subir_foto_sin_fichero_avisa_sin_fallar(cliente_web):
    respuesta = cliente_web.post("/perfil/foto", data={}, follow_redirects=True)
    assert respuesta.status_code == 200
    assert "No se ha seleccionado ninguna foto".encode("utf-8") in respuesta.data


def test_borrar_foto_la_quita_del_perfil(cliente_web, tmp_path: Path):
    from io import BytesIO

    cliente_web.post(
        "/perfil/foto",
        data={"foto": (BytesIO(b"contenido"), "foto.jpg")},
        content_type="multipart/form-data",
    )
    cliente_web.post("/perfil/foto/borrar")
    perfil = store.load_profile(tmp_path / "perfil")
    assert perfil.photo == ""


def test_la_ruta_de_archivo_de_foto_da_404_sin_foto(cliente_web):
    respuesta = cliente_web.get("/perfil/foto/archivo")
    assert respuesta.status_code == 404


# --------------------------------------------------------------------------
# Bulk delete: clearing an entire section at once, not just one by one
# --------------------------------------------------------------------------


def test_borrar_todas_las_experiencias_las_quita_todas(cliente_web, tmp_path: Path):
    root = tmp_path / "perfil"
    store.save_experience(
        root,
        Experience(
            id="proyecto-1",
            title=Bilingual(es="Proyecto 1", en="Project 1"),
            period=Bilingual(es="2024", en="2024"),
            bullets=Bilingual(es=["Hecho 1"], en=["Done 1"]),
            stack=Bilingual(es="Python", en="Python"),
        ),
    )
    store.save_experience(
        root,
        Experience(
            id="proyecto-2",
            title=Bilingual(es="Proyecto 2", en="Project 2"),
            period=Bilingual(es="2025", en="2025"),
            bullets=Bilingual(es=["Hecho 2"], en=["Done 2"]),
            stack=Bilingual(es="SQL", en="SQL"),
        ),
    )

    respuesta = cliente_web.post("/perfil/experiencias/borrar-todas", follow_redirects=True)

    assert respuesta.status_code == 200
    assert "2 experiencia(s) borradas".encode("utf-8") in respuesta.data
    assert store.load_profile(root).experiences == []


def test_editar_una_experiencia_no_contamina_otra(cliente_web, tmp_path: Path):
    """Regression: two experiences in Daniel's real profile (ml-developer and
    data-engineer) turned up with cross-contaminated content — one's
    bullet/stack showing up inside the other. No path through the code was
    found that could cause it (the id always comes from the URL,
    `guardar_experiencia` only ever writes to that id's own file), so it was
    most likely a slip while editing by hand. This test stands as proof that
    editing A, through the real HTTP route, twice in a row, never touches B —
    if it ever happens again, it is a real bug and this test catches it."""
    root = tmp_path / "perfil"
    store.save_experience(
        root,
        Experience(
            id="proyecto-a",
            title=Bilingual(es="Proyecto A", en="Project A"),
            period=Bilingual(es="2024", en="2024"),
            bullets=Bilingual(es=["Bullet A"], en=["Bullet A EN"]),
            stack=Bilingual(es="Stack A", en="Stack A"),
            keywords=["a"],
        ),
    )
    store.save_experience(
        root,
        Experience(
            id="proyecto-b",
            title=Bilingual(es="Proyecto B", en="Project B"),
            period=Bilingual(es="2025", en="2025"),
            bullets=Bilingual(es=["Bullet B"], en=["Bullet B EN"]),
            stack=Bilingual(es="Stack B", en="Stack B"),
            keywords=["b"],
        ),
    )

    respuesta = cliente_web.post(
        "/perfil/experiencias/proyecto-a/editar",
        data={
            "titulo_es": "Proyecto A editado",
            "titulo_en": "Project A edited",
            "periodo_es": "2024",
            "periodo_en": "2024",
            "bullets_es": "Bullet A nuevo",
            "bullets_en": "Bullet A new",
            "stack_es": "Stack A nuevo",
            "stack_en": "Stack A new",
            "keywords": "a, nuevo",
        },
    )
    assert respuesta.status_code == 302

    perfil = store.load_profile(root)
    b = perfil.experience("proyecto-b")
    assert b.title["es"] == "Proyecto B"
    assert b.bullets["es"] == ["Bullet B"]
    assert b.stack["es"] == "Stack B"

    # Editing B right after must not revert or touch A either.
    cliente_web.post(
        "/perfil/experiencias/proyecto-b/editar",
        data={
            "titulo_es": "Proyecto B editado",
            "titulo_en": "Project B edited",
            "periodo_es": "2025",
            "periodo_en": "2025",
            "bullets_es": "Bullet B nuevo",
            "bullets_en": "Bullet B new",
            "stack_es": "Stack B nuevo",
            "stack_en": "Stack B new",
            "keywords": "b, nuevo",
        },
    )

    perfil = store.load_profile(root)
    a = perfil.experience("proyecto-a")
    assert a.title["es"] == "Proyecto A editado"
    assert a.bullets["es"] == ["Bullet A nuevo"]
    assert a.stack["es"] == "Stack A nuevo"


def test_borrar_todas_las_skills_tecnicas_no_toca_las_personales(cliente_web, tmp_path: Path):
    root = tmp_path / "perfil"
    store.save_skill(root, Skill(id="python", name=Bilingual(es="Python", en="Python")))
    store.save_personal_skill(
        root, Skill(id="empatia", name=Bilingual(es="Empatía", en="Empathy"))
    )

    cliente_web.post("/perfil/skills/borrar-todas")

    perfil = store.load_profile(root)
    assert perfil.skills == []
    assert perfil.personal_skill("empatia") is not None


def test_borrar_todas_las_skills_personales_las_quita_todas(cliente_web, tmp_path: Path):
    root = tmp_path / "perfil"
    store.save_personal_skill(
        root, Skill(id="empatia", name=Bilingual(es="Empatía", en="Empathy"))
    )

    respuesta = cliente_web.post(
        "/perfil/skills-personales/borrar-todas", follow_redirects=True
    )

    assert "1 skill(s) personal(es) borradas".encode("utf-8") in respuesta.data
    assert store.load_profile(root).personal_skills == []


def test_borrar_todos_los_idiomas_los_quita_todos(cliente_web, tmp_path: Path):
    root = tmp_path / "perfil"
    store.save_language(
        root,
        SpokenLanguage(
            id="ingles",
            name=Bilingual(es="Inglés", en="English"),
            level=Bilingual(es="C1", en="C1"),
        ),
    )

    respuesta = cliente_web.post("/perfil/idiomas/borrar-todos", follow_redirects=True)

    assert "1 idioma(s) borrados".encode("utf-8") in respuesta.data
    assert store.load_profile(root).languages == []


def test_borrar_todas_sobre_una_seccion_vacia_avisa_sin_fallar(cliente_web):
    respuesta = cliente_web.post("/perfil/experiencias/borrar-todas", follow_redirects=True)
    assert "No había ninguna experiencia que borrar".encode("utf-8") in respuesta.data


def test_borrar_todas_las_experiencias_no_aparece_si_no_hay_ninguna(cliente_web):
    respuesta = cliente_web.get("/perfil")
    assert "Borrar todas".encode("utf-8") not in respuesta.data


# --------------------------------------------------------------------------
# Proposal: the two blocks never depend on the AI's selection
# --------------------------------------------------------------------------


def _propuesta_de_prueba() -> Proposal:
    return Proposal(
        language="es",
        about_me=SelectedAboutMe(group_a=["a", "b", "c"], group_b=["d", "e", "f"], text="Texto."),
        skills=[],
        experiences=[],
    )


def test_la_propuesta_no_muestra_secciones_vacias(cliente_web, tmp_path: Path):
    modulo_borrador.save_draft(
        tmp_path / "perfil",
        modulo_borrador.Draft(
            vacante="vacante", empresa="ACME", puesto="Dev", propuesta=_propuesta_de_prueba()
        ),
    )
    respuesta = cliente_web.get("/propuesta")
    assert "Skills personales".encode("utf-8") not in respuesta.data
    assert "Idiomas".encode("utf-8") not in respuesta.data


def test_la_propuesta_muestra_skills_personales_e_idiomas_del_perfil(cliente_web, tmp_path: Path):
    root = tmp_path / "perfil"
    store.save_personal_skill(
        root, Skill(id="equipo", name=Bilingual(es="Trabajo en equipo", en="Teamwork"))
    )
    from ancla.profile.model import SpokenLanguage

    store.save_language(
        root,
        SpokenLanguage(
            id="ingles",
            name=Bilingual(es="Inglés", en="English"),
            level=Bilingual(es="C1", en="C1"),
        ),
    )
    modulo_borrador.save_draft(
        root,
        modulo_borrador.Draft(
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
    """The "Change" dropdown for a technical skill in Proposal can only
    offer technical skills — if it offered a personal one, the user could
    slip it in there with a single click, breaking the separation."""
    root = tmp_path / "perfil"
    store.save_skill(root, Skill(id="python", name=Bilingual(es="Python", en="Python")))
    store.save_personal_skill(
        root, Skill(id="liderazgo", name=Bilingual(es="Liderazgo", en="Leadership"))
    )
    propuesta = Proposal(
        language="es",
        about_me=SelectedAboutMe(group_a=["a", "b", "c"], group_b=["d", "e", "f"], text="Texto."),
        skills=["python"],
        experiences=[],
    )
    modulo_borrador.save_draft(
        root, modulo_borrador.Draft(vacante="v", empresa="ACME", puesto="Dev", propuesta=propuesta)
    )

    respuesta = cliente_web.get("/propuesta")
    html = respuesta.data.decode("utf-8")
    # "Liderazgo" can only appear in the read-only personal-skills block,
    # never inside an <option> of the adjustment selector.
    assert 'value="liderazgo"' not in html


# --------------------------------------------------------------------------
# Saving to My CVs: captures the time, not just the date
# --------------------------------------------------------------------------


def test_guardar_la_propuesta_captura_la_hora(cliente_web, tmp_path: Path):
    root = tmp_path / "perfil"
    modulo_borrador.save_draft(
        root,
        modulo_borrador.Draft(
            vacante="vacante", empresa="ACME", puesto="Dev", propuesta=_propuesta_de_prueba()
        ),
    )

    cliente_web.post("/propuesta/guardar", data={"empresa": "ACME", "puesto": "Dev"})

    from ancla.archive import repository

    guardados = repository.list_all(root)
    assert len(guardados) == 1
    assert guardados[0].time is not None


def test_el_encabezado_de_cualquier_pantalla_enlaza_a_plantillas(cliente_web):
    respuesta = cliente_web.get("/perfil")
    assert b'href="/plantillas"' in respuesta.data


def test_el_pie_ya_no_repite_los_enlaces_del_encabezado(cliente_web):
    """They used to be duplicated and could confuse people: now they only
    live in the header."""
    respuesta = cliente_web.get("/perfil")
    assert b"Contactar soporte" not in respuesta.data
    assert "Plantillas de Canva".encode("utf-8") not in respuesta.data


def test_la_propuesta_enlaza_a_plantillas_junto_a_copiar_todo(cliente_web, tmp_path: Path):
    modulo_borrador.save_draft(
        tmp_path / "perfil",
        modulo_borrador.Draft(
            vacante="vacante", empresa="ACME", puesto="Dev", propuesta=_propuesta_de_prueba()
        ),
    )
    respuesta = cliente_web.get("/propuesta")
    assert b'href="/plantillas"' in respuesta.data
