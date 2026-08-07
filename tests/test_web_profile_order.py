"""Tests for panel order on My profile: it is saved in Settings and
honoured when rendering, and an invalid order never hides a section."""
from __future__ import annotations

from pathlib import Path

import pytest

from ancla.web import settings as modulo_ajustes
from ancla.web import create_app


@pytest.fixture
def cliente_web(tmp_path: Path):
    app = create_app(raiz_perfil=tmp_path / "perfil", settings_path=tmp_path / "ajustes.json")
    app.config["TESTING"] = True
    return app.test_client()


def test_el_orden_por_defecto_es_experiencias_primero(cliente_web):
    respuesta = cliente_web.get("/perfil")
    html = respuesta.data.decode("utf-8")
    assert html.index('id="experiencias"') < html.index('id="skills"') < html.index('id="idiomas"')


def test_guardar_un_orden_valido_lo_persiste_y_se_refleja_al_recargar(cliente_web, tmp_path: Path):
    respuesta = cliente_web.post(
        "/perfil/orden",
        json={"orden": ["idiomas", "skills", "skills_personales", "experiencias"]},
    )
    assert respuesta.status_code == 200
    assert respuesta.get_json() == {"ok": True}

    guardados = modulo_ajustes.load_settings(tmp_path / "ajustes.json")
    assert guardados.orden_perfil == ["idiomas", "skills", "skills_personales", "experiencias"]

    html = cliente_web.get("/perfil").data.decode("utf-8")
    assert html.index('id="idiomas"') < html.index('id="skills"') < html.index('id="experiencias"')


def test_un_orden_incompleto_cae_al_orden_por_defecto_sin_reventar(cliente_web, tmp_path: Path):
    respuesta = cliente_web.post("/perfil/orden", json={"orden": ["skills", "idiomas"]})
    assert respuesta.status_code == 200

    guardados = modulo_ajustes.load_settings(tmp_path / "ajustes.json")
    assert guardados.orden_perfil == list(modulo_ajustes.SECCIONES_PERFIL)


def test_un_orden_con_una_clave_desconocida_cae_al_orden_por_defecto(cliente_web, tmp_path: Path):
    respuesta = cliente_web.post(
        "/perfil/orden",
        json={"orden": ["experiencias", "skills", "skills_personales", "algo-inventado"]},
    )
    assert respuesta.status_code == 200
    guardados = modulo_ajustes.load_settings(tmp_path / "ajustes.json")
    assert guardados.orden_perfil == list(modulo_ajustes.SECCIONES_PERFIL)


def test_un_cuerpo_vacio_no_revienta(cliente_web):
    respuesta = cliente_web.post("/perfil/orden")
    assert respuesta.status_code == 200


def test_guardar_la_clave_de_api_no_resetea_un_orden_ya_guardado(cliente_web, tmp_path: Path):
    """Real bug caught while building this: the Settings form used to
    create a brand-new `Settings` from scratch and wiped out the order."""
    cliente_web.post("/perfil/orden", json={"orden": ["idiomas", "skills", "skills_personales", "experiencias"]})

    cliente_web.post("/ajustes", data={"proveedor": "groq", "clave_api": "gsk_test123"})

    guardados = modulo_ajustes.load_settings(tmp_path / "ajustes.json")
    assert guardados.clave_api == "gsk_test123"
    assert guardados.orden_perfil == ["idiomas", "skills", "skills_personales", "experiencias"]
