"""Tests for copying user data from where earlier packaged builds kept it
(next to the executable) into the per-user data folder."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from ancla.web.legacy_data import copy_legacy_data


@pytest.fixture
def carpeta_vieja(tmp_path: Path) -> Path:
    vieja = tmp_path / "junto-al-exe"
    (vieja / "perfil" / "experience").mkdir(parents=True)
    (vieja / "perfil" / "experience" / "acme.yaml").write_text("empresa: Acme\n")
    (vieja / "perfil" / "cvs").mkdir()
    (vieja / "perfil" / "cvs" / "cv-1.yaml").write_text("id: cv-1\n")
    (vieja / "ajustes.json").write_text('{"proveedor": "groq"}')
    return vieja


def test_copia_perfil_con_cvs_y_ajustes(carpeta_vieja: Path, tmp_path: Path):
    nueva = tmp_path / "AppData" / "Ancla"

    copiados = copy_legacy_data(carpeta_vieja, nueva)

    assert copiados == ["perfil", "ajustes.json"]
    assert (nueva / "perfil" / "experience" / "acme.yaml").read_text() == "empresa: Acme\n"
    assert (nueva / "perfil" / "cvs" / "cv-1.yaml").exists()
    assert (nueva / "ajustes.json").read_text() == '{"proveedor": "groq"}'


def test_no_borra_ni_toca_el_origen(carpeta_vieja: Path, tmp_path: Path):
    copy_legacy_data(carpeta_vieja, tmp_path / "nueva")

    assert (carpeta_vieja / "perfil" / "experience" / "acme.yaml").read_text() == "empresa: Acme\n"
    assert (carpeta_vieja / "ajustes.json").exists()


def test_no_sobrescribe_lo_que_ya_hay_en_destino(carpeta_vieja: Path, tmp_path: Path):
    nueva = tmp_path / "nueva"
    (nueva / "perfil").mkdir(parents=True)
    (nueva / "perfil" / "contact.yaml").write_text("nombre: Nuevo\n")

    copiados = copy_legacy_data(carpeta_vieja, nueva)

    assert copiados == ["ajustes.json"]
    assert (nueva / "perfil" / "contact.yaml").read_text() == "nombre: Nuevo\n"
    assert not (nueva / "perfil" / "experience").exists()


def test_no_se_repite_en_el_siguiente_arranque(carpeta_vieja: Path, tmp_path: Path):
    nueva = tmp_path / "nueva"
    copy_legacy_data(carpeta_vieja, nueva)
    (nueva / "ajustes.json").write_text('{"proveedor": "anthropic"}')

    assert copy_legacy_data(carpeta_vieja, nueva) == []
    assert (nueva / "ajustes.json").read_text() == '{"proveedor": "anthropic"}'


def test_sin_datos_viejos_no_hace_nada(tmp_path: Path):
    nueva = tmp_path / "nueva"
    assert copy_legacy_data(tmp_path / "vacia", nueva) == []
    assert not nueva.exists()


def test_una_copia_interrumpida_se_completa_en_el_siguiente_arranque(carpeta_vieja: Path, tmp_path: Path):
    """A crash midway leaves only the temporary copy, never a `perfil/`
    that would look complete and stop the retry."""
    nueva = tmp_path / "nueva"
    (nueva / "perfil.copying" / "experience").mkdir(parents=True)

    copy_legacy_data(carpeta_vieja, nueva)

    assert (nueva / "perfil" / "experience" / "acme.yaml").exists()
    assert (nueva / "perfil" / "cvs" / "cv-1.yaml").exists()
    assert not (nueva / "perfil.copying").exists()


def test_un_fallo_al_copiar_no_impide_arrancar_y_se_reintenta(carpeta_vieja: Path, tmp_path: Path, monkeypatch):
    nueva = tmp_path / "nueva"

    def _falla(*_args, **_kwargs):
        raise PermissionError("read-only")

    monkeypatch.setattr(shutil, "copytree", _falla)
    assert copy_legacy_data(carpeta_vieja, nueva) == ["ajustes.json"]
    assert not (nueva / "perfil").exists()

    monkeypatch.undo()
    assert copy_legacy_data(carpeta_vieja, nueva) == ["perfil"]


def test_origen_de_solo_lectura_se_copia_igual(carpeta_vieja: Path, tmp_path: Path):
    """App Translocation runs the old bundle from a read-only copy."""
    for ruta in [carpeta_vieja, *carpeta_vieja.rglob("*")]:
        ruta.chmod(0o555 if ruta.is_dir() else 0o444)
    try:
        assert copy_legacy_data(carpeta_vieja, tmp_path / "nueva") == ["perfil", "ajustes.json"]
        (tmp_path / "nueva" / "perfil" / "experience" / "nueva.yaml").write_text("se puede guardar\n")
        (tmp_path / "nueva" / "ajustes.json").write_text("{}")
    finally:
        for ruta in [carpeta_vieja, *carpeta_vieja.rglob("*")]:
            ruta.chmod(0o755 if ruta.is_dir() else 0o644)


def test_misma_carpeta_de_origen_y_destino_no_hace_nada(carpeta_vieja: Path):
    assert copy_legacy_data(carpeta_vieja, carpeta_vieja) == []
