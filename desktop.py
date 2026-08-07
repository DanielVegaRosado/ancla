"""Desktop launcher: starts the Flask server on a thread and shows it in a
native window with pywebview, instead of in a browser tab. It's the entry
point PyInstaller packages (`desktop.spec`) for the desktop build.

Anyone running the app from source keeps using `run.py`, which opens the
system browser and does not depend on pywebview — that path is unchanged.
"""
from __future__ import annotations

import os
import socket
import threading
import time

HOST = "127.0.0.1"
PORT = int(os.environ.get("ANCLA_PUERTO", "5000"))
TITLE = "Ancla"


def _start_server() -> None:
    from ancla.web import create_app

    create_app().run(host=HOST, port=PORT, debug=False, use_reloader=False)


def _wait_for_server(host: str, port: int, attempts: int = 50, wait: float = 0.1) -> None:
    """Retries connecting until Flask starts listening, instead of a fixed
    wait: on a slow computer a fixed second might not be enough, and the
    window would open against a server that still isn't responding."""
    for _ in range(attempts):
        try:
            with socket.create_connection((host, port), timeout=0.2):
                return
        except OSError:
            time.sleep(wait)
    raise RuntimeError("The server did not start in time.")


def main() -> None:
    import webview

    thread = threading.Thread(target=_start_server, daemon=True)
    thread.start()
    _wait_for_server(HOST, PORT)

    webview.create_window(TITLE, f"http://{HOST}:{PORT}", width=1100, height=780, min_size=(760, 560))
    webview.start()


if __name__ == "__main__":
    main()
