"""Tests de dónde vive por defecto la carpeta de datos (perfil/, ajustes.json).

El caso que importa de verdad: empaquetada con PyInstaller (`sys.frozen`),
la carpeta tiene que ser la del ejecutable, nunca la carpeta temporal de
autoextracción — esa se pierde entre arranques y con ella el perfil del
usuario.
"""
from __future__ import annotations

import sys
from pathlib import Path

from cv_adaptativo.web.rutas import raiz_datos


def test_sin_empaquetar_usa_la_raiz_del_repositorio():
    assert raiz_datos() == Path(__file__).resolve().parents[1]


def test_empaquetada_usa_la_carpeta_del_ejecutable_no_la_temporal(monkeypatch, tmp_path: Path):
    ejecutable = tmp_path / "CV Adaptativo.exe"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(ejecutable))

    assert raiz_datos() == tmp_path


def test_sin_frozen_definido_se_comporta_como_no_empaquetada(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert raiz_datos() == Path(__file__).resolve().parents[1]
