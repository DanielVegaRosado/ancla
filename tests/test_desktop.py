"""Tests for the desktop launcher: the parts that don't open a native
window (waiting for the server, bringing data over from earlier builds).
What opens the window itself can't be tested without a graphical
environment, same as `run.py`."""
from __future__ import annotations

import socket
import sys
import threading
import time

import pytest

from desktop import _wait_for_server


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_no_espera_si_el_servidor_ya_escucha():
    puerto = _free_port()
    servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    servidor.bind(("127.0.0.1", puerto))
    servidor.listen(1)
    try:
        _wait_for_server("127.0.0.1", puerto, attempts=5, wait=0.01)
    finally:
        servidor.close()


def test_espera_hasta_que_el_servidor_empieza_a_escuchar():
    puerto = _free_port()

    def _start_with_delay():
        time.sleep(0.2)
        servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        servidor.bind(("127.0.0.1", puerto))
        servidor.listen(1)
        time.sleep(0.5)
        servidor.close()

    hilo = threading.Thread(target=_start_with_delay, daemon=True)
    hilo.start()

    _wait_for_server("127.0.0.1", puerto, attempts=50, wait=0.05)


def test_lanza_un_error_claro_si_nunca_arranca():
    puerto = _free_port()
    with pytest.raises(RuntimeError):
        _wait_for_server("127.0.0.1", puerto, attempts=3, wait=0.01)


def test_empaquetada_trae_los_datos_de_junto_al_ejecutable(monkeypatch, tmp_path):
    from desktop import _copy_data_from_earlier_versions

    junto_al_exe = tmp_path / "descarga"
    (junto_al_exe / "perfil").mkdir(parents=True)
    (junto_al_exe / "ajustes.json").write_text("{}")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(junto_al_exe / "Ancla.exe"))
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData"))

    _copy_data_from_earlier_versions()

    assert (tmp_path / "AppData" / "Ancla" / "perfil").is_dir()
    assert (tmp_path / "AppData" / "Ancla" / "ajustes.json").exists()


def test_desde_fuente_no_copia_nada(monkeypatch):
    import ancla.web.legacy_data
    from desktop import _copy_data_from_earlier_versions

    llamadas = []
    monkeypatch.setattr(ancla.web.legacy_data, "copy_legacy_data", lambda *args: llamadas.append(args))
    monkeypatch.delattr(sys, "frozen", raising=False)

    _copy_data_from_earlier_versions()

    assert llamadas == []
