"""Tests del almacén YAML del perfil.

Lo que se protege aquí, por orden de importancia: que abrir la app sin perfil no
sea un error, que nada de lo que escribe el usuario se pierda o se altere al
guardar y volver a leer, y que un fichero roto se explique en vez de reventar.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from cv_adaptativo.perfil import almacen
from cv_adaptativo.perfil.almacen import ErrorPerfil
from cv_adaptativo.perfil.modelo import Bilingue, Experiencia, Skill, SobreMi


def _experiencia(id: str = "ml-telco-churn") -> Experiencia:
    return Experiencia(
        id=id,
        titulo=Bilingue(es="ML Developer — Telco", en="ML Developer — Telco"),
        periodo=Bilingue(es="2026 - ACTUALIDAD", en="2026 - PRESENT"),
        bullets=Bilingue(
            es=["Pipeline completo: diseño, pruebas y evaluación.", "Optuna, 50 iteraciones."],
            en=["Full pipeline: design, testing, evaluation", "Optuna, 50 trials"],
        ),
        stack=Bilingue(es="Python · Scikit-Learn", en="Python · Scikit-Learn"),
        keywords=["machine learning", "optuna"],
        estado="actualidad",
    )


def _skill(id: str = "python") -> Skill:
    return Skill(
        id=id,
        nombre=Bilingue(es="Python", en="Python"),
        categoria="lenguaje",
        keywords=["python", "scripting"],
    )


def _sobre_mi() -> SobreMi:
    texto = (
        "Estudiante con conocimientos en {GRUPO_A_1}, {GRUPO_A_2} y {GRUPO_A_3}. "
        "Desarrollo en {GRUPO_B_1}, {GRUPO_B_2} y {GRUPO_B_3}."
    )
    return SobreMi(plantilla=Bilingue(es=texto, en=texto))


# --------------------------------------------------------------------------
# Carga
# --------------------------------------------------------------------------


def test_una_carpeta_que_no_existe_da_un_perfil_vacio(tmp_path: Path):
    """Es el estado normal la primera vez que se abre la app, no un error."""
    perfil = almacen.cargar_perfil(tmp_path / "todavia-no-existe")

    assert perfil.esta_vacio()
    assert perfil.sobre_mi is None


def test_una_carpeta_a_medias_carga_lo_que_haya(tmp_path: Path):
    """Tener skills pero aún no experiencias es un perfil a medio escribir."""
    almacen.guardar_skill(tmp_path, _skill())

    perfil = almacen.cargar_perfil(tmp_path)

    assert [s.id for s in perfil.skills] == ["python"]
    assert perfil.experiencias == []
    assert perfil.sobre_mi is None


def test_guardar_y_cargar_devuelve_exactamente_lo_mismo(tmp_path: Path):
    """El sistema no reescribe al usuario: ni sus bullets ni sus acentos."""
    original = _experiencia()
    almacen.guardar_experiencia(tmp_path, original)

    recuperada = almacen.cargar_perfil(tmp_path).experiencia("ml-telco-churn")

    assert recuperada == original


def test_guardar_y_cargar_una_skill_y_el_sobre_mi(tmp_path: Path):
    almacen.guardar_skill(tmp_path, _skill())
    almacen.guardar_sobre_mi(tmp_path, _sobre_mi())

    perfil = almacen.cargar_perfil(tmp_path)

    assert perfil.skill("python") == _skill()
    assert perfil.sobre_mi == _sobre_mi()


def test_el_id_sale_del_nombre_del_fichero(tmp_path: Path):
    """Solo hay una fuente de la verdad para el id, y es el nombre del fichero."""
    ruta = tmp_path / almacen.CARPETA_SKILLS / "sql.yaml"
    ruta.parent.mkdir(parents=True)
    ruta.write_text("nombre:\n  es: SQL\n  en: SQL\n", encoding="utf-8")

    assert almacen.cargar_perfil(tmp_path).skills[0].id == "sql"


def test_un_texto_suelto_vale_para_los_dos_idiomas(tmp_path: Path):
    """Muchos títulos son idénticos en ES y EN; obligar a repetirlos invita a
    que se desincronicen."""
    ruta = tmp_path / almacen.CARPETA_SKILLS / "java.yaml"
    ruta.parent.mkdir(parents=True)
    ruta.write_text("nombre: Java\ncategoria: lenguaje\n", encoding="utf-8")

    skill = almacen.cargar_perfil(tmp_path).skill("java")

    assert skill.nombre["es"] == "Java"
    assert skill.nombre["en"] == "Java"


def test_las_keywords_valen_en_lista_y_separadas_por_comas(tmp_path: Path):
    carpeta = tmp_path / almacen.CARPETA_SKILLS
    carpeta.mkdir(parents=True)
    (carpeta / "a.yaml").write_text("keywords: sql, bases de datos\n", encoding="utf-8")
    (carpeta / "b.yaml").write_text("keywords:\n  - sql\n  - bases de datos\n", encoding="utf-8")

    perfil = almacen.cargar_perfil(tmp_path)

    assert perfil.skill("a").keywords == ["sql", "bases de datos"]
    assert perfil.skill("b").keywords == perfil.skill("a").keywords


def test_un_fichero_vacio_carga_como_elemento_en_blanco(tmp_path: Path):
    """Estar a medias es normal mientras se edita; ya lo contará la validación."""
    ruta = tmp_path / almacen.CARPETA_EXPERIENCIA / "empezada.yaml"
    ruta.parent.mkdir(parents=True)
    ruta.write_text("", encoding="utf-8")

    experiencia = almacen.cargar_perfil(tmp_path).experiencia("empezada")

    assert experiencia.titulo["es"] == ""
    assert experiencia.bullets["en"] == []


def test_el_orden_de_carga_no_depende_del_sistema_de_ficheros(tmp_path: Path):
    for id_ in ("zeta", "alfa", "mu"):
        almacen.guardar_skill(tmp_path, _skill(id_))

    assert [s.id for s in almacen.cargar_perfil(tmp_path).skills] == ["alfa", "mu", "zeta"]


# --------------------------------------------------------------------------
# Ficheros rotos: se explican, no revientan
# --------------------------------------------------------------------------


def test_un_yaml_mal_formado_da_un_mensaje_en_castellano_con_el_fichero(tmp_path: Path):
    ruta = tmp_path / almacen.CARPETA_EXPERIENCIA / "rota.yaml"
    ruta.parent.mkdir(parents=True)
    ruta.write_text("titulo:\n  es: bien\n   en: mal indentado\n", encoding="utf-8")

    with pytest.raises(ErrorPerfil) as error:
        almacen.cargar_perfil(tmp_path)

    mensaje = str(error.value)
    assert "rota.yaml" in mensaje
    assert "Traceback" not in mensaje
    assert "línea" in mensaje


def test_un_campo_de_lista_que_no_es_lista_se_explica(tmp_path: Path):
    ruta = tmp_path / almacen.CARPETA_EXPERIENCIA / "rara.yaml"
    ruta.parent.mkdir(parents=True)
    ruta.write_text("bullets:\n  es: esto debería ser una lista\n", encoding="utf-8")

    with pytest.raises(ErrorPerfil, match="rara.yaml"):
        almacen.cargar_perfil(tmp_path)


def test_un_fichero_que_no_es_un_diccionario_se_explica(tmp_path: Path):
    ruta = tmp_path / almacen.CARPETA_SKILLS / "lista.yaml"
    ruta.parent.mkdir(parents=True)
    ruta.write_text("- python\n- java\n", encoding="utf-8")

    with pytest.raises(ErrorPerfil, match="lista.yaml"):
        almacen.cargar_perfil(tmp_path)


# --------------------------------------------------------------------------
# Escritura
# --------------------------------------------------------------------------


@pytest.mark.parametrize("id_malo", ["../fuera", "carpeta/dentro", "", "con espacio", ".oculto"])
def test_un_id_peligroso_no_escribe_fuera_de_la_carpeta(tmp_path: Path, id_malo: str):
    """El id acaba siendo un nombre de fichero: una barra escribiría fuera."""
    with pytest.raises(ErrorPerfil):
        almacen.guardar_skill(tmp_path, _skill(id_malo))


def test_guardar_dos_veces_sobrescribe_y_no_deja_temporales(tmp_path: Path):
    almacen.guardar_skill(tmp_path, _skill())
    almacen.guardar_skill(tmp_path, _skill())

    carpeta = tmp_path / almacen.CARPETA_SKILLS
    assert [ruta.name for ruta in carpeta.iterdir()] == ["python.yaml"]


def test_el_yaml_guardado_se_lee_a_ojo(tmp_path: Path):
    """Los ficheros son del usuario y tiene que poder editarlos a mano."""
    almacen.guardar_skill(tmp_path, _skill("scikit"))

    texto = (tmp_path / almacen.CARPETA_SKILLS / "scikit.yaml").read_text(encoding="utf-8")

    assert texto.startswith("nombre:")  # No se reordenan los campos alfabéticamente.
    assert "\\u" not in texto  # Los acentos se escriben, no se escapan.


def test_los_acentos_sobreviven_a_una_vuelta_completa(tmp_path: Path):
    skill = Skill(
        id="disenio",
        nombre=Bilingue(es="Diseño de sistemas", en="System design"),
        categoria="ingeniería",
        keywords=["diseño", "arquitectura"],
    )
    almacen.guardar_skill(tmp_path, skill)

    assert almacen.cargar_perfil(tmp_path).skill("disenio") == skill


def test_borrar_quita_el_fichero_y_repetirlo_no_falla(tmp_path: Path):
    almacen.guardar_skill(tmp_path, _skill())

    almacen.borrar_skill(tmp_path, "python")
    almacen.borrar_skill(tmp_path, "python")

    assert almacen.cargar_perfil(tmp_path).skill("python") is None


# --------------------------------------------------------------------------
# Respaldo y mudanza
# --------------------------------------------------------------------------


def test_exportar_e_importar_deja_el_perfil_igual(tmp_path: Path):
    origen = tmp_path / "perfil"
    almacen.guardar_experiencia(origen, _experiencia())
    almacen.guardar_skill(origen, _skill())
    almacen.guardar_sobre_mi(origen, _sobre_mi())
    (origen / "cvs" / "adjuntos").mkdir(parents=True)
    (origen / "cvs" / "adjuntos" / "cv.pdf").write_bytes(b"%PDF-falso")

    zip_ = almacen.exportar_zip(origen, tmp_path / "respaldo")
    destino = tmp_path / "otro-ordenador"
    almacen.importar_zip(destino, zip_)

    assert zip_.name == "respaldo.zip"
    assert almacen.cargar_perfil(destino) == almacen.cargar_perfil(origen)
    assert (destino / "cvs" / "adjuntos" / "cv.pdf").read_bytes() == b"%PDF-falso"


def test_importar_sobre_un_perfil_existente_no_mezcla_en_silencio(tmp_path: Path):
    origen = tmp_path / "perfil"
    almacen.guardar_skill(origen, _skill())
    zip_ = almacen.exportar_zip(origen, tmp_path / "respaldo.zip")

    with pytest.raises(ErrorPerfil, match="vacía"):
        almacen.importar_zip(origen, zip_)


def test_exportar_un_perfil_que_no_existe_se_explica(tmp_path: Path):
    with pytest.raises(ErrorPerfil, match="exportar"):
        almacen.exportar_zip(tmp_path / "nada", tmp_path / "respaldo.zip")


def test_un_zip_con_rutas_que_se_escapan_no_se_importa(tmp_path: Path):
    """Un respaldo puede venir de cualquier sitio; no se extrae a ciegas."""
    malicioso = tmp_path / "malicioso.zip"
    with zipfile.ZipFile(malicioso, "w") as zip_:
        zip_.writestr("../../robado.yaml", "nombre: uy")

    destino = tmp_path / "perfil"
    with pytest.raises(ErrorPerfil, match="salen de la carpeta"):
        almacen.importar_zip(destino, malicioso)

    assert not (tmp_path.parent / "robado.yaml").exists()


def test_una_exportacion_que_falla_no_deja_un_respaldo_a_medias(tmp_path: Path, monkeypatch):
    """Un respaldo truncado aparenta estar entero, y eso solo se descubre el día
    que hace falta restaurarlo."""
    origen = tmp_path / "perfil"
    almacen.guardar_skill(origen, _skill())

    def _falla_a_media_escritura(_self, *_args, **_kwargs):
        raise OSError(28, "No queda espacio en el disco")

    monkeypatch.setattr(zipfile.ZipFile, "write", _falla_a_media_escritura)

    with pytest.raises(ErrorPerfil, match="respaldo"):
        almacen.exportar_zip(origen, tmp_path / "respaldo.zip")

    assert list(tmp_path.glob("respaldo*")) == []


def test_importar_algo_que_no_es_un_zip_se_explica(tmp_path: Path):
    falso = tmp_path / "respaldo.zip"
    falso.write_text("esto no es un zip", encoding="utf-8")

    with pytest.raises(ErrorPerfil, match="no es un respaldo válido"):
        almacen.importar_zip(tmp_path / "perfil", falso)
