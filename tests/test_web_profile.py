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
    AboutMe,
    Bilingual,
    Experience,
    SpokenLanguage,
    Proposal,
    SelectedAboutMe,
    Skill,
)
from ancla.web import draft as modulo_borrador
from ancla.web import settings as modulo_ajustes
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
            "centro": "UEMC",
            "periodo": "2023 — 2027",
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
            "centro": "",
            "periodo": "2023",
        },
    )
    assert "falta el centro".encode("utf-8") in respuesta.data


def test_borrar_educacion_la_quita_del_perfil(cliente_web, tmp_path: Path):
    cliente_web.post(
        "/perfil/educacion/nueva",
        data={
            "titulo_es": "Máster", "titulo_en": "Master's", "id": "master",
            "centro": "UEMC",
            "periodo": "2027",
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
            period="2024",
            bullets=Bilingual(es=["Hecho 1"], en=["Done 1"]),
            stack="Python",
        ),
    )
    store.save_experience(
        root,
        Experience(
            id="proyecto-2",
            title=Bilingual(es="Proyecto 2", en="Project 2"),
            period="2025",
            bullets=Bilingual(es=["Hecho 2"], en=["Done 2"]),
            stack="SQL",
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
            period="2024",
            bullets=Bilingual(es=["Bullet A"], en=["Bullet A EN"]),
            stack="Stack A",
            keywords=["a"],
        ),
    )
    store.save_experience(
        root,
        Experience(
            id="proyecto-b",
            title=Bilingual(es="Proyecto B", en="Project B"),
            period="2025",
            bullets=Bilingual(es=["Bullet B"], en=["Bullet B EN"]),
            stack="Stack B",
            keywords=["b"],
        ),
    )

    respuesta = cliente_web.post(
        "/perfil/experiencias/proyecto-a/editar",
        data={
            "titulo_es": "Proyecto A editado",
            "titulo_en": "Project A edited",
            "periodo": "2024",
            "bullets_es": "Bullet A nuevo",
            "bullets_en": "Bullet A new",
            "stack": "Stack A nuevo",
            "keywords": "a, nuevo",
        },
    )
    assert respuesta.status_code == 302

    perfil = store.load_profile(root)
    b = perfil.experience("proyecto-b")
    assert b.title["es"] == "Proyecto B"
    assert b.bullets["es"] == ["Bullet B"]
    assert b.stack == "Stack B"

    # Editing B right after must not revert or touch A either.
    cliente_web.post(
        "/perfil/experiencias/proyecto-b/editar",
        data={
            "titulo_es": "Proyecto B editado",
            "titulo_en": "Project B edited",
            "periodo": "2025",
            "bullets_es": "Bullet B nuevo",
            "bullets_en": "Bullet B new",
            "stack": "Stack B nuevo",
            "keywords": "b, nuevo",
        },
    )

    perfil = store.load_profile(root)
    a = perfil.experience("proyecto-a")
    assert a.title["es"] == "Proyecto A editado"
    assert a.bullets["es"] == ["Bullet A nuevo"]
    assert a.stack == "Stack A nuevo"


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


# --------------------------------------------------------------------------
# "About me" template
# --------------------------------------------------------------------------


def test_la_ayuda_del_sobre_mi_nombra_los_huecos_que_el_sistema_reconoce(cliente_web):
    """The gaps are written in two places —`modelo.py` and this form's help
    text— and the user has to type them by hand, character for character.
    They drifted apart once (the help said `{GRUPO_A_1}`, the system only
    accepted `{GROUP_A_1}`), which left anyone following the on-screen
    instructions unable to save. This ties the two together."""
    html = cliente_web.get("/perfil/sobre-mi").data.decode("utf-8")

    for hueco in AboutMe(template=Bilingual(es="", en="")).gaps():
        assert hueco in html


def test_el_sobre_mi_escrito_siguiendo_la_ayuda_se_guarda(cliente_web, tmp_path: Path):
    """The path of someone starting with an empty profile: they read the
    help, copy the gaps as shown, and save."""
    plantilla = (
        "Desarrollador con base en {GROUP_A_1}, {GROUP_A_2} y {GROUP_A_3}, "
        "que trabaja con {GROUP_B_1}, {GROUP_B_2} y {GROUP_B_3}."
    )

    respuesta = cliente_web.post(
        "/perfil/sobre-mi",
        data={"plantilla_es": plantilla, "plantilla_en": plantilla},
    )

    assert respuesta.status_code == 302
    assert store.load_profile(tmp_path / "perfil").about_me.template["es"] == plantilla


def test_la_pantalla_del_sobre_mi_trae_un_boton_por_hueco(cliente_web):
    """La vía sin IA: los seis huecos se marcan seleccionando texto y pulsando
    su botón, sin clave de API y sin ninguna llamada. Es lo que garantiza que
    la pantalla se pueda completar aunque no haya proveedor."""
    html = cliente_web.get("/perfil/sobre-mi").data.decode("utf-8")

    for hueco in AboutMe(template=Bilingual(es="", en="")).gaps():
        assert f'data-hueco="{hueco}"' in html


def test_proponer_huecos_sin_clave_devuelve_el_texto_intacto_y_avisa(cliente_web):
    respuesta = cliente_web.post(
        "/perfil/sobre-mi/huecos",
        json={"plantilla_es": "Trabajo con Python.", "plantilla_en": "I work with Python."},
    )

    assert respuesta.status_code == 200
    datos = respuesta.get_json()
    assert datos["plantilla_es"] == "Trabajo con Python."
    assert datos["avisos"]


def test_proponer_huecos_no_le_ensena_al_modelo_skills_personales_ni_idiomas(
    cliente_web, monkeypatch, tmp_path: Path
):
    """Regla 7 comprobada en el camino real, no prometida: los dos catálogos
    aparte no pueden llegar a ningún prompt."""
    import ancla.web.views.profile as vista_perfil

    cliente_web.post(
        "/perfil/skills-personales/nueva",
        data={"nombre_es": "Trabajo en equipo", "nombre_en": "Teamwork", "keywords": "team"},
    )
    cliente_web.post(
        "/perfil/idiomas/nuevo",
        data={
            "nombre_es": "Alemán",
            "nombre_en": "German",
            "nivel_es": "B2",
            "nivel_en": "B2",
            "keywords": "aleman",
        },
    )
    cliente_web.post(
        "/perfil/skills/nueva",
        data={"nombre_es": "Python", "nombre_en": "Python", "categoria": "lenguaje", "keywords": "python"},
    )
    cliente_web.post("/ajustes", data={"proveedor": "groq", "clave_api": "gsk_test123"})

    perfil = store.load_profile(tmp_path / "perfil")
    assert perfil.personal_skills and perfil.languages and perfil.skills

    peticiones: list[str] = []

    class ClienteEspia:
        def available(self):
            return True

        def complete(self, sistema, usuario):
            peticiones.append(sistema + "\n" + usuario)
            return "{}"

    monkeypatch.setattr(
        vista_perfil, "create_client", lambda *args, **kwargs: ClienteEspia()
    )

    cliente_web.post(
        "/perfil/sobre-mi/huecos",
        json={
            "plantilla_es": "Trabajo con Python.",
            "plantilla_en": "I work with Python.",
        },
    )

    assert peticiones, "no se ha llegado a llamar al modelo"
    enviado = peticiones[0]
    assert "Python" in enviado
    for prohibido in ("Trabajo en equipo", "Teamwork", "Alemán", "German"):
        assert prohibido not in enviado


# --------------------------------------------------------------------------
# Importing a CV as the way into an empty profile
# --------------------------------------------------------------------------


def _configure_key(tmp_path: Path) -> None:
    modulo_ajustes.save_settings(
        modulo_ajustes.Settings(proveedor="groq", clave_api="gsk-de-prueba"),
        tmp_path / "ajustes.json",
    )


def test_un_perfil_vacio_abre_con_el_formulario_de_importar(cliente_web, tmp_path: Path):
    _configure_key(tmp_path)

    html = cliente_web.get("/perfil").data.decode("utf-8")

    assert 'name="fichero"' in html
    assert 'action="/perfil/importar"' in html


def test_sin_clave_configurada_el_perfil_vacio_no_ensena_un_formulario_condenado(
    cliente_web, tmp_path: Path
):
    """A file input cannot be repopulated from the server, so offering the
    form without a key would throw away the file the user just chose."""
    html = cliente_web.get("/perfil").data.decode("utf-8")

    assert 'name="fichero"' not in html
    assert "/ajustes" in html


def test_con_datos_el_perfil_ofrece_importar_sin_incrustar_el_formulario(
    cliente_web, tmp_path: Path
):
    _configure_key(tmp_path)
    store.save_skill(
        tmp_path / "perfil",
        Skill(id="python", name=Bilingual(es="Python", en="Python"), category="lenguaje"),
    )

    html = cliente_web.get("/perfil").data.decode("utf-8")

    assert 'name="fichero"' not in html
    assert 'href="/perfil/importar"' in html


def test_la_pantalla_de_importar_tampoco_ensena_el_formulario_sin_clave(cliente_web):
    """Same dead end as on the profile card, reached by URL instead: the
    screen is linkable and bookmarkable, so the check cannot live only in
    the card that usually opens it."""
    html = cliente_web.get("/perfil/importar").data.decode("utf-8")

    assert 'name="fichero"' not in html
    assert "/ajustes" in html


def test_la_pantalla_de_importar_ensena_el_formulario_con_clave(cliente_web, tmp_path: Path):
    _configure_key(tmp_path)

    html = cliente_web.get("/perfil/importar").data.decode("utf-8")

    assert 'name="fichero"' in html
