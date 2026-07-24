"""Genera un icono de prueba (verde de marca + "CV") en .ico y .icns.

Es un placeholder a propósito: Daniel todavía tiene que decidir el icono y
el nombre definitivos de la app de escritorio. Cuando los tenga, este script
se sustituye por el diseño real (o se borra si el icono final se hace con
una herramienta de diseño en vez de código) — lo importante es que hasta
entonces el .spec de PyInstaller tenga algo a lo que apuntar.

Se ejecuta con: python empaquetado/iconos/generar_icono_prueba.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

VERDE = "#1f5238"
BLANCO = "#ffffff"
TAM = 512
CARPETA = Path(__file__).parent


def generar() -> None:
    img = Image.new("RGBA", (TAM, TAM), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([0, 0, TAM - 1, TAM - 1], radius=90, fill=VERDE)

    fuente = ImageFont.load_default(size=220)
    texto = "CV"
    caja = draw.textbbox((0, 0), texto, font=fuente)
    ancho, alto = caja[2] - caja[0], caja[3] - caja[1]
    draw.text(((TAM - ancho) / 2 - caja[0], (TAM - alto) / 2 - caja[1]), texto, font=fuente, fill=BLANCO)

    img.save(CARPETA / "icono_prueba.png")
    img.save(CARPETA / "icono_prueba.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    img.save(CARPETA / "icono_prueba.icns")


if __name__ == "__main__":
    generar()
