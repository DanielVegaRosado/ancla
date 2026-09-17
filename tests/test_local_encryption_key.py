"""Tests for the encryption key a packaged desktop build generates for itself
when `ANCLA_CLAVE_CIFRADO` is not set, and for the hosted case keeping its
explicit failure."""
from __future__ import annotations

from pathlib import Path

import pytest

from ancla.web import create_app
from ancla.web import settings as modulo_ajustes
from ancla.web.settings import Settings, SettingsError, load_settings, save_settings


@pytest.fixture
def sin_variable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """No env var, and the OS data folder redirected to a temp dir."""
    monkeypatch.delenv(modulo_ajustes.VARIABLE_ENTORNO_CLAVE_CIFRADO, raising=False)
    carpeta_datos = tmp_path / "datos-del-sistema"
    monkeypatch.setattr(modulo_ajustes, "user_data_dir", lambda: carpeta_datos)
    return carpeta_datos


@pytest.fixture
def empaquetada(monkeypatch: pytest.MonkeyPatch, sin_variable: Path) -> Path:
    monkeypatch.setattr(modulo_ajustes, "is_packaged", lambda: True)
    return sin_variable


def test_la_build_empaquetada_genera_y_reutiliza_su_clave(tmp_path: Path, empaquetada: Path):
    ruta = tmp_path / "ajustes.json"

    save_settings(Settings(proveedor="groq", clave_api="gsk_secreta"), ruta)

    fichero_clave = empaquetada / modulo_ajustes.NOMBRE_FICHERO_CLAVE_CIFRADO
    clave = fichero_clave.read_text(encoding="utf-8")
    assert clave
    assert "gsk_secreta" not in ruta.read_text(encoding="utf-8")
    assert load_settings(ruta).clave_api == "gsk_secreta"
    # A second save must not replace the key: the first one is still readable.
    save_settings(Settings(proveedor="groq", claves_api={"groq": "gsk_secreta", "openai": "sk_otra"}), ruta)
    assert fichero_clave.read_text(encoding="utf-8") == clave
    assert load_settings(ruta).claves_api == {"groq": "gsk_secreta", "openai": "sk_otra"}


def test_la_variable_de_entorno_tiene_prioridad_sobre_el_fichero(
    tmp_path: Path, empaquetada: Path, monkeypatch: pytest.MonkeyPatch
):
    from cryptography.fernet import Fernet

    monkeypatch.setenv(modulo_ajustes.VARIABLE_ENTORNO_CLAVE_CIFRADO, Fernet.generate_key().decode())

    save_settings(Settings(proveedor="groq", clave_api="gsk_secreta"), tmp_path / "ajustes.json")

    assert not (empaquetada / modulo_ajustes.NOMBRE_FICHERO_CLAVE_CIFRADO).exists()


def test_fuera_de_la_build_empaquetada_sigue_fallando_explicito(tmp_path: Path, sin_variable: Path):
    """The hosted deployment (Render, gunicorn) runs from source: generating a
    key per worker there would make one worker unable to read what another
    saved, so a missing variable must keep failing."""
    ruta = tmp_path / "ajustes.json"

    with pytest.raises(SettingsError, match=modulo_ajustes.VARIABLE_ENTORNO_CLAVE_CIFRADO):
        save_settings(Settings(proveedor="groq", clave_api="gsk_secreta"), ruta)

    assert not ruta.exists()
    assert not sin_variable.exists()


def _cliente(tmp_path: Path):
    app = create_app(raiz_perfil=tmp_path / "perfil", settings_path=tmp_path / "ajustes.json", require_login=False)
    app.config["TESTING"] = True
    return app.test_client()


def test_guardar_una_clave_en_ajustes_funciona_en_escritorio_entre_arranques(
    tmp_path: Path, empaquetada: Path
):
    respuesta = _cliente(tmp_path).post(
        "/ajustes", data={"proveedor": "groq", "clave_api": "gsk_de_escritorio"}, follow_redirects=True
    )
    assert modulo_ajustes.VARIABLE_ENTORNO_CLAVE_CIFRADO.encode() not in respuesta.data

    # A new app over the same data folder stands in for a second launch.
    html = _cliente(tmp_path).get("/ajustes").data.decode("utf-8")
    assert "gsk_de_escritorio" in html


def test_guardar_una_clave_en_ajustes_sin_variable_avisa_fuera_de_escritorio(
    tmp_path: Path, sin_variable: Path
):
    respuesta = _cliente(tmp_path).post(
        "/ajustes", data={"proveedor": "groq", "clave_api": "gsk_alojada"}, follow_redirects=True
    )

    assert modulo_ajustes.VARIABLE_ENTORNO_CLAVE_CIFRADO.encode() in respuesta.data
    assert not (tmp_path / "ajustes.json").exists() or "gsk_alojada" not in (tmp_path / "ajustes.json").read_text()
