"""Tests del lanzador de escritorio. Solo cubre `_esperar_servidor`: es la
única parte que no es directamente abrir una ventana nativa, así que es lo
único que se puede probar de verdad sin un entorno gráfico (igual que
`run.py`, que tampoco tiene tests, no se prueba aquí lo que abre la ventana
en sí)."""
from __future__ import annotations

import socket
import threading
import time

import pytest

from escritorio import _esperar_servidor


def _puerto_libre() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_no_espera_si_el_servidor_ya_escucha():
    puerto = _puerto_libre()
    servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    servidor.bind(("127.0.0.1", puerto))
    servidor.listen(1)
    try:
        _esperar_servidor("127.0.0.1", puerto, intentos=5, espera=0.01)
    finally:
        servidor.close()


def test_espera_hasta_que_el_servidor_empieza_a_escuchar():
    puerto = _puerto_libre()

    def _arrancar_con_retraso():
        time.sleep(0.2)
        servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        servidor.bind(("127.0.0.1", puerto))
        servidor.listen(1)
        time.sleep(0.5)
        servidor.close()

    hilo = threading.Thread(target=_arrancar_con_retraso, daemon=True)
    hilo.start()

    _esperar_servidor("127.0.0.1", puerto, intentos=50, espera=0.05)


def test_lanza_un_error_claro_si_nunca_arranca():
    puerto = _puerto_libre()
    with pytest.raises(RuntimeError):
        _esperar_servidor("127.0.0.1", puerto, intentos=3, espera=0.01)
