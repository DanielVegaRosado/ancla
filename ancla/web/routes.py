"""Where the app's folders live: the writable one for the user's data, and
the read-only one the bundled templates ship in.

There is no database: `perfil/` (which also holds the archived `cvs/`) and
`ajustes.json` are plain files in a real folder on disk, so that folder has
to survive restarts and updates of the app itself.

Running from source (`python run.py`, tests, development) both folders are
the repository root. A packaged app cannot write next to its own code:

- PyInstaller (`sys.frozen`) self-extracts into a different temp folder on
  every launch (`sys._MEIPASS`). The executable's own folder is no better:
  on Windows it may be `Program Files` (not writable) and a new version is
  usually unzipped somewhere else; on macOS it is inside `Ancla.app`, which
  is replaced on update and, for an unsigned app opened where it was
  downloaded, runs from a randomized read-only copy (App Translocation).
- Flatpak installs the code in `/app`, read-only, and its `$HOME` is an
  in-memory folder discarded on exit unless the app is granted
  `--filesystem=home`; the per-app `$XDG_DATA_HOME` is the only persistent
  place.

So packaged builds keep user data in the OS's per-user data folder.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "Ancla"
FLATPAK_APP_ID = "com.danielvegarosado.Ancla"
PROFILE_DIR_NAME = "perfil"
SETTINGS_FILE_NAME = "ajustes.json"


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def is_flatpak() -> bool:
    """Compares against this app's own id rather than just checking that
    `FLATPAK_ID` exists: a terminal inside another Flatpak (a sandboxed
    IDE, say) also sets it, and running from source there must keep using
    the repository root."""
    return os.environ.get("FLATPAK_ID") == FLATPAK_APP_ID


def is_packaged() -> bool:
    return is_frozen() or is_flatpak()


def executable_dir() -> Path:
    return Path(sys.executable).resolve().parent


def source_root() -> Path:
    return Path(__file__).resolve().parents[2]


def data_root() -> Path:
    return user_data_dir() if is_packaged() else source_root()


def templates_root() -> Path:
    """Where `canva-templates/` and `html-templates/` ship, never written to.

    Windows carries them as plain folders next to `Ancla.exe`, so users
    can drop their own templates in. On macOS they are bundled inside the
    executable instead (see `desktop.spec`): folders sitting next to
    `Ancla.app` are left behind when App Translocation runs the app from a
    randomized copy, or when only the `.app` is dragged to Applications.
    Flatpak installs them next to the source code, like running from source.
    """
    if not is_frozen():
        return source_root()
    if sys.platform == "darwin":
        return Path(sys._MEIPASS)
    return executable_dir()


def user_data_dir() -> Path:
    if sys.platform == "win32":
        return Path(os.environ["APPDATA"]) / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    return _xdg_data_home() / APP_NAME


def _xdg_data_home() -> Path:
    configured = os.environ.get("XDG_DATA_HOME")
    return Path(configured) if configured else Path.home() / ".local" / "share"
