"""Where `perfil/`, `ajustes.json`, and `cvs/` live by default.

There is no database: everything is files in a real folder on disk, so
that folder has to survive across restarts and be the same folder the user
sees and can move or back up.

Running from source (`python run.py`, tests, development), that folder is
the repository root. Packaged with PyInstaller into a single executable
(`--onefile`), the runtime self-extracts into a different temp folder on
every launch (`sys._MEIPASS`) — writing there would lose the user's profile
from one session to the next. `sys.frozen` (which PyInstaller sets)
distinguishes the two cases; when packaged, the stable folder is the one
containing the executable itself (`sys.executable`), not the extracted code.
"""
from __future__ import annotations

import sys
from pathlib import Path


def data_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]
