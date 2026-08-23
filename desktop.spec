# -*- mode: python ; coding: utf-8 -*-
"""Packages desktop.py as a single executable with PyInstaller.

One .spec for both Windows and macOS, with the real difference between them
resolved through `sys.platform` rather than two separate files:

- Windows: the `.exe` from `EXE(...)` already is "the program", a standalone
  file you double-click. That's exactly the portable executable we want.
- macOS: a bare Unix binary isn't something you can double-click from Finder,
  and it carries no icon of its own. It has to be wrapped in a `.app` via
  `BUNDLE(...)`. Technically that's a folder, but Finder treats it as a single
  icon, which is how macOS natively gives you the same behaviour as Windows.

PyInstaller doesn't cross-compile: this .spec produces the .exe when run ON
Windows and the .app when run ON macOS. See the GitHub Actions workflow
(`.github/workflows/build-desktop.yml`) to build both at once, one per
operating system.
"""
import sys

NAME = "Ancla"
VERSION = "1.0.0"
ICONS_FOLDER = "empaquetado/iconos"
WINDOWS_ICON = f"{ICONS_FOLDER}/ancla.ico"
MACOS_ICON = f"{ICONS_FOLDER}/ancla.icns"
WINDOWS_VERSION_INFO = "empaquetado/version_info.txt"

a = Analysis(
    ["desktop.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("ancla/web/templates", "ancla/web/templates"),
        ("ancla/web/static", "ancla/web/static"),
    ],
    hiddenimports=[
        # pywebview picks its backend at runtime based on the operating system,
        # not through static imports, which is precisely what PyInstaller's
        # static analysis can fail to detect on its own.
        "webview.platforms.winforms" if sys.platform == "win32" else "webview.platforms.cocoa",
    ],
    hookspath=[],
    # pywebview supports several backends (winforms, Qt...) and picks one at
    # runtime, but `hiddenimports` above already forces which one to use per
    # system. If the build environment has more than one set of Qt bindings
    # installed at once (say PyQt5 and PySide6 in a busy conda "base"),
    # PyInstaller aborts the build because it can't package both, and none of
    # them are needed here anyway.
    excludes=["PyQt5", "PyQt6", "PySide2", "PySide6"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=NAME if sys.platform != "darwin" else "desktop",
    console=False,  # a window, not a console behind it
    onefile=True,
    icon=WINDOWS_ICON if sys.platform == "win32" else MACOS_ICON,
    # SignPath Foundation requires signed binaries to carry consistent product
    # name and version metadata. macOS takes it from BUNDLE()'s `version` below;
    # the PE resource only applies on Windows, since version_info.txt uses
    # PyInstaller's Windows-only VSVersionInfo format.
    version=WINDOWS_VERSION_INFO if sys.platform == "win32" else None,
)

if sys.platform == "darwin":
    app = BUNDLE(
        exe,
        name=f"{NAME}.app",
        icon=MACOS_ICON,
        bundle_identifier="com.danielvegarosado.ancla",
        version=VERSION,
    )
