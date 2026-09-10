"""One-way copy of user data from where earlier packaged builds kept it.

Earlier Windows/macOS builds stored `perfil/` and `ajustes.json` next to
the executable (inside `Ancla.app/Contents/MacOS` on macOS). Packaged builds
now use the per-user data folder (see `routes.py`); without this, users
updating in place would open an empty app while their data sat untouched
in the old location.

Copy, never move: the old folder may be read-only (App Translocation on
macOS), and leaving it intact means a failed or interrupted copy can never
lose anything — the next launch simply tries again.

Each item is copied only if the destination does not have it yet, so data
the user already has in the new folder is never overwritten, and once an
item has arrived the copy is not repeated on later launches. An item is
first copied under a temporary name and renamed into place in one step,
so a crash midway leaves no half-copied `perfil/` that would look complete
on the next launch.
"""
from __future__ import annotations

import logging
import os
import shutil
import stat
from pathlib import Path

from ancla.web.routes import PROFILE_DIR_NAME, SETTINGS_FILE_NAME

LEGACY_ITEMS = (PROFILE_DIR_NAME, SETTINGS_FILE_NAME)
_PARTIAL_SUFFIX = ".copying"

_log = logging.getLogger(__name__)


def copy_legacy_data(legacy_root: Path, data_root: Path) -> list[str]:
    """Returns the names of the items copied. Failures are logged, not
    raised: the app must still open, and the untouched original means the
    next launch can retry."""
    if legacy_root.resolve() == data_root.resolve():
        return []
    copied = []
    for name in LEGACY_ITEMS:
        source = legacy_root / name
        target = data_root / name
        if not source.exists() or target.exists():
            continue
        try:
            _copy_into_place(source, target)
        except OSError:
            _log.warning("Could not copy %s to %s", source, target, exc_info=True)
            continue
        copied.append(name)
    return copied


def _copy_into_place(source: Path, target: Path) -> None:
    partial = target.with_name(target.name + _PARTIAL_SUFFIX)
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, partial, copy_function=shutil.copyfile, dirs_exist_ok=True)
    else:
        shutil.copyfile(source, partial)
    _make_writable(partial)
    os.replace(partial, target)


def _make_writable(path: Path) -> None:
    """`copytree` always carries each folder's permissions over, and a
    source that was read-only (translocated, or marked read-only by hand)
    would give the app a profile it then cannot save to."""
    for entry in [path, *path.rglob("*")]:
        entry.chmod(entry.stat().st_mode | stat.S_IWUSR)
