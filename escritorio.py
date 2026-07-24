"""Lanzador de escritorio: arranca el servidor Flask en un hilo y lo enseña
en una ventana nativa con pywebview, en vez de en una pestaña del
navegador. Es el punto de entrada que empaqueta PyInstaller
(`escritorio.spec`) para la versión de escritorio.

Quien ejecuta la app desde el código fuente sigue usando `run.py`, que abre
el navegador del sistema y no depende de pywebview — ese camino no cambia.
"""
from __future__ import annotations

import os
import socket
import threading
import time

HOST = "127.0.0.1"
PUERTO = int(os.environ.get("CV_ADAPTATIVO_PUERTO", "5000"))
TITULO = "CV Adaptativo"


def _arrancar_servidor() -> None:
    from cv_adaptativo.web import crear_app

    crear_app().run(host=HOST, port=PUERTO, debug=False, use_reloader=False)


def _esperar_servidor(host: str, puerto: int, intentos: int = 50, espera: float = 0.1) -> None:
    """Reintenta conectar hasta que Flask empiece a escuchar, en vez de una
    espera fija: en un ordenador lento un segundo fijo puede no bastar, y la
    ventana se abriría contra un servidor que todavía no responde."""
    for _ in range(intentos):
        try:
            with socket.create_connection((host, puerto), timeout=0.2):
                return
        except OSError:
            time.sleep(espera)
    raise RuntimeError("El servidor no ha arrancado a tiempo.")


def main() -> None:
    import webview

    hilo = threading.Thread(target=_arrancar_servidor, daemon=True)
    hilo.start()
    _esperar_servidor(HOST, PUERTO)

    webview.create_window(TITULO, f"http://{HOST}:{PUERTO}", width=1100, height=780, min_size=(760, 560))
    webview.start()


if __name__ == "__main__":
    main()
