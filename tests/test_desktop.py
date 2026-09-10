"""Tests for the desktop launcher. Only covers `_wait_for_server`: it's the
only part that isn't directly opening a native window, so it's the only
thing that can really be tested without a graphical environment (same as
`run.py`, which also has no tests — what opens the window itself isn't
tested here)."""
from __future__ import annotations

import socket
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


def test_fuera_de_flatpak_no_cambia_donde_se_guarda_el_perfil(monkeypatch):
    from desktop import _flatpak_data_root

    monkeypatch.delenv("FLATPAK_ID", raising=False)
    assert _flatpak_data_root() is None


def test_dentro_de_flatpak_el_perfil_va_a_xdg_data_home_no_a_home(monkeypatch, tmp_path):
    """Dentro del sandbox `$HOME` es una carpeta en memoria que se tira al
    cerrar la app; lo único persistente es `$XDG_DATA_HOME`."""
    from desktop import _flatpak_data_root

    monkeypatch.setenv("FLATPAK_ID", "com.danielvegarosado.Ancla")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("HOME", str(tmp_path / "home-efimero"))

    assert _flatpak_data_root() == tmp_path / "data" / "Ancla"
