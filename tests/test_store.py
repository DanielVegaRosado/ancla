"""Tests for the profile's YAML storage layer.

What is protected here, in order of importance: that opening the app with
no profile is not an error, that nothing the user writes is lost or
altered by saving and reading it back, and that a broken file is explained
rather than crashing.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from ancla.profile import store
from ancla.profile.store import ProfileError
from ancla.profile.model import AboutMe, Bilingual, Education, Experience, Skill


def _educacion(id: str = "grado") -> Education:
    return Education(
        id=id,
        title=Bilingual(es="Grado en Ingeniería Informática", en="BSc in Computer Engineering"),
        institution=Bilingual(es="UEMC", en="UEMC"),
        period=Bilingual(es="2023 — 2027", en="2023 — 2027"),
    )


def _experiencia(id: str = "ml-telco-churn") -> Experience:
    return Experience(
        id=id,
        title=Bilingual(es="ML Developer — Telco", en="ML Developer — Telco"),
        period=Bilingual(es="2026 - ACTUALIDAD", en="2026 - PRESENT"),
        bullets=Bilingual(
            es=["Pipeline completo: diseño, pruebas y evaluación.", "Optuna, 50 iteraciones."],
            en=["Full pipeline: design, testing, evaluation", "Optuna, 50 trials"],
        ),
        stack=Bilingual(es="Python · Scikit-Learn", en="Python · Scikit-Learn"),
        keywords=["machine learning", "optuna"],
        status="actualidad",
    )


def _skill(id: str = "python") -> Skill:
    return Skill(
        id=id,
        name=Bilingual(es="Python", en="Python"),
        category="lenguaje",
        keywords=["python", "scripting"],
    )


def _sobre_mi() -> AboutMe:
    texto = (
        "Estudiante con conocimientos en {GROUP_A_1}, {GROUP_A_2} y {GROUP_A_3}. "
        "Desarrollo en {GROUP_B_1}, {GROUP_B_2} y {GROUP_B_3}."
    )
    return AboutMe(template=Bilingual(es=texto, en=texto))


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------


def test_una_carpeta_que_no_existe_da_un_perfil_vacio(tmp_path: Path):
    """This is the normal state the first time the app is opened, not an error."""
    perfil = store.load_profile(tmp_path / "todavia-no-existe")

    assert perfil.is_empty()
    assert perfil.about_me is None


def test_una_carpeta_a_medias_carga_lo_que_haya(tmp_path: Path):
    """Having skills but no experiences yet is a half-written profile."""
    store.save_skill(tmp_path, _skill())

    perfil = store.load_profile(tmp_path)

    assert [s.id for s in perfil.skills] == ["python"]
    assert perfil.experiences == []
    assert perfil.about_me is None


def test_guardar_y_cargar_devuelve_exactamente_lo_mismo(tmp_path: Path):
    """The system never rewrites the user: not their bullets, not their accents."""
    original = _experiencia()
    store.save_experience(tmp_path, original)

    recuperada = store.load_profile(tmp_path).experience("ml-telco-churn")

    assert recuperada == original


def test_guardar_y_cargar_una_skill_y_el_sobre_mi(tmp_path: Path):
    store.save_skill(tmp_path, _skill())
    store.save_about_me(tmp_path, _sobre_mi())

    perfil = store.load_profile(tmp_path)

    assert perfil.skill("python") == _skill()
    assert perfil.about_me == _sobre_mi()


def test_el_id_sale_del_nombre_del_fichero(tmp_path: Path):
    """There is only one source of truth for the id, and it is the file name."""
    ruta = tmp_path / store.CARPETA_SKILLS / "sql.yaml"
    ruta.parent.mkdir(parents=True)
    ruta.write_text("name:\n  es: SQL\n  en: SQL\n", encoding="utf-8")

    assert store.load_profile(tmp_path).skills[0].id == "sql"


def test_un_texto_suelto_vale_para_los_dos_idiomas(tmp_path: Path):
    """Many titles are identical in ES and EN; forcing them to be repeated
    invites them to drift apart."""
    ruta = tmp_path / store.CARPETA_SKILLS / "java.yaml"
    ruta.parent.mkdir(parents=True)
    ruta.write_text("name: Java\ncategory: lenguaje\n", encoding="utf-8")

    skill = store.load_profile(tmp_path).skill("java")

    assert skill.name["es"] == "Java"
    assert skill.name["en"] == "Java"


def test_las_keywords_valen_en_lista_y_separadas_por_comas(tmp_path: Path):
    carpeta = tmp_path / store.CARPETA_SKILLS
    carpeta.mkdir(parents=True)
    (carpeta / "a.yaml").write_text("keywords: sql, bases de datos\n", encoding="utf-8")
    (carpeta / "b.yaml").write_text("keywords:\n  - sql\n  - bases de datos\n", encoding="utf-8")

    perfil = store.load_profile(tmp_path)

    assert perfil.skill("a").keywords == ["sql", "bases de datos"]
    assert perfil.skill("b").keywords == perfil.skill("a").keywords


def test_un_fichero_vacio_carga_como_elemento_en_blanco(tmp_path: Path):
    """Being half-done is normal while editing; validation will report it."""
    ruta = tmp_path / store.CARPETA_EXPERIENCIA / "empezada.yaml"
    ruta.parent.mkdir(parents=True)
    ruta.write_text("", encoding="utf-8")

    experiencia = store.load_profile(tmp_path).experience("empezada")

    assert experiencia.title["es"] == ""
    assert experiencia.bullets["en"] == []


def test_el_orden_de_carga_no_depende_del_sistema_de_ficheros(tmp_path: Path):
    for id_ in ("zeta", "alfa", "mu"):
        store.save_skill(tmp_path, _skill(id_))

    assert [s.id for s in store.load_profile(tmp_path).skills] == ["alfa", "mu", "zeta"]


# --------------------------------------------------------------------------
# Broken files: explained, never a crash
# --------------------------------------------------------------------------


def test_un_yaml_mal_formado_da_un_mensaje_en_castellano_con_el_fichero(tmp_path: Path):
    ruta = tmp_path / store.CARPETA_EXPERIENCIA / "rota.yaml"
    ruta.parent.mkdir(parents=True)
    ruta.write_text("title:\n  es: bien\n   en: mal indentado\n", encoding="utf-8")

    with pytest.raises(ProfileError) as error:
        store.load_profile(tmp_path)

    mensaje = str(error.value)
    assert "rota.yaml" in mensaje
    assert "Traceback" not in mensaje
    assert "línea" in mensaje


def test_un_campo_de_lista_que_no_es_lista_se_explica(tmp_path: Path):
    ruta = tmp_path / store.CARPETA_EXPERIENCIA / "rara.yaml"
    ruta.parent.mkdir(parents=True)
    ruta.write_text("bullets:\n  es: esto debería ser una lista\n", encoding="utf-8")

    with pytest.raises(ProfileError, match="rara.yaml"):
        store.load_profile(tmp_path)


def test_un_fichero_que_no_es_un_diccionario_se_explica(tmp_path: Path):
    ruta = tmp_path / store.CARPETA_SKILLS / "lista.yaml"
    ruta.parent.mkdir(parents=True)
    ruta.write_text("- python\n- java\n", encoding="utf-8")

    with pytest.raises(ProfileError, match="lista.yaml"):
        store.load_profile(tmp_path)


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------


@pytest.mark.parametrize("id_malo", ["../fuera", "carpeta/dentro", "", "con espacio", ".oculto"])
def test_un_id_peligroso_no_escribe_fuera_de_la_carpeta(tmp_path: Path, id_malo: str):
    """The id ends up as a file name: a slash would write outside the folder."""
    with pytest.raises(ProfileError):
        store.save_skill(tmp_path, _skill(id_malo))


def test_guardar_dos_veces_sobrescribe_y_no_deja_temporales(tmp_path: Path):
    store.save_skill(tmp_path, _skill())
    store.save_skill(tmp_path, _skill())

    carpeta = tmp_path / store.CARPETA_SKILLS
    assert [ruta.name for ruta in carpeta.iterdir()] == ["python.yaml"]


def test_el_yaml_guardado_se_lee_a_ojo(tmp_path: Path):
    """The files belong to the user and they have to be able to edit them by hand."""
    store.save_skill(tmp_path, _skill("scikit"))

    texto = (tmp_path / store.CARPETA_SKILLS / "scikit.yaml").read_text(encoding="utf-8")

    assert texto.startswith("name:")  # Fields are not reordered alphabetically.
    assert "\\u" not in texto  # Accents are written out, not escaped.


def test_los_acentos_sobreviven_a_una_vuelta_completa(tmp_path: Path):
    skill = Skill(
        id="disenio",
        name=Bilingual(es="Diseño de sistemas", en="System design"),
        category="ingeniería",
        keywords=["diseño", "arquitectura"],
    )
    store.save_skill(tmp_path, skill)

    assert store.load_profile(tmp_path).skill("disenio") == skill


def test_borrar_quita_el_fichero_y_repetirlo_no_falla(tmp_path: Path):
    store.save_skill(tmp_path, _skill())

    store.delete_skill(tmp_path, "python")
    store.delete_skill(tmp_path, "python")

    assert store.load_profile(tmp_path).skill("python") is None


def test_borrar_todas_las_skills_vacia_la_carpeta_y_repetirlo_no_falla(tmp_path: Path):
    store.save_skill(tmp_path, _skill("python"))
    store.save_skill(tmp_path, _skill("sql"))

    store.delete_all_skills(tmp_path)
    store.delete_all_skills(tmp_path)

    assert store.load_profile(tmp_path).skills == []


def test_borrar_todas_las_experiencias_no_toca_las_skills(tmp_path: Path):
    store.save_experience(tmp_path, _experiencia())
    store.save_skill(tmp_path, _skill())

    store.delete_all_experiences(tmp_path)

    perfil = store.load_profile(tmp_path)
    assert perfil.experiences == []
    assert perfil.skill("python") is not None


def test_borrar_todas_las_skills_personales_y_todos_los_idiomas(tmp_path: Path):
    from ancla.profile.model import SpokenLanguage

    store.save_personal_skill(tmp_path, _skill("trabajo-en-equipo"))
    store.save_language(
        tmp_path,
        SpokenLanguage(
            id="ingles",
            name=Bilingual(es="Inglés", en="English"),
            level=Bilingual(es="C1", en="C1"),
        ),
    )

    store.delete_all_personal_skills(tmp_path)
    store.delete_all_languages(tmp_path)

    perfil = store.load_profile(tmp_path)
    assert perfil.personal_skills == []
    assert perfil.languages == []


def test_borrar_todas_sobre_una_carpeta_que_no_existe_no_falla(tmp_path: Path):
    store.delete_all_experiences(tmp_path)
    store.delete_all_skills(tmp_path)
    store.delete_all_personal_skills(tmp_path)
    store.delete_all_languages(tmp_path)


# --------------------------------------------------------------------------
# Education, contact, photo
# --------------------------------------------------------------------------


def test_guardar_y_cargar_educacion_hace_ida_y_vuelta(tmp_path: Path):
    store.save_education(tmp_path, _educacion())
    perfil = store.load_profile(tmp_path)
    assert perfil.education == [_educacion()]
    assert perfil.education_entry("grado") == _educacion()


def test_borrar_educacion(tmp_path: Path):
    store.save_education(tmp_path, _educacion())
    store.delete_education(tmp_path, "grado")
    assert store.load_profile(tmp_path).education == []


def test_borrar_todas_las_educaciones(tmp_path: Path):
    store.save_education(tmp_path, _educacion("grado"))
    store.save_education(tmp_path, _educacion("master"))
    store.delete_all_education(tmp_path)
    assert store.load_profile(tmp_path).education == []


def test_sin_fichero_de_contacto_el_perfil_no_tiene_contacto_ni_titular(tmp_path: Path):
    perfil = store.load_profile(tmp_path)
    assert perfil.name == ""
    assert perfil.contact == []
    assert perfil.headline == Bilingual(es="", en="")


def test_guardar_y_cargar_contacto_hace_ida_y_vuelta(tmp_path: Path):
    lineas = ["+34 600 000 000", "tu@email.com", "Valladolid"]
    titular = Bilingual(es="Ingeniero Informático", en="Computer Engineer")
    store.save_contact(tmp_path, "Daniel Vega", titular, lineas)
    perfil = store.load_profile(tmp_path)
    assert perfil.name == "Daniel Vega"
    assert perfil.contact == lineas
    assert perfil.headline == titular


def test_un_titular_viejo_sin_es_en_se_aplica_a_los_dos_idiomas(tmp_path: Path):
    """`headline` era un texto plano antes de hacerse bilingüe — un perfil
    real guardado con el formato viejo tiene que seguir cargando, con ese
    mismo texto en los dos idiomas hasta que el usuario lo separe a mano."""
    (tmp_path / "contact.yaml").write_text("headline: Ingeniero Informático\n", encoding="utf-8")
    perfil = store.load_profile(tmp_path)
    assert perfil.headline == Bilingual(es="Ingeniero Informático", en="Ingeniero Informático")


def test_sin_foto_el_perfil_no_tiene_foto(tmp_path: Path):
    assert store.load_profile(tmp_path).photo == ""
    assert store.photo_path(tmp_path) is None


def test_guardar_y_cargar_foto_hace_ida_y_vuelta(tmp_path: Path):
    store.save_photo(tmp_path, "foto.png", b"contenido-de-imagen-falso")
    perfil = store.load_profile(tmp_path)
    assert perfil.photo == "photo.png"
    assert store.photo_path(tmp_path) == tmp_path / "photo.png"
    assert (tmp_path / "photo.png").read_bytes() == b"contenido-de-imagen-falso"


def test_subir_una_foto_nueva_reemplaza_la_anterior_aunque_cambie_la_extension(tmp_path: Path):
    store.save_photo(tmp_path, "foto.jpg", b"version-jpg")
    store.save_photo(tmp_path, "foto.png", b"version-png")

    perfil = store.load_profile(tmp_path)
    assert perfil.photo == "photo.png"
    assert not (tmp_path / "photo.jpg").exists()


def test_guardar_una_foto_con_formato_no_admitido_da_error(tmp_path: Path):
    with pytest.raises(ProfileError):
        store.save_photo(tmp_path, "foto.gif", b"contenido")


def test_borrar_foto_sin_que_exista_no_falla(tmp_path: Path):
    store.delete_photo(tmp_path)
    assert store.load_profile(tmp_path).photo == ""


# --------------------------------------------------------------------------
# Backup and migration
# --------------------------------------------------------------------------


def test_exportar_e_importar_deja_el_perfil_igual(tmp_path: Path):
    origen = tmp_path / "perfil"
    store.save_experience(origen, _experiencia())
    store.save_skill(origen, _skill())
    store.save_about_me(origen, _sobre_mi())
    (origen / "cvs" / "attachments").mkdir(parents=True)
    (origen / "cvs" / "attachments" / "cv.pdf").write_bytes(b"%PDF-falso")

    zip_ = store.export_zip(origen, tmp_path / "respaldo")
    destino = tmp_path / "otro-ordenador"
    store.import_zip(destino, zip_)

    assert zip_.name == "respaldo.zip"
    assert store.load_profile(destino) == store.load_profile(origen)
    assert (destino / "cvs" / "attachments" / "cv.pdf").read_bytes() == b"%PDF-falso"


def test_importar_sobre_un_perfil_existente_no_mezcla_en_silencio(tmp_path: Path):
    origen = tmp_path / "perfil"
    store.save_skill(origen, _skill())
    zip_ = store.export_zip(origen, tmp_path / "respaldo.zip")

    with pytest.raises(ProfileError, match="vacía"):
        store.import_zip(origen, zip_)


def test_exportar_un_perfil_que_no_existe_se_explica(tmp_path: Path):
    with pytest.raises(ProfileError, match="exportar"):
        store.export_zip(tmp_path / "nada", tmp_path / "respaldo.zip")


def test_un_zip_con_rutas_que_se_escapan_no_se_importa(tmp_path: Path):
    """A backup can come from anywhere; it is never extracted blindly."""
    malicioso = tmp_path / "malicioso.zip"
    with zipfile.ZipFile(malicioso, "w") as zip_:
        zip_.writestr("../../robado.yaml", "name: uy")

    destino = tmp_path / "perfil"
    with pytest.raises(ProfileError, match="salen de la carpeta"):
        store.import_zip(destino, malicioso)

    assert not (tmp_path.parent / "robado.yaml").exists()


def test_una_exportacion_que_falla_no_deja_un_respaldo_a_medias(tmp_path: Path, monkeypatch):
    """A truncated backup looks complete, and that is only ever discovered
    the day it needs to be restored."""
    origen = tmp_path / "perfil"
    store.save_skill(origen, _skill())

    def _falla_a_media_escritura(_self, *_args, **_kwargs):
        raise OSError(28, "No queda espacio en el disco")

    monkeypatch.setattr(zipfile.ZipFile, "write", _falla_a_media_escritura)

    with pytest.raises(ProfileError, match="respaldo"):
        store.export_zip(origen, tmp_path / "respaldo.zip")

    assert list(tmp_path.glob("respaldo*")) == []


def test_importar_algo_que_no_es_un_zip_se_explica(tmp_path: Path):
    falso = tmp_path / "respaldo.zip"
    falso.write_text("esto no es un zip", encoding="utf-8")

    with pytest.raises(ProfileError, match="no es un respaldo válido"):
        store.import_zip(tmp_path / "perfil", falso)
