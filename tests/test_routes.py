"""Tests for where the data and template folders live.

The cases that really matter are the packaged ones: user data must end up
in a folder that survives restarts and updates (never PyInstaller's temp
self-extraction folder, never next to the executable, never Flatpak's
in-memory `$HOME`), while running from source keeps using the repository.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from ancla.web.routes import FLATPAK_APP_ID, data_root, templates_root

RAIZ_REPOSITORIO = Path(__file__).resolve().parents[1]


@pytest.fixture
def desde_fuente(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.delenv("FLATPAK_ID", raising=False)


@pytest.fixture
def congelada(monkeypatch, tmp_path: Path):
    """PyInstaller build whose executable sits in `tmp_path / "descarga"`."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "descarga" / "Ancla.exe"))
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "_MEI123"), raising=False)
    monkeypatch.delenv("FLATPAK_ID", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData" / "Roaming"))


def test_desde_fuente_datos_y_plantillas_en_la_raiz_del_repositorio(desde_fuente):
    assert data_root() == RAIZ_REPOSITORIO
    assert templates_root() == RAIZ_REPOSITORIO


def test_desde_fuente_dentro_de_otro_flatpak_sigue_usando_el_repositorio(desde_fuente, monkeypatch):
    """A terminal inside another sandboxed app (an IDE) also sets FLATPAK_ID."""
    monkeypatch.setenv("FLATPAK_ID", "com.visualstudio.code")
    assert data_root() == RAIZ_REPOSITORIO


def test_congelada_en_windows_los_datos_van_a_appdata(congelada, monkeypatch, tmp_path: Path):
    monkeypatch.setattr(sys, "platform", "win32")
    assert data_root() == tmp_path / "AppData" / "Roaming" / "Ancla"


def test_congelada_en_macos_los_datos_van_a_application_support(congelada, monkeypatch, tmp_path: Path):
    monkeypatch.setattr(sys, "platform", "darwin")
    assert data_root() == tmp_path / "home" / "Library" / "Application Support" / "Ancla"


def test_congelada_en_linux_los_datos_van_a_xdg_data_home(congelada, monkeypatch, tmp_path: Path):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    assert data_root() == tmp_path / "home" / ".local" / "share" / "Ancla"


@pytest.mark.parametrize("sistema", ["win32", "darwin", "linux"])
def test_congelada_nunca_guarda_datos_junto_al_ejecutable_ni_en_la_temporal(
    congelada, monkeypatch, tmp_path: Path, sistema
):
    monkeypatch.setattr(sys, "platform", sistema)
    assert tmp_path / "descarga" not in data_root().parents
    assert tmp_path / "_MEI123" not in data_root().parents


def test_congelada_en_windows_las_plantillas_junto_al_exe(congelada, monkeypatch, tmp_path: Path):
    monkeypatch.setattr(sys, "platform", "win32")
    assert templates_root() == tmp_path / "descarga"


def test_congelada_en_macos_las_plantillas_dentro_del_ejecutable(congelada, monkeypatch, tmp_path: Path):
    """Folders next to Ancla.app are lost under App Translocation."""
    monkeypatch.setattr(sys, "platform", "darwin")
    assert templates_root() == tmp_path / "_MEI123"


def test_dentro_del_flatpak_los_datos_van_a_xdg_data_home_no_a_home(desde_fuente, monkeypatch, tmp_path: Path):
    """Inside the sandbox `$HOME` is an in-memory folder thrown away on
    exit; only `$XDG_DATA_HOME` persists."""
    monkeypatch.setenv("FLATPAK_ID", FLATPAK_APP_ID)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("HOME", str(tmp_path / "home-efimero"))
    monkeypatch.setattr(sys, "platform", "linux")

    assert data_root() == tmp_path / "data" / "Ancla"


def test_dentro_del_flatpak_las_plantillas_junto_al_codigo(desde_fuente, monkeypatch, tmp_path: Path):
    monkeypatch.setenv("FLATPAK_ID", FLATPAK_APP_ID)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    assert templates_root() == RAIZ_REPOSITORIO
