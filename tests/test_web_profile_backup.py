"""HTTP tests for the profile backup download (`/perfil/exportar-zip`)."""
from __future__ import annotations

import zipfile
from io import BytesIO
from pathlib import Path

import pytest

from ancla.profile import store
from ancla.profile.model import AboutMe, Bilingual
from ancla.web import create_app


@pytest.fixture
def cliente_web(tmp_path: Path):
    app = create_app(raiz_perfil=tmp_path / "perfil", settings_path=tmp_path / "ajustes.json")
    app.config["TESTING"] = True
    return app.test_client()


def test_exportar_zip_descarga_un_zip_con_el_perfil(cliente_web, tmp_path: Path):
    # Cualquier guardado crea la carpeta del perfil; el "Sobre mí" es el más simple.
    store.save_about_me(
        tmp_path / "perfil", AboutMe(template=Bilingual(es="Hola", en="Hello"))
    )

    respuesta = cliente_web.get("/perfil/exportar-zip")

    assert respuesta.status_code == 200
    assert respuesta.mimetype == "application/zip"
    assert 'attachment; filename="ancla-perfil.zip"' in respuesta.headers["Content-Disposition"]
    with zipfile.ZipFile(BytesIO(respuesta.data)) as zip_:
        assert zip_.namelist()  # no está vacío


def test_boton_de_copia_de_seguridad_no_aparece_en_modo_demo(tmp_path: Path):
    app = create_app(raiz_perfil=tmp_path / "perfil", settings_path=tmp_path / "ajustes.json", demo_mode=True)
    app.config["TESTING"] = True
    cliente = app.test_client()

    respuesta = cliente.get("/ajustes")

    assert "exportar-zip".encode("utf-8") not in respuesta.data
