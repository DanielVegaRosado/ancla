"""Tests for the Import screen: the import's ephemeral state and the HTTP
routes end to end (upload, review, save the selected ones, discard).
"""
from __future__ import annotations

import io
from pathlib import Path

import pytest

from ancla.profile import store
from ancla.profile.model import AboutMe, Bilingual, Education, Experience, SpokenLanguage, Skill
from ancla.web import create_app
from ancla.web import import_batch as modulo_importacion


@pytest.fixture
def cliente_web(tmp_path: Path):
    app = create_app(raiz_perfil=tmp_path / "perfil", settings_path=tmp_path / "ajustes.json")
    app.config["TESTING"] = True
    return app.test_client()


def _experiencia(id: str = "ml-dev") -> Experience:
    return Experience(
        id=id,
        title=Bilingual(es="ML Developer", en="ML Developer"),
        period_start="2026", period_end="",
        bullets=Bilingual(es=["Pipeline completo"], en=["Full pipeline"]),
        stack="Python",
        keywords=["ml"],
    )


def _skill(id: str = "python") -> Skill:
    return Skill(id=id, name=Bilingual(es="Python", en="Python"), category="lenguaje", keywords=["py"])


def _skill_personal(id: str = "equipo") -> Skill:
    return Skill(id=id, name=Bilingual(es="Trabajo en equipo", en="Teamwork"), keywords=["team player"])


def _idioma(id: str = "ingles") -> SpokenLanguage:
    return SpokenLanguage(
        id=id,
        name=Bilingual(es="Inglés", en="English"),
        level=Bilingual(es="C1", en="C1"),
        keywords=["advanced english"],
    )


def _educacion(id: str = "grado") -> Education:
    return Education(
        id=id,
        title=Bilingual(es="Grado en Ingeniería Informática", en="BSc in Computer Engineering"),
        institution="UEMC",
        period_start="2021",
        period_end="2025",
    )


# --------------------------------------------------------------------------
# web/importacion.py: ephemeral state, round trip
# --------------------------------------------------------------------------


def test_sin_importacion_guardada_no_hay_nada_que_cargar(tmp_path: Path):
    assert modulo_importacion.load_import(tmp_path) is None


def test_guardar_y_cargar_importacion_hace_ida_y_vuelta(tmp_path: Path):
    original = modulo_importacion.ImportBatch(
        experiencias=[_experiencia()], skills=[_skill()], avisos=["ojo con esto"]
    )
    modulo_importacion.save_import(tmp_path, original)
    recargada = modulo_importacion.load_import(tmp_path)
    assert recargada == original


def test_guardar_y_cargar_el_resto_pendiente_hace_ida_y_vuelta(tmp_path: Path):
    original = modulo_importacion.ImportBatch(
        skills=[_skill()], resto="EDUCACIÓN\nGrado en Ingeniería\n"
    )
    modulo_importacion.save_import(tmp_path, original)
    recargada = modulo_importacion.load_import(tmp_path)
    assert recargada == original


def test_borrar_importacion_la_deja_indisponible(tmp_path: Path):
    modulo_importacion.save_import(
        tmp_path, modulo_importacion.ImportBatch(experiencias=[_experiencia()])
    )
    modulo_importacion.delete_import(tmp_path)
    assert modulo_importacion.load_import(tmp_path) is None


def test_borrar_importacion_sin_fichero_no_falla(tmp_path: Path):
    modulo_importacion.delete_import(tmp_path)  # no debe lanzar


def test_un_fichero_de_importacion_corrupto_no_revienta(tmp_path: Path):
    (tmp_path / modulo_importacion.NOMBRE_FICHERO).write_text("esto no es JSON", encoding="utf-8")
    assert modulo_importacion.load_import(tmp_path) is None


# --------------------------------------------------------------------------
# HTTP routes
# --------------------------------------------------------------------------


def test_ver_importar(cliente_web):
    respuesta = cliente_web.get("/perfil/importar")
    assert respuesta.status_code == 200
    assert "Importar".encode("utf-8") in respuesta.data


def test_importar_sin_fichero_ni_texto_pide_uno_de_los_dos(cliente_web):
    respuesta = cliente_web.post("/perfil/importar", data={"texto": ""})
    assert respuesta.status_code == 200
    assert "Sube un fichero o pega el texto".encode("utf-8") in respuesta.data


def test_importar_sin_clave_configurada_redirige_a_ajustes(cliente_web):
    respuesta = cliente_web.post(
        "/perfil/importar", data={"texto": "Un CV cualquiera con suficiente texto."}
    )
    assert respuesta.status_code == 302
    assert respuesta.location.endswith("/ajustes")


def test_revisar_sin_importacion_pendiente_redirige_a_importar(cliente_web):
    respuesta = cliente_web.get("/perfil/importar/revisar", follow_redirects=True)
    assert "No hay ninguna importación pendiente".encode("utf-8") in respuesta.data


def test_revisar_muestra_las_candidatas_guardadas(cliente_web, tmp_path: Path):
    modulo_importacion.save_import(
        tmp_path / "perfil",
        modulo_importacion.ImportBatch(experiencias=[_experiencia()], skills=[_skill()]),
    )
    respuesta = cliente_web.get("/perfil/importar/revisar")
    assert "ML Developer".encode("utf-8") in respuesta.data
    assert "Python".encode("utf-8") in respuesta.data


def test_guardar_solo_lo_marcado(cliente_web, tmp_path: Path):
    root = tmp_path / "perfil"
    modulo_importacion.save_import(
        root,
        modulo_importacion.ImportBatch(
            experiencias=[_experiencia("uno"), _experiencia("dos")], skills=[_skill()]
        ),
    )
    cliente_web.post(
        "/perfil/importar/guardar",
        data={
            "exp-0": "1",
            "exp-0-titulo_es": "ML Developer",
            "exp-0-titulo_en": "ML Developer",
            "exp-0-periodo": "2026",
            "exp-0-bullets_es": "Pipeline completo",
            "exp-0-bullets_en": "Full pipeline",
            "exp-0-stack": "Python",
            # "exp-1" no viene en el formulario: no estaba marcado
        },
    )
    perfil = store.load_profile(root)
    assert perfil.experience("uno") is not None
    assert perfil.experience("dos") is None
    assert perfil.skill("python") is None  # tampoco estaba marcado


def test_guardar_permite_editar_antes_de_confirmar(cliente_web, tmp_path: Path):
    root = tmp_path / "perfil"
    modulo_importacion.save_import(
        root, modulo_importacion.ImportBatch(skills=[_skill()])
    )
    cliente_web.post(
        "/perfil/importar/guardar",
        data={
            "skill-0": "1",
            "skill-0-nombre_es": "Python avanzado",
            "skill-0-nombre_en": "Advanced Python",
            "skill-0-categoria": "lenguaje",
        },
    )
    perfil = store.load_profile(root)
    assert perfil.skill("python").name["es"] == "Python avanzado"


def test_una_candidata_incompleta_no_se_guarda_pero_avisa(cliente_web, tmp_path: Path):
    """If the name gets erased in every language while editing, normal
    validation rejects it — just like in the manual form — instead of saving
    it broken. Erasing only one of the two languages does not: that is an
    entry waiting for a translation, and it is the case the whole
    single-language import exists for."""
    root = tmp_path / "perfil"
    modulo_importacion.save_import(
        root, modulo_importacion.ImportBatch(skills=[_skill()])
    )
    respuesta = cliente_web.post(
        "/perfil/importar/guardar",
        data={"skill-0": "1", "skill-0-nombre_es": "", "skill-0-nombre_en": ""},
        follow_redirects=True,
    )
    perfil = store.load_profile(root)
    assert perfil.skill("python") is None
    assert "no se pudieron guardar".encode("utf-8") in respuesta.data


def test_guardar_una_skill_personal_importada_va_al_catalogo_correcto(cliente_web, tmp_path: Path):
    """Real case that prompted this: a "PERSONAL" section of the CV (Trabajo
    en equipo, Team player...) has to end up in personal_skills, never mixed
    in with technical skills."""
    root = tmp_path / "perfil"
    modulo_importacion.save_import(
        root, modulo_importacion.ImportBatch(skills_personales=[_skill_personal()])
    )
    cliente_web.post(
        "/perfil/importar/guardar",
        data={
            "skillpersonal-0": "1",
            "skillpersonal-0-nombre_es": "Trabajo en equipo",
            "skillpersonal-0-nombre_en": "Teamwork",
        },
    )
    perfil = store.load_profile(root)
    assert perfil.personal_skill("equipo") is not None
    assert perfil.skill("equipo") is None  # nunca en el catálogo técnico


def test_guardar_un_idioma_importado(cliente_web, tmp_path: Path):
    root = tmp_path / "perfil"
    modulo_importacion.save_import(
        root, modulo_importacion.ImportBatch(idiomas=[_idioma()])
    )
    cliente_web.post(
        "/perfil/importar/guardar",
        data={
            "idioma-0": "1",
            "idioma-0-nombre_es": "Inglés",
            "idioma-0-nombre_en": "English",
            "idioma-0-nivel_es": "C1 Avanzado",
            "idioma-0-nivel_en": "C1 Advanced",
        },
    )
    perfil = store.load_profile(root)
    assert perfil.language("ingles") is not None
    assert perfil.language("ingles").level["es"] == "C1 Avanzado"


def test_una_skill_personal_o_idioma_no_marcados_no_se_guardan(cliente_web, tmp_path: Path):
    root = tmp_path / "perfil"
    modulo_importacion.save_import(
        root,
        modulo_importacion.ImportBatch(
            skills_personales=[_skill_personal()], idiomas=[_idioma()]
        ),
    )
    cliente_web.post("/perfil/importar/guardar", data={})
    perfil = store.load_profile(root)
    assert perfil.personal_skill("equipo") is None
    assert perfil.language("ingles") is None


def test_revisar_muestra_skills_personales_e_idiomas(cliente_web, tmp_path: Path):
    modulo_importacion.save_import(
        tmp_path / "perfil",
        modulo_importacion.ImportBatch(
            skills_personales=[_skill_personal()], idiomas=[_idioma()]
        ),
    )
    respuesta = cliente_web.get("/perfil/importar/revisar")
    html = respuesta.data.decode("utf-8")
    assert "Trabajo en equipo" in html
    assert "Inglés" in html and "C1" in html


def test_guardar_limpia_la_importacion_pendiente(cliente_web, tmp_path: Path):
    root = tmp_path / "perfil"
    modulo_importacion.save_import(root, modulo_importacion.ImportBatch(skills=[_skill()]))
    cliente_web.post("/perfil/importar/guardar", data={"skill-0": "1", "skill-0-nombre_es": "Python", "skill-0-nombre_en": "Python"})
    assert modulo_importacion.load_import(root) is None


def test_guardar_sin_importacion_pendiente_redirige(cliente_web):
    respuesta = cliente_web.post("/perfil/importar/guardar", data={})
    assert respuesta.status_code == 302


def test_descartar_borra_la_importacion_sin_guardar_nada(cliente_web, tmp_path: Path):
    root = tmp_path / "perfil"
    modulo_importacion.save_import(root, modulo_importacion.ImportBatch(skills=[_skill()]))
    cliente_web.post("/perfil/importar/descartar")
    assert modulo_importacion.load_import(root) is None
    assert store.load_profile(root).skill("python") is None


def test_un_perfil_vacio_abre_con_la_puerta_de_entrada_a_importar(cliente_web):
    """An empty profile leads with importing, not with a link buried in help
    text: it is the only way in that does not mean typing everything by hand.
    Without a key the card offers that step instead of the form (see
    `test_web_profile.py` for both shapes)."""
    respuesta = cliente_web.get("/perfil")
    assert "Importa tu CV".encode("utf-8") in respuesta.data


def test_un_perfil_con_datos_tambien_enlaza_a_importar_desde_mi_perfil(cliente_web, tmp_path: Path):
    """The link used to only appear with an empty profile; now it stays
    there after the first import too."""
    store.save_skill(tmp_path / "perfil", _skill())
    respuesta = cliente_web.get("/perfil")
    assert b'href="/perfil/importar"' in respuesta.data
    assert "¿Tienes otro CV que añadir?".encode("utf-8") in respuesta.data


def test_importar_cv_no_esta_en_la_cabecera(cliente_web):
    """Only lives on My profile, not in the global navigation — with
    Templates and Support already there, the header was getting too crowded."""
    respuesta = cliente_web.get("/ajustes")
    assert b'href="/perfil/importar"' not in respuesta.data


def test_subir_un_formato_no_soportado_muestra_el_error(cliente_web):
    datos = {"fichero": (io.BytesIO(b"contenido cualquiera"), "cv.txt")}
    respuesta = cliente_web.post(
        "/perfil/importar", data=datos, content_type="multipart/form-data"
    )
    assert respuesta.status_code == 200
    assert "no es un formato soportado".encode("utf-8") in respuesta.data


# --------------------------------------------------------------------------
# End to end: upload -> extract -> analyze -> review -> save.
#
# The tests above check each piece on its own (extraction, analysis with a
# fake ClienteIA, saving what was checked); this is the only one that shows
# the VIEW wires them together correctly. `create_client` is swapped for a
# double (touching neither the network nor a real key) so the whole chain
# can be tested without spending a real call.
# --------------------------------------------------------------------------


class _ClienteFalsoDisponible:
    """Always "available" and always returns the same proposal — there is
    no need to vary the response to show the view knows how to use it."""

    def __init__(self, respuesta: str):
        self.respuesta = respuesta

    def complete(self, sistema: str, usuario: str) -> str:
        return self.respuesta

    def available(self) -> bool:
        return True


def _respuesta_ia() -> str:
    import json

    return json.dumps(
        {
            "experiencias": [
                {
                    "titulo": {"es": "Ingeniera de Datos", "en": "Data Engineer"},
                    "periodo": {"es": "2025 - actualidad", "en": "2025 - present"},
                    "bullets": {
                        "es": ["Pipeline de ingesta con Airflow"],
                        "en": ["Ingestion pipeline with Airflow"],
                    },
                    "stack": {"es": "Python, Airflow", "en": "Python, Airflow"},
                    "keywords": ["airflow", "etl"],
                }
            ],
            "skills": [
                {"nombre": {"es": "SQL", "en": "SQL"}, "categoria": "dato", "keywords": ["sql"]}
            ],
            "skills_personales": [
                {
                    "nombre": {"es": "Trabajo en equipo", "en": "Teamwork"},
                    "keywords": ["team player"],
                }
            ],
            "idiomas": [
                {
                    "nombre": {"es": "Inglés", "en": "English"},
                    "nivel": {"es": "C1 Avanzado", "en": "C1 Advanced"},
                    "keywords": ["advanced english"],
                }
            ],
            "educacion": [
                {
                    "titulo": {
                        "es": "Grado en Ingeniería Informática",
                        "en": "BSc in Computer Engineering",
                    },
                    "centro": "UEMC",
                    "periodo": "2021 - 2025",
                }
            ],
        },
        ensure_ascii=False,
    )


def _docx_de_prueba() -> bytes:
    import docx

    documento = docx.Document()
    documento.add_paragraph("Ana Ejemplo — Ingeniera de Datos")
    documento.add_paragraph("2025 - actualidad: pipeline de ingesta con Airflow y Python.")
    buffer = io.BytesIO()
    documento.save(buffer)
    return buffer.getvalue()


def test_de_punta_a_punta_subir_analizar_revisar_y_guardar(cliente_web, tmp_path, monkeypatch):
    import ancla.web.views.import_cv as vista_importar

    monkeypatch.setattr(
        vista_importar,
        "create_client",
        lambda proveedor, clave, url_base="", modelo="": _ClienteFalsoDisponible(_respuesta_ia()),
    )

    # 1) Upload a real .docx.
    subida = cliente_web.post(
        "/perfil/importar",
        data={"fichero": (io.BytesIO(_docx_de_prueba()), "mi-cv.docx")},
        content_type="multipart/form-data",
    )
    assert subida.status_code == 302
    assert subida.location.endswith("/perfil/importar/revisar")

    # 2) The review screen shows what the analysis returned, not a
    #    placeholder or another test's data.
    revision = cliente_web.get("/perfil/importar/revisar")
    html = revision.data.decode("utf-8")
    assert "Ingeniera de Datos" in html
    assert "Airflow" in html
    assert "SQL" in html
    assert "Trabajo en equipo" in html
    assert "Inglés" in html
    assert "Grado en Ingeniería Informática" in html
    assert "UEMC" in html

    # 3) Save the experience and the personal skill; discard the technical
    #    skill and the language, to exercise both paths (save/discard)
    #    across all four categories at once.
    save = cliente_web.post(
        "/perfil/importar/guardar",
        data={
            "exp-0": "1",
            "exp-0-titulo_es": "Ingeniera de Datos",
            "exp-0-titulo_en": "Data Engineer",
            "exp-0-periodo": "2025 - actualidad",
            "exp-0-bullets_es": "Pipeline de ingesta con Airflow",
            "exp-0-bullets_en": "Ingestion pipeline with Airflow",
            "exp-0-stack": "Python, Airflow",
            # "skill-0" is not sent: it stays discarded.
            "skillpersonal-0": "1",
            "skillpersonal-0-nombre_es": "Trabajo en equipo",
            "skillpersonal-0-nombre_en": "Teamwork",
            # "idioma-0" is not sent: it stays discarded.
            "edu-0": "1",
            "edu-0-titulo_es": "Grado en Ingeniería Informática",
            "edu-0-titulo_en": "BSc in Computer Engineering",
            "edu-0-centro": "UEMC",
            "edu-0-periodo_inicio": "2021",
            "edu-0-periodo_fin": "2025",
        },
    )
    assert save.status_code == 302

    # 4) The real profile has the experience and the personal skill, and
    #    has NEITHER the discarded technical skill NOR the discarded language.
    perfil = store.load_profile(tmp_path / "perfil")
    experiencias = [e for e in perfil.experiences if e.title["es"] == "Ingeniera de Datos"]
    assert len(experiencias) == 1
    assert experiencias[0].bullets["es"] == ["Pipeline de ingesta con Airflow"]
    assert perfil.skill("sql") is None
    assert perfil.personal_skill("trabajo-en-equipo") is not None
    assert perfil.skill("trabajo-en-equipo") is None  # nunca en el catálogo técnico
    assert perfil.language("ingles") is None
    assert perfil.education_entry("grado-en-ingenieria-informatica") is not None

    # 5) The pending import draft is cleared: the same batch cannot be
    #    "reviewed" again, and nothing is left dangling in the profile.
    assert modulo_importacion.load_import(tmp_path / "perfil") is None


# --------------------------------------------------------------------------
# Education: the fifth category, added after the importer was written.
# --------------------------------------------------------------------------


def test_guardar_y_cargar_una_educacion_hace_ida_y_vuelta(tmp_path: Path):
    original = modulo_importacion.ImportBatch(educacion=[_educacion()])
    modulo_importacion.save_import(tmp_path, original)
    assert modulo_importacion.load_import(tmp_path) == original


def test_revisar_muestra_la_educacion(cliente_web, tmp_path: Path):
    modulo_importacion.save_import(
        tmp_path / "perfil", modulo_importacion.ImportBatch(educacion=[_educacion()])
    )
    html = cliente_web.get("/perfil/importar/revisar").data.decode("utf-8")
    assert "Grado en Ingeniería Informática" in html
    assert "UEMC" in html
    assert 'name="edu-0"' in html


def test_guardar_una_educacion_importada_va_al_perfil(cliente_web, tmp_path: Path):
    root = tmp_path / "perfil"
    modulo_importacion.save_import(
        root, modulo_importacion.ImportBatch(educacion=[_educacion()])
    )
    cliente_web.post(
        "/perfil/importar/guardar",
        data={
            "edu-0": "1",
            "edu-0-titulo_es": "Grado en Ingeniería Informática",
            "edu-0-titulo_en": "BSc in Computer Engineering",
            "edu-0-centro": "UEMC",
            "edu-0-periodo_inicio": "2021",
            "edu-0-periodo_fin": "2025",
        },
    )
    educacion = store.load_profile(root).education_entry("grado")
    assert educacion is not None
    assert educacion.institution == "UEMC"
    assert educacion.period_end == "2025"


def test_una_educacion_no_marcada_no_se_guarda(cliente_web, tmp_path: Path):
    root = tmp_path / "perfil"
    modulo_importacion.save_import(
        root, modulo_importacion.ImportBatch(educacion=[_educacion()])
    )
    cliente_web.post("/perfil/importar/guardar", data={})
    assert store.load_profile(root).education_entry("grado") is None


def test_una_educacion_sin_centro_no_se_guarda_pero_avisa(cliente_web, tmp_path: Path):
    """Same treatment as the other four categories: normal validation
    rejects it instead of writing a half-empty entry into the profile."""
    root = tmp_path / "perfil"
    modulo_importacion.save_import(
        root, modulo_importacion.ImportBatch(educacion=[_educacion()])
    )
    respuesta = cliente_web.post(
        "/perfil/importar/guardar",
        data={
            "edu-0": "1",
            "edu-0-titulo_es": "Grado en Ingeniería Informática",
            "edu-0-titulo_en": "BSc in Computer Engineering",
            "edu-0-centro": "",
            "edu-0-periodo_inicio": "2021",
        },
        follow_redirects=True,
    )
    assert store.load_profile(root).education_entry("grado") is None
    assert "no se pudieron guardar".encode("utf-8") in respuesta.data


def test_una_importacion_solo_con_educacion_llega_a_la_pantalla_de_revision(
    cliente_web, tmp_path, monkeypatch
):
    """The "nothing found" check used to look only at the other four
    categories: a CV whose only new content is a degree must not be
    reported as unreadable."""
    import ancla.web.views.import_cv as vista_importar

    import json as _json

    respuesta_ia = _json.dumps(
        {
            "experiencias": [],
            "skills": [],
            "educacion": [
                {
                    "titulo": {"es": "Máster en IA", "en": "MSc in AI"},
                    "centro": "UEMC",
                    "periodo": "2023 - actualidad",
                }
            ],
        },
        ensure_ascii=False,
    )
    monkeypatch.setattr(
        vista_importar,
        "create_client",
        lambda proveedor, clave, url_base="", modelo="": _ClienteFalsoDisponible(respuesta_ia),
    )
    subida = cliente_web.post("/perfil/importar", data={"texto": "Máster en IA, UEMC, 2023."})
    assert subida.location.endswith("/perfil/importar/revisar")


def test_un_limite_temporal_del_proveedor_se_explica_en_la_pantalla_de_importar(
    cliente_web, monkeypatch
):
    """The failure that made someone think their CV had been lost: the
    provider's per-minute allowance was spent, the screen showed nothing to
    save, and nothing said that waiting a minute was all it took."""
    import ancla.web.views.import_cv as vista_importar
    from ancla.ai.client import AIError

    class _ClienteAlLimite:
        def complete(self, sistema: str, usuario: str) -> str:
            raise AIError("Espera un minuto y vuelve a intentarlo: tu plan gratuito")

        def available(self) -> bool:
            return True

    monkeypatch.setattr(
        vista_importar,
        "create_client",
        lambda proveedor, clave, url_base="", modelo="": _ClienteAlLimite(),
    )
    respuesta = cliente_web.post(
        "/perfil/importar", data={"texto": "Daniel Vega, ML Developer."}
    )

    assert respuesta.status_code == 200
    assert "Espera un minuto y vuelve a intentarlo".encode("utf-8") in respuesta.data
    assert "no se ha encontrado".encode("utf-8") not in respuesta.data.lower()


def test_la_pantalla_de_importar_avisa_de_que_analizar_puede_esperar(cliente_web):
    """A retried request is a blocking wait with nothing on screen: the page
    has to say it is working, or it reads as frozen."""
    cliente_web.post(
        "/ajustes", data={"proveedor": "groq", "clave_api": "gsk_123"}, follow_redirects=True
    )
    respuesta = cliente_web.get("/perfil/importar")

    assert "no cierres esta página".encode("utf-8") in respuesta.data


# --------------------------------------------------------------------------
# One language in, translation as a separate step
# --------------------------------------------------------------------------


def _skill_solo_en_espanol(id: str = "python") -> Skill:
    return Skill(id=id, name=Bilingual(es="Python", en=""), category="lenguaje", keywords=["py"])


class _ClienteFalso:
    def __init__(self, respuesta: str):
        self.respuesta = respuesta
        self.llamadas: list[tuple[str, str]] = []

    def complete(self, sistema: str, usuario: str) -> str:
        self.llamadas.append((sistema, usuario))
        return self.respuesta

    def available(self) -> bool:
        return True


def test_una_candidata_en_un_solo_idioma_se_guarda(cliente_web, tmp_path: Path):
    """The reason the whole thing exists: a CV read in Spanish has to reach
    the profile without spending a call on English first."""
    root = tmp_path / "perfil"
    modulo_importacion.save_import(
        root,
        modulo_importacion.ImportBatch(skills=[_skill_solo_en_espanol()], written=["es"]),
    )

    cliente_web.post("/perfil/importar/guardar", data={"skill-0": "1"})

    guardada = store.load_profile(root).skill("python")
    assert guardada is not None
    assert guardada.name["es"] == "Python"
    assert guardada.name["en"] == ""


def test_la_revision_no_pide_el_idioma_que_no_se_ha_importado(cliente_web, tmp_path: Path):
    modulo_importacion.save_import(
        tmp_path / "perfil",
        modulo_importacion.ImportBatch(skills=[_skill_solo_en_espanol()], written=["es"]),
    )

    respuesta = cliente_web.get("/perfil/importar/revisar")

    assert b'name="skill-0-nombre_es"' in respuesta.data
    assert b'name="skill-0-nombre_en"' not in respuesta.data
    assert "Traducir al inglés".encode("utf-8") in respuesta.data


def test_traducir_la_importacion_rellena_el_otro_idioma(cliente_web, tmp_path: Path, monkeypatch):
    import json

    import ancla.web.views.import_cv as vista

    root = tmp_path / "perfil"
    modulo_importacion.save_import(
        root,
        modulo_importacion.ImportBatch(skills=[_skill_solo_en_espanol()], written=["es"]),
    )
    cliente = _ClienteFalso(json.dumps({"0": {"name": "Python"}}))
    monkeypatch.setattr(
        vista, "create_client",
        lambda proveedor, clave, url_base="", modelo="": cliente,
    )

    cliente_web.post(
        "/perfil/importar/traducir", data={"skill-0-nombre_es": "Python"}
    )

    lote = modulo_importacion.load_import(root)
    assert lote.skills[0].name["en"] == "Python"
    assert lote.skills[0].name["es"] == "Python"
    assert lote.written == ["es", "en"]
    assert len(cliente.llamadas) == 1


def test_traducir_toda_la_importacion_es_una_sola_llamada(cliente_web, tmp_path: Path, monkeypatch):
    """Five categories in one request: five would need five minutes of the
    free tier's quota to do what fits in one answer."""
    import json

    import ancla.web.views.import_cv as vista

    root = tmp_path / "perfil"
    modulo_importacion.save_import(
        root,
        modulo_importacion.ImportBatch(
            experiencias=[
                Experience(
                    id="ml-dev", title=Bilingual(es="Dev", en=""),
                    period_start="2026", period_end="",
                    bullets=Bilingual(es=["Uno"], en=[]), stack="Python", keywords=["ml"],
                )
            ],
            skills=[_skill_solo_en_espanol()],
            educacion=[
                Education(
                    id="grado", title=Bilingual(es="Grado", en=""),
                    institution="UEMC", period_start="2023", period_end="2027",
                )
            ],
            written=["es"],
        ),
    )
    cliente = _ClienteFalso(
        json.dumps(
            {
                "0": {"title": "Dev", "bullets": ["One"]},
                "1": {"name": "Python"},
                "2": {"title": "Degree"},
            }
        )
    )
    monkeypatch.setattr(
        vista, "create_client",
        lambda proveedor, clave, url_base="", modelo="": cliente,
    )

    cliente_web.post(
        "/perfil/importar/traducir",
        data={
            "exp-0-titulo_es": "Dev", "exp-0-bullets_es": "Uno",
            "exp-0-periodo_inicio": "2026", "exp-0-stack": "Python",
            "skill-0-nombre_es": "Python",
            "edu-0-titulo_es": "Grado", "edu-0-centro": "UEMC",
            "edu-0-periodo_inicio": "2023", "edu-0-periodo_fin": "2027",
        },
    )

    lote = modulo_importacion.load_import(root)
    assert len(cliente.llamadas) == 1
    assert lote.experiencias[0].bullets["en"] == ["One"]
    assert lote.skills[0].name["en"] == "Python"
    assert lote.educacion[0].title["en"] == "Degree"


def test_traducir_conserva_lo_que_el_usuario_habia_corregido(cliente_web, tmp_path: Path, monkeypatch):
    """The two buttons of the review screen submit the same form, so pressing
    "translate" must not throw away the edits that "save" would have kept."""
    import json

    import ancla.web.views.import_cv as vista

    root = tmp_path / "perfil"
    modulo_importacion.save_import(
        root,
        modulo_importacion.ImportBatch(skills=[_skill_solo_en_espanol()], written=["es"]),
    )
    monkeypatch.setattr(
        vista, "create_client",
        lambda proveedor, clave, url_base="", modelo="": _ClienteFalso(
            json.dumps({"0": {"name": "Advanced Python"}})
        ),
    )

    cliente_web.post(
        "/perfil/importar/traducir", data={"skill-0-nombre_es": "Python avanzado"}
    )

    lote = modulo_importacion.load_import(root)
    assert lote.skills[0].name["es"] == "Python avanzado"
    assert lote.skills[0].name["en"] == "Advanced Python"


# --------------------------------------------------------------------------
# Importar la segunda parte de un CV recortado
# --------------------------------------------------------------------------


def test_revisar_ofrece_importar_el_resto_si_quedo_pendiente(cliente_web, tmp_path: Path):
    modulo_importacion.save_import(
        tmp_path / "perfil",
        modulo_importacion.ImportBatch(skills=[_skill()], resto="EDUCACIÓN\nGrado\n"),
    )

    respuesta = cliente_web.get("/perfil/importar/revisar")

    assert "Importar el resto del CV".encode("utf-8") in respuesta.data


def test_revisar_no_ofrece_importar_el_resto_si_no_quedo_nada(cliente_web, tmp_path: Path):
    modulo_importacion.save_import(
        tmp_path / "perfil", modulo_importacion.ImportBatch(skills=[_skill()])
    )

    respuesta = cliente_web.get("/perfil/importar/revisar")

    assert "Importar el resto del CV".encode("utf-8") not in respuesta.data


def test_importar_la_segunda_parte_anade_sus_candidatas_al_mismo_lote(
    cliente_web, tmp_path: Path, monkeypatch
):
    import json

    import ancla.web.views.import_cv as vista

    root = tmp_path / "perfil"
    modulo_importacion.save_import(
        root,
        modulo_importacion.ImportBatch(
            skills=[_skill()], resto="EDUCACIÓN\nGrado en Ingeniería\n", written=["es"],
        ),
    )
    cliente = _ClienteFalso(
        json.dumps({"educacion": [{"titulo": "Grado en Ingeniería", "centro": "UEMC"}]})
    )
    monkeypatch.setattr(
        vista, "create_client",
        lambda proveedor, clave, url_base="", modelo="": cliente,
    )

    respuesta = cliente_web.post(
        "/perfil/importar/segunda-parte",
        data={"skill-0-nombre_es": "Python"},
        follow_redirects=True,
    )

    assert respuesta.status_code == 200
    lote = modulo_importacion.load_import(root)
    assert lote.educacion[0].title["es"] == "Grado en Ingeniería"
    # The leftover text was fully analysed in one call: nothing left pending.
    assert lote.resto == ""
    # The first part's own edit travelled with the request, same as translating.
    assert lote.skills[0].name["es"] == "Python"
    assert len(cliente.llamadas) == 1


def test_importar_la_segunda_parte_no_repite_lo_que_ya_estaba_en_el_lote(
    cliente_web, tmp_path: Path, monkeypatch
):
    import json

    import ancla.web.views.import_cv as vista

    root = tmp_path / "perfil"
    modulo_importacion.save_import(
        root,
        modulo_importacion.ImportBatch(
            skills=[_skill()], resto="algo mas del cv", written=["es"],
        ),
    )
    cliente = _ClienteFalso(json.dumps({"skills": [{"nombre": "Python"}]}))
    monkeypatch.setattr(
        vista, "create_client",
        lambda proveedor, clave, url_base="", modelo="": cliente,
    )

    cliente_web.post("/perfil/importar/segunda-parte", data={"skill-0-nombre_es": "Python"})

    lote = modulo_importacion.load_import(root)
    assert len(lote.skills) == 1


def test_importar_la_segunda_parte_sin_nada_pendiente_redirige_a_revisar(
    cliente_web, tmp_path: Path
):
    modulo_importacion.save_import(
        tmp_path / "perfil", modulo_importacion.ImportBatch(skills=[_skill()])
    )

    respuesta = cliente_web.post("/perfil/importar/segunda-parte", follow_redirects=True)

    assert "No queda ninguna parte pendiente".encode("utf-8") in respuesta.data


def test_importar_la_segunda_parte_sin_importacion_pendiente_redirige_a_importar(cliente_web):
    respuesta = cliente_web.post("/perfil/importar/segunda-parte", follow_redirects=True)

    assert "vuelve a subir el CV".encode("utf-8") in respuesta.data


# --------------------------------------------------------------------------
# Contact and "About me": single values, not lists — added so an import
# proposes the whole profile, not just the five professional categories.
# --------------------------------------------------------------------------


def _sobre_mi_con_huecos(idioma: str = "es") -> AboutMe:
    """A template with all six gaps already placed in the language it was
    imported in — the shape `analyze_cv` + `gaps.place` hand to the review
    screen when every fragment could be matched."""
    huecos = " ".join(AboutMe(template=Bilingual(es="", en="")).gaps())
    return AboutMe(template=Bilingual(**{idioma: f"Perfil con {huecos}.", "en" if idioma == "es" else "es": ""}))


def test_guardar_y_cargar_contacto_y_sobre_mi_hace_ida_y_vuelta(tmp_path: Path):
    original = modulo_importacion.ImportBatch(
        contacto_nombre="Ana Ejemplo",
        contacto_titular=Bilingual(es="Ingeniera de Datos", en=""),
        contacto_lineas=["ana@ejemplo.com", "Madrid, España"],
        sobre_mi=_sobre_mi_con_huecos(),
    )
    modulo_importacion.save_import(tmp_path, original)

    cargado = modulo_importacion.load_import(tmp_path)

    assert cargado.contacto_nombre == "Ana Ejemplo"
    assert cargado.contacto_titular["es"] == "Ingeniera de Datos"
    assert cargado.contacto_lineas == ["ana@ejemplo.com", "Madrid, España"]
    assert cargado.sobre_mi.template["es"] == original.sobre_mi.template["es"]


def test_un_lote_sin_contacto_ni_sobre_mi_carga_igual(tmp_path: Path):
    modulo_importacion.save_import(tmp_path, modulo_importacion.ImportBatch(skills=[_skill()]))
    cargado = modulo_importacion.load_import(tmp_path)
    assert cargado.has_contact() is False
    assert cargado.sobre_mi is None


def test_revisar_muestra_el_contacto_y_el_sobre_mi(cliente_web, tmp_path: Path):
    modulo_importacion.save_import(
        tmp_path / "perfil",
        modulo_importacion.ImportBatch(
            contacto_nombre="Ana Ejemplo",
            contacto_titular=Bilingual(es="Ingeniera de Datos", en=""),
            contacto_lineas=["ana@ejemplo.com"],
            sobre_mi=_sobre_mi_con_huecos(),
        ),
    )
    respuesta = cliente_web.get("/perfil/importar/revisar")
    html = respuesta.data.decode("utf-8")
    assert "Ana Ejemplo" in html
    assert "ana@ejemplo.com" in html
    assert "Perfil con" in html


def test_revisar_sin_contacto_ni_sobre_mi_no_muestra_esas_tarjetas(cliente_web, tmp_path: Path):
    modulo_importacion.save_import(
        tmp_path / "perfil", modulo_importacion.ImportBatch(skills=[_skill()])
    )
    html = cliente_web.get("/perfil/importar/revisar").data.decode("utf-8")
    assert "Guardar el contacto" not in html
    assert "Guardar el «Sobre mí»" not in html


def test_guardar_el_contacto_importado_va_al_perfil(cliente_web, tmp_path: Path):
    root = tmp_path / "perfil"
    modulo_importacion.save_import(
        root,
        modulo_importacion.ImportBatch(
            contacto_nombre="Ana Ejemplo",
            contacto_titular=Bilingual(es="Ingeniera de Datos", en=""),
            contacto_lineas=["ana@ejemplo.com", "Madrid, España"],
        ),
    )
    cliente_web.post(
        "/perfil/importar/guardar",
        data={
            "contacto": "1",
            "contacto-nombre": "Ana Ejemplo",
            "contacto-titular_es": "Ingeniera de Datos",
            "contacto-lineas": "ana@ejemplo.com\nMadrid, España",
        },
    )
    perfil = store.load_profile(root)
    assert perfil.name == "Ana Ejemplo"
    assert perfil.headline["es"] == "Ingeniera de Datos"
    assert perfil.contact == ["ana@ejemplo.com", "Madrid, España"]


def test_el_contacto_no_marcado_no_se_guarda(cliente_web, tmp_path: Path):
    root = tmp_path / "perfil"
    modulo_importacion.save_import(
        root, modulo_importacion.ImportBatch(contacto_nombre="Ana Ejemplo")
    )
    cliente_web.post("/perfil/importar/guardar", data={})
    assert store.load_profile(root).name == ""


def test_guardar_el_sobre_mi_importado_con_los_huecos_ya_colocados(cliente_web, tmp_path: Path):
    root = tmp_path / "perfil"
    sobre_mi = _sobre_mi_con_huecos()
    modulo_importacion.save_import(root, modulo_importacion.ImportBatch(sobre_mi=sobre_mi))

    cliente_web.post(
        "/perfil/importar/guardar",
        data={"sobre-mi": "1", "sobre-mi-plantilla_es": sobre_mi.template["es"]},
    )

    perfil = store.load_profile(root)
    assert perfil.about_me is not None
    assert perfil.about_me.template["es"] == sobre_mi.template["es"]


def test_un_sobre_mi_con_huecos_sin_colocar_no_se_guarda_pero_avisa(cliente_web, tmp_path: Path):
    """Same treatment as the five list categories: a candidate that fails
    validation is rejected, not written half-finished — here that means
    finishing it by hand later from «Editar Sobre mí», which can mark the
    remaining gaps over the same text."""
    root = tmp_path / "perfil"
    incompleto = AboutMe(template=Bilingual(es="Perfil con experiencia variada.", en=""))
    modulo_importacion.save_import(root, modulo_importacion.ImportBatch(sobre_mi=incompleto))

    respuesta = cliente_web.post(
        "/perfil/importar/guardar",
        data={"sobre-mi": "1", "sobre-mi-plantilla_es": incompleto.template["es"]},
        follow_redirects=True,
    )

    assert store.load_profile(root).about_me is None
    assert "no se pudieron guardar".encode("utf-8") in respuesta.data


def test_el_sobre_mi_no_marcado_no_se_guarda(cliente_web, tmp_path: Path):
    root = tmp_path / "perfil"
    sobre_mi = _sobre_mi_con_huecos()
    modulo_importacion.save_import(root, modulo_importacion.ImportBatch(sobre_mi=sobre_mi))
    cliente_web.post("/perfil/importar/guardar", data={})
    assert store.load_profile(root).about_me is None


def test_una_importacion_solo_con_contacto_llega_a_la_pantalla_de_revision(
    cliente_web, tmp_path, monkeypatch
):
    import json

    import ancla.web.views.import_cv as vista

    monkeypatch.setattr(
        vista, "create_client",
        lambda proveedor, clave, url_base="", modelo="": _ClienteFalso(
            json.dumps(
                {
                    "experiencias": [], "skills": [], "skills_personales": [], "idiomas": [],
                    "educacion": [],
                    "contacto": {"nombre": "Ana Ejemplo", "titular": "", "lineas": []},
                }
            )
        ),
    )
    respuesta = cliente_web.post("/perfil/importar", data={"texto": "cv de sobra largo " * 5})
    assert respuesta.status_code == 302
    assert respuesta.location.endswith("/perfil/importar/revisar")
