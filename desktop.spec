# -*- mode: python ; coding: utf-8 -*-
"""Packages desktop.py as a single executable with PyInstaller.

One .spec for Windows, macOS and Linux, with the real differences between
them resolved through `sys.platform` rather than separate files:

- Windows: the `.exe` from `EXE(...)` already is "the program", a standalone
  file you double-click. That's exactly the portable executable we want.
- macOS: a bare Unix binary isn't something you can double-click from Finder,
  and it carries no icon of its own. It has to be wrapped in a `.app` via
  `BUNDLE(...)`. Technically that's a folder, but Finder treats it as a single
  icon, which is how macOS natively gives you the same behaviour as Windows.
- Linux: like Windows, the `EXE(...)` binary is already "the program" — no
  bundle step, just an executable file you run directly.

PyInstaller doesn't cross-compile: this .spec produces the .exe when run ON
Windows, the .app when run ON macOS, and the plain binary when run ON Linux.
See the GitHub Actions workflow (`.github/workflows/build-desktop.yml`) to
build all three at once, one per operating system.
"""
import sys

ES_WINDOWS = sys.platform == "win32"
ES_MACOS = sys.platform == "darwin"

NAME = "Ancla"
VERSION = "1.0.1"
ICONS_FOLDER = "empaquetado/iconos"
WINDOWS_ICON = f"{ICONS_FOLDER}/ancla.ico"
MACOS_ICON = f"{ICONS_FOLDER}/ancla.icns"
WINDOWS_VERSION_INFO = "empaquetado/version_info.txt"

# canva-templates/ and html-templates/ are read-only content, never app
# data. On Windows they ship as plain folders next to Ancla.exe (see
# build-desktop.yml), so users can drop their own templates in without a
# rebuild. On macOS that doesn't hold: App Translocation runs an unsigned
# app from a randomized copy of the .app alone, and dragging Ancla.app to
# Applications leaves any sibling folder behind — so there they are bundled
# into the executable and found through sys._MEIPASS (see templates_root()
# in ancla/web/routes.py). The trade-off: adding your own template on macOS
# means running from source.
TEMPLATE_FOLDERS = ["canva-templates", "html-templates"]

a = Analysis(
    ["desktop.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("ancla/web/templates", "ancla/web/templates"),
        ("ancla/web/static", "ancla/web/static"),
    ]
    + ([(folder, folder) for folder in TEMPLATE_FOLDERS] if ES_MACOS else []),
    hiddenimports=[
        # pywebview picks its backend at runtime based on the operating system,
        # not through static imports, which is precisely what PyInstaller's
        # static analysis can fail to detect on its own. Linux uses the GTK
        # backend (webview.platforms.gtk) — the default and lightest pywebview
        # recommends there, backed by python3-gi + WebKit2GTK at the system
        # level (see build-desktop.yml for the apt packages).
        "webview.platforms.winforms"
        if ES_WINDOWS
        else "webview.platforms.cocoa"
        if ES_MACOS
        else "webview.platforms.gtk",
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
    name=NAME if not ES_MACOS else "desktop",
    console=False,  # a window, not a console behind it
    onefile=True,
    # PyInstaller only applies `icon` on Windows and macOS; on Linux it's a
    # no-op; there's no bundle step to hand it to either, so it's just None.
    icon=WINDOWS_ICON if ES_WINDOWS else MACOS_ICON if ES_MACOS else None,
    # SignPath Foundation requires signed binaries to carry consistent product
    # name and version metadata. macOS takes it from BUNDLE()'s `version` below;
    # the PE resource only applies on Windows, since version_info.txt uses
    # PyInstaller's Windows-only VSVersionInfo format.
    version=WINDOWS_VERSION_INFO if ES_WINDOWS else None,
)

if ES_MACOS:
    app = BUNDLE(
        exe,
        name=f"{NAME}.app",
        icon=MACOS_ICON,
        bundle_identifier="com.danielvegarosado.ancla",
        version=VERSION,
    )
