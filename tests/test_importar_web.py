"""Tests de la pantalla Importar: estado efímero de la importación y las
rutas HTTP de punta a punta (subir, revisar, guardar seleccionadas, descartar).
"""
from __future__ import annotations

import io
from pathlib import Path

import pytest

from cv_adaptativo.perfil import almacen
from cv_adaptativo.perfil.modelo import Bilingue, Experiencia, Skill
from cv_adaptativo.web import crear_app
from cv_adaptativo.web import importacion as modulo_importacion


@pytest.fixture
def cliente_web(tmp_path: Path):
    app = crear_app(raiz_perfil=tmp_path / "perfil", ruta_ajustes=tmp_path / "ajustes.json")
    app.config["TESTING"] = True
    return app.test_client()


def _experiencia(id: str = "ml-dev") -> Experiencia:
    return Experiencia(
        id=id,
        titulo=Bilingue(es="ML Developer", en="ML Developer"),
        periodo=Bilingue(es="2026", en="2026"),
        bullets=Bilingue(es=["Pipeline completo"], en=["Full pipeline"]),
        stack=Bilingue(es="Python", en="Python"),
        keywords=["ml"],
    )


def _skill(id: str = "python") -> Skill:
    return Skill(id=id, nombre=Bilingue(es="Python", en="Python"), categoria="lenguaje", keywords=["py"])


# --------------------------------------------------------------------------
# web/importacion.py: estado efímero, ida y vuelta
# --------------------------------------------------------------------------


def test_sin_importacion_guardada_no_hay_nada_que_cargar(tmp_path: Path):
    assert modulo_importacion.cargar_importacion(tmp_path) is None


def test_guardar_y_cargar_importacion_hace_ida_y_vuelta(tmp_path: Path):
    original = modulo_importacion.Importacion(
        experiencias=[_experiencia()], skills=[_skill()], avisos=["ojo con esto"]
    )
    modulo_importacion.guardar_importacion(tmp_path, original)
    recargada = modulo_importacion.cargar_importacion(tmp_path)
    assert recargada == original


def test_borrar_importacion_la_deja_indisponible(tmp_path: Path):
    modulo_importacion.guardar_importacion(
        tmp_path, modulo_importacion.Importacion(experiencias=[_experiencia()])
    )
    modulo_importacion.borrar_importacion(tmp_path)
    assert modulo_importacion.cargar_importacion(tmp_path) is None


def test_borrar_importacion_sin_fichero_no_falla(tmp_path: Path):
    modulo_importacion.borrar_importacion(tmp_path)  # no debe lanzar


def test_un_fichero_de_importacion_corrupto_no_revienta(tmp_path: Path):
    (tmp_path / modulo_importacion.NOMBRE_FICHERO).write_text("esto no es JSON", encoding="utf-8")
    assert modulo_importacion.cargar_importacion(tmp_path) is None


# --------------------------------------------------------------------------
# Rutas HTTP
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
    modulo_importacion.guardar_importacion(
        tmp_path / "perfil",
        modulo_importacion.Importacion(experiencias=[_experiencia()], skills=[_skill()]),
    )
    respuesta = cliente_web.get("/perfil/importar/revisar")
    assert "ML Developer".encode("utf-8") in respuesta.data
    assert "Python".encode("utf-8") in respuesta.data


def test_guardar_solo_lo_marcado(cliente_web, tmp_path: Path):
    raiz = tmp_path / "perfil"
    modulo_importacion.guardar_importacion(
        raiz,
        modulo_importacion.Importacion(
            experiencias=[_experiencia("uno"), _experiencia("dos")], skills=[_skill()]
        ),
    )
    cliente_web.post(
        "/perfil/importar/guardar",
        data={
            "exp-0": "1",
            "exp-0-titulo_es": "ML Developer",
            "exp-0-titulo_en": "ML Developer",
            "exp-0-periodo_es": "2026",
            "exp-0-periodo_en": "2026",
            "exp-0-bullets_es": "Pipeline completo",
            "exp-0-bullets_en": "Full pipeline",
            "exp-0-stack_es": "Python",
            "exp-0-stack_en": "Python",
            # "exp-1" no viene en el formulario: no estaba marcado
        },
    )
    perfil = almacen.cargar_perfil(raiz)
    assert perfil.experiencia("uno") is not None
    assert perfil.experiencia("dos") is None
    assert perfil.skill("python") is None  # tampoco estaba marcado


def test_guardar_permite_editar_antes_de_confirmar(cliente_web, tmp_path: Path):
    raiz = tmp_path / "perfil"
    modulo_importacion.guardar_importacion(
        raiz, modulo_importacion.Importacion(skills=[_skill()])
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
    perfil = almacen.cargar_perfil(raiz)
    assert perfil.skill("python").nombre["es"] == "Python avanzado"


def test_una_candidata_incompleta_no_se_guarda_pero_avisa(cliente_web, tmp_path: Path):
    """Si al editar se borra el nombre en inglés, la validación normal la
    rechaza — igual que en el formulario manual — en vez de guardarla rota."""
    raiz = tmp_path / "perfil"
    modulo_importacion.guardar_importacion(
        raiz, modulo_importacion.Importacion(skills=[_skill()])
    )
    respuesta = cliente_web.post(
        "/perfil/importar/guardar",
        data={"skill-0": "1", "skill-0-nombre_es": "Python", "skill-0-nombre_en": ""},
        follow_redirects=True,
    )
    perfil = almacen.cargar_perfil(raiz)
    assert perfil.skill("python") is None
    assert "no se pudieron guardar".encode("utf-8") in respuesta.data


def test_guardar_limpia_la_importacion_pendiente(cliente_web, tmp_path: Path):
    raiz = tmp_path / "perfil"
    modulo_importacion.guardar_importacion(raiz, modulo_importacion.Importacion(skills=[_skill()]))
    cliente_web.post("/perfil/importar/guardar", data={"skill-0": "1", "skill-0-nombre_es": "Python", "skill-0-nombre_en": "Python"})
    assert modulo_importacion.cargar_importacion(raiz) is None


def test_guardar_sin_importacion_pendiente_redirige(cliente_web):
    respuesta = cliente_web.post("/perfil/importar/guardar", data={})
    assert respuesta.status_code == 302


def test_descartar_borra_la_importacion_sin_guardar_nada(cliente_web, tmp_path: Path):
    raiz = tmp_path / "perfil"
    modulo_importacion.guardar_importacion(raiz, modulo_importacion.Importacion(skills=[_skill()]))
    cliente_web.post("/perfil/importar/descartar")
    assert modulo_importacion.cargar_importacion(raiz) is None
    assert almacen.cargar_perfil(raiz).skill("python") is None


def test_un_perfil_vacio_enlaza_a_importar_desde_mi_perfil(cliente_web):
    respuesta = cliente_web.get("/perfil")
    assert b'href="/perfil/importar"' in respuesta.data


def test_el_pie_de_cualquier_pantalla_enlaza_a_importar(cliente_web):
    respuesta = cliente_web.get("/ajustes")
    assert b'href="/perfil/importar"' in respuesta.data


def test_subir_un_formato_no_soportado_muestra_el_error(cliente_web):
    datos = {"fichero": (io.BytesIO(b"contenido cualquiera"), "cv.txt")}
    respuesta = cliente_web.post(
        "/perfil/importar", data=datos, content_type="multipart/form-data"
    )
    assert respuesta.status_code == 200
    assert "no es un formato soportado".encode("utf-8") in respuesta.data
