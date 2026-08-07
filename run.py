"""Starts the app locally: `python run.py`.

Just opens the browser. To the user this is an application: they run a
file and a window opens; they never see the terminal again.

**No `debug=True`.** Werkzeug's debugger shows a console that runs arbitrary
Python code the moment an exception is raised, and this is going to be
started by strangers on their own computer. To develop:
`flask --app ancla.web run --debug`.

Listens only on `127.0.0.1` on purpose: the data belongs to whoever is
running the app, and there is no reason for it to be exposed to the rest
of the network.
"""
from __future__ import annotations

import os
import threading
import webbrowser

from ancla.web import create_app

HOST = "127.0.0.1"
PORT = int(os.environ.get("ANCLA_PUERTO", "5000"))
SECONDS_BEFORE_OPENING = 1.0


def main() -> None:
    url = f"http://{HOST}:{PORT}"
    # The browser opens from a separate thread and with a small delay: if it
    # opened before the server was listening, the user would see a connection
    # error and think the app is broken.
    threading.Timer(SECONDS_BEFORE_OPENING, webbrowser.open, args=[url]).start()

    print(f"Ancla — opening {url}")
    print("Leave this window open while you use the app. Ctrl+C to close it.")
    create_app().run(host=HOST, port=PORT, debug=False)


if __name__ == "__main__":
    main()
