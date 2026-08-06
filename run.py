"""Arranca la app en local: `python run.py`.

Abre el navegador solo. Para el usuario esto es una aplicación: ejecuta un
fichero y se le abre una ventana; no vuelve a ver la terminal.

**Sin `debug=True`.** El depurador de Werkzeug enseña una consola que ejecuta
código Python arbitrario en cuanto salta una excepción, y esto lo va a arrancar
gente desconocida en su propio ordenador. Para desarrollar:
`flask --app ancla.web run --debug`.

Escucha solo en `127.0.0.1` a propósito: los datos son de quien ejecuta la app
y no tienen por qué quedar expuestos al resto de la red.
"""
from __future__ import annotations

import os
import threading
import webbrowser

from ancla.web import crear_app

HOST = "127.0.0.1"
PUERTO = int(os.environ.get("ANCLA_PUERTO", "5000"))
SEGUNDOS_ANTES_DE_ABRIR = 1.0


def main() -> None:
    url = f"http://{HOST}:{PUERTO}"
    # El navegador se abre desde un hilo aparte y con un respiro: si se abriera
    # antes de que el servidor escuche, el usuario vería un error de conexión y
    # pensaría que la app está rota.
    threading.Timer(SEGUNDOS_ANTES_DE_ABRIR, webbrowser.open, args=[url]).start()

    print(f"Ancla — abriendo {url}")
    print("Deja esta ventana abierta mientras uses la app. Ctrl+C para cerrarla.")
    crear_app().run(host=HOST, port=PUERTO, debug=False)


if __name__ == "__main__":
    main()
