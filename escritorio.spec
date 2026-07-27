# -*- mode: python ; coding: utf-8 -*-
"""Empaqueta escritorio.py como ejecutable único con PyInstaller.

Un solo .spec para Windows y macOS, con la diferencia real entre los dos
sistemas resuelta con `sys.platform`, no con dos ficheros separados:

- Windows: el `.exe` de `EXE(...)` YA es "el programa" — un fichero suelto,
  doble clic y arranca. Es justo el ejecutable portable que se quiere.
- macOS: un binario Unix suelto no es lo que alguien espera poder abrir
  haciendo doble clic desde Finder ni lleva icono propio. Hace falta
  envolverlo en un `.app` (con `BUNDLE(...)`) — técnicamente es una carpeta,
  pero Finder la trata como un único icono, que es el mismo comportamiento
  que en Windows, solo que así es como macOS lo resuelve de forma nativa.

PyInstaller no compila cruzado: este .spec genera el .exe si se ejecuta EN
Windows, y el .app si se ejecuta EN macOS. Ver el workflow de GitHub
Actions (`.github/workflows/build-escritorio.yml`) para compilar los dos a
la vez, uno en cada sistema operativo.
"""
import sys

NOMBRE = "CV Adaptativo"
CARPETA_ICONOS = "empaquetado/iconos"
# Icono de prueba: pendiente del icono y el nombre definitivos (ver
# historial.md, 2026-07-24). Sustituir aquí cuando estén listos.
ICONO_WINDOWS = f"{CARPETA_ICONOS}/icono_prueba.ico"
ICONO_MACOS = f"{CARPETA_ICONOS}/icono_prueba.icns"

a = Analysis(
    ["escritorio.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("cv_adaptativo/web/templates", "cv_adaptativo/web/templates"),
        ("cv_adaptativo/web/static", "cv_adaptativo/web/static"),
    ],
    hiddenimports=[
        # pywebview elige el backend según el sistema operativo en tiempo
        # de ejecución (no con imports estáticos), y eso es precisamente lo
        # que el análisis estático de PyInstaller puede no detectar solo.
        "webview.platforms.winforms" if sys.platform == "win32" else "webview.platforms.cocoa",
    ],
    hookspath=[],
    # pywebview soporta varios backends (winforms, Qt...) y elige el que
    # toque en tiempo de ejecución, pero `hiddenimports` de arriba ya fuerza
    # cuál usar en cada sistema. Si en el entorno de compilación hay más de
    # unas bindings de Qt instaladas a la vez (p. ej. PyQt5 y PySide6 en un
    # conda "base" con muchos paquetes), PyInstaller aborta el build porque
    # no puede empaquetar las dos a la vez — y aquí no hace falta ninguna.
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
    name=NOMBRE if sys.platform != "darwin" else "escritorio",
    console=False,  # ventana, no consola detrás
    onefile=True,
    icon=ICONO_WINDOWS if sys.platform == "win32" else ICONO_MACOS,
)

if sys.platform == "darwin":
    app = BUNDLE(
        exe,
        name=f"{NOMBRE}.app",
        icon=ICONO_MACOS,
        bundle_identifier="com.danielvegarosado.cvadaptativo",
    )
