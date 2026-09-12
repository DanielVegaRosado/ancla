"""Tests for encrypting the AI provider keys at rest in `ajustes.json`."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from ancla.web import settings as modulo_ajustes
from ancla.web.settings import Settings, SettingsError, load_settings, save_settings


@pytest.fixture
def clave_cifrado(monkeypatch: pytest.MonkeyPatch) -> str:
    clave = Fernet.generate_key().decode()
    monkeypatch.setenv(modulo_ajustes.VARIABLE_ENTORNO_CLAVE_CIFRADO, clave)
    return clave


def test_el_fichero_en_disco_no_contiene_la_clave_en_texto_plano(tmp_path: Path, clave_cifrado: str):
    ruta = tmp_path / "ajustes.json"
    ajustes = Settings(proveedor="groq", clave_api="gsk_secreta_de_verdad")

    save_settings(ajustes, ruta)

    contenido = ruta.read_text(encoding="utf-8")
    assert "gsk_secreta_de_verdad" not in contenido


def test_se_descifra_bien_al_recargar(tmp_path: Path, clave_cifrado: str):
    ruta = tmp_path / "ajustes.json"
    ajustes = Settings(
        proveedor="groq",
        claves_api={"groq": "gsk_groq", "openai": "sk_openai"},
        modelo="gpt-oss-120b",
    )

    save_settings(ajustes, ruta)
    recargado = load_settings(ruta)

    assert recargado.clave_api == "gsk_groq"
    assert recargado.claves_api == {"groq": "gsk_groq", "openai": "sk_openai"}
    assert recargado.proveedor == "groq"
    assert recargado.modelo == "gpt-oss-120b"


def test_un_ajustes_json_antiguo_sin_cifrar_sigue_funcionando(tmp_path: Path, clave_cifrado: str):
    ruta = tmp_path / "ajustes.json"
    ruta.write_text(
        json.dumps({"proveedor": "groq", "clave_api": "gsk_de_toda_la_vida"}),
        encoding="utf-8",
    )

    ajustes = load_settings(ruta)

    assert ajustes.clave_api == "gsk_de_toda_la_vida"
    assert ajustes.claves_api == {"groq": "gsk_de_toda_la_vida"}


def test_un_ajustes_json_antiguo_no_necesita_la_variable_de_entorno(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(modulo_ajustes.VARIABLE_ENTORNO_CLAVE_CIFRADO, raising=False)
    ruta = tmp_path / "ajustes.json"
    ruta.write_text(
        json.dumps({"proveedor": "groq", "clave_api": "gsk_de_toda_la_vida"}),
        encoding="utf-8",
    )

    ajustes = load_settings(ruta)

    assert ajustes.clave_api == "gsk_de_toda_la_vida"


def test_un_ajustes_json_antiguo_se_cifra_al_volver_a_guardarlo(tmp_path: Path, clave_cifrado: str):
    ruta = tmp_path / "ajustes.json"
    ruta.write_text(
        json.dumps({"proveedor": "groq", "clave_api": "gsk_de_toda_la_vida"}),
        encoding="utf-8",
    )

    ajustes = load_settings(ruta)
    save_settings(ajustes, ruta)

    assert "gsk_de_toda_la_vida" not in ruta.read_text(encoding="utf-8")
    assert load_settings(ruta).clave_api == "gsk_de_toda_la_vida"


def test_guardar_una_clave_sin_la_variable_de_entorno_avisa_con_claridad(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.delenv(modulo_ajustes.VARIABLE_ENTORNO_CLAVE_CIFRADO, raising=False)
    ruta = tmp_path / "ajustes.json"
    ajustes = Settings(proveedor="groq", clave_api="gsk_secreta")

    with pytest.raises(SettingsError, match=modulo_ajustes.VARIABLE_ENTORNO_CLAVE_CIFRADO):
        save_settings(ajustes, ruta)

    assert not ruta.exists()


def test_guardar_sin_ninguna_clave_no_exige_la_variable_de_entorno(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Cambiar solo el idioma, sin haber configurado nunca una clave de API,
    no debe forzar a una instalación local de un solo dueño a definir la
    variable de entorno — no hay nada sensible que cifrar todavía."""
    monkeypatch.delenv(modulo_ajustes.VARIABLE_ENTORNO_CLAVE_CIFRADO, raising=False)
    ruta = tmp_path / "ajustes.json"
    ajustes = Settings(idioma="en")

    save_settings(ajustes, ruta)

    assert load_settings(ruta).idioma == "en"


def test_descifrar_con_una_variable_de_entorno_distinta_avisa_con_claridad(tmp_path: Path, clave_cifrado: str):
    ruta = tmp_path / "ajustes.json"
    save_settings(Settings(proveedor="groq", clave_api="gsk_secreta"), ruta)

    otra_sesion = Fernet.generate_key().decode()
    import os

    os.environ[modulo_ajustes.VARIABLE_ENTORNO_CLAVE_CIFRADO] = otra_sesion
    try:
        with pytest.raises(SettingsError, match=modulo_ajustes.VARIABLE_ENTORNO_CLAVE_CIFRADO):
            load_settings(ruta)
    finally:
        os.environ[modulo_ajustes.VARIABLE_ENTORNO_CLAVE_CIFRADO] = clave_cifrado


def test_no_persiste_el_campo_clave_api_por_separado(tmp_path: Path, clave_cifrado: str):
    """`clave_api` es redundante con `claves_api` (ver `Settings.__post_init__`);
    guardarlo aparte duplicaría el secreto en el fichero."""
    ruta = tmp_path / "ajustes.json"
    save_settings(Settings(proveedor="groq", clave_api="gsk_secreta"), ruta)

    datos = json.loads(ruta.read_text(encoding="utf-8"))

    assert "clave_api" not in datos
