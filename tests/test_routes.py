"""Tests for where the data folder lives by default (perfil/, ajustes.json).

The case that really matters: packaged with PyInstaller (`sys.frozen`), the
folder has to be the executable's own, never the temporary self-extraction
folder — that one gets lost between launches, and the user's profile with
it.
"""
from __future__ import annotations

import sys
from pathlib import Path

from ancla.web.routes import data_root


def test_sin_empaquetar_usa_la_raiz_del_repositorio():
    assert data_root() == Path(__file__).resolve().parents[1]


def test_empaquetada_usa_la_carpeta_del_ejecutable_no_la_temporal(monkeypatch, tmp_path: Path):
    ejecutable = tmp_path / "Ancla.exe"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(ejecutable))

    assert data_root() == tmp_path


def test_sin_frozen_definido_se_comporta_como_no_empaquetada(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert data_root() == Path(__file__).resolve().parents[1]
