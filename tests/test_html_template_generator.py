"""Tests for `herramientas/nueva-plantilla-html.py`.

The script lives in `herramientas/` (internal tooling, not part of the
public `app/` package) but its output is real content for
`html-templates/`, so its contract with `ancla.export.html_templates` is
tested here like any other producer of that folder's files. Loaded via
`importlib` because the file name has hyphens and cannot be `import`ed
directly.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from PIL import Image

from ancla.export import html_templates
from ancla.export.sidecar import read_yaml_sidecar

HERRAMIENTAS = Path(__file__).resolve().parents[2] / "herramientas"


def _cargar_modulo():
    ruta = HERRAMIENTAS / "nueva-plantilla-html.py"
    spec = importlib.util.spec_from_file_location("nueva_plantilla_html", ruta)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modulo
    spec.loader.exec_module(modulo)
    return modulo


gen = _cargar_modulo()


# --------------------------------------------------------------------------
# Color helpers
# --------------------------------------------------------------------------


def test_color_hex_formatea_con_ceros_a_la_izquierda():
    assert gen._color_hex((0, 8, 255)) == "#0008ff"


def test_es_neutro_detecta_blanco_y_gris_de_texto():
    assert gen._es_neutro((250, 250, 248))  # near-white
    assert gen._es_neutro((30, 32, 28))  # near-black, low saturation
    assert not gen._es_neutro((179, 128, 90))  # terracotta: saturated


def test_mezclar_con_blanco_aclara_hacia_el_blanco():
    aclarado = gen._mezclar_con_blanco("#000000", 0.5)
    assert aclarado == "#808080"
    assert gen._mezclar_con_blanco("#123456", 0.0) == "#123456"


def test_es_mezcla_de_bordes_descarta_el_antialiasing_pero_no_un_color_real():
    panel = (12, 35, 63)  # navy-ish
    medio_camino = tuple(round((p + b) / 2) for p, b in zip(panel, (255, 255, 255)))
    assert gen._es_mezcla_de_bordes(medio_camino, panel)
    # A saturated accent far from the panel-to-white line is kept.
    assert not gen._es_mezcla_de_bordes((179, 128, 90), panel)


# --------------------------------------------------------------------------
# Geometry, measured on synthetic images (no PDF needed: these functions
# only ever look at pixels, see the module docstring for why).
# --------------------------------------------------------------------------


def _imagen_dos_columnas(
    ancho: int = 800,
    alto: int = 1100,
    fraccion_lateral: float = 0.35,
    color_panel: tuple[int, int, int] = (12, 35, 63),
    color_acento: tuple[int, int, int] | None = None,
) -> Image.Image:
    imagen = Image.new("RGB", (ancho, alto), (255, 255, 255))
    borde = int(ancho * fraccion_lateral)
    for y in range(alto):
        for x in range(borde):
            imagen.putpixel((x, y), color_panel)
    if color_acento is not None:
        # A block of accent color inside the sidebar, below where the
        # generator skips looking for the profile photo (see
        # `_detectar_acento`'s `y_inicial`).
        y0, y1 = int(alto * 0.4), int(alto * 0.45)
        for y in range(y0, y1):
            for x in range(10, borde - 10):
                imagen.putpixel((x, y), color_acento)
    return imagen


def test_detectar_lateral_encuentra_el_ancho_y_el_color_del_panel():
    imagen = _imagen_dos_columnas(fraccion_lateral=0.35)
    ancho_lateral_pt, color_panel = gen._detectar_lateral(imagen, dpi=gen.DPI_MEDICION)

    ancho_pagina_pt = imagen.size[0] / (gen.DPI_MEDICION / gen.PT_POR_PULGADA)
    assert ancho_lateral_pt == pytest.approx(ancho_pagina_pt * 0.35, abs=3)
    # `_color_dominante` buckets colors to smooth out antialiasing, so the
    # result lands within one bucket (8 per channel) of the true color
    # rather than matching it exactly.
    medido = tuple(int(color_panel[i : i + 2], 16) for i in (1, 3, 5))
    assert gen._distancia(medido, (12, 35, 63)) < 12


def test_detectar_lateral_falla_sin_panel_reconocible():
    imagen = Image.new("RGB", (800, 1100), (255, 255, 255))
    with pytest.raises(gen.DisenoNoReconocido):
        gen._detectar_lateral(imagen, dpi=gen.DPI_MEDICION)


def test_detectar_acento_encuentra_un_color_saturado_que_no_es_el_panel():
    color_panel_esperado = (12, 35, 63)
    imagen = _imagen_dos_columnas(color_panel=color_panel_esperado, color_acento=(179, 128, 90))
    color_acento, panel_de_color_oscuro = gen._detectar_acento(
        imagen, gen._color_hex(color_panel_esperado), ancho_lateral_pt=200, dpi=gen.DPI_MEDICION
    )
    assert color_acento == "#b0801e" or gen._distancia(
        tuple(int(color_acento[i : i + 2], 16) for i in (1, 3, 5)), (179, 128, 90)
    ) < 40
    assert panel_de_color_oscuro is True


def test_detectar_acento_sin_color_propio_reutiliza_el_panel():
    """Corporativa Clásica reuses its navy background as the accent too: if
    there's no distinct saturated color, the accent is the panel itself."""
    color_panel = (12, 35, 63)
    imagen = _imagen_dos_columnas(color_panel=color_panel, color_acento=None)
    color_acento, _ = gen._detectar_acento(
        imagen, gen._color_hex(color_panel), ancho_lateral_pt=200, dpi=gen.DPI_MEDICION
    )
    assert color_acento == gen._color_hex(color_panel)


# --------------------------------------------------------------------------
# Full generation: written files must be discoverable by
# `ancla.export.html_templates`, the module every real template goes
# through.
# --------------------------------------------------------------------------


@pytest.fixture
def geometria() -> "gen.Geometria":
    return gen.Geometria(
        ancho_pagina_pt=595.32,
        alto_pagina_pt=841.92,
        ancho_lateral_pt=205.0,
        color_panel="#f6f6f6",
        color_acento="#b3805a",
        panel_de_color_oscuro=False,
    )


@pytest.mark.parametrize("estilo", sorted(gen.ESTILOS))
def test_plantilla_generada_es_descubierta_por_html_templates(tmp_path: Path, geometria, estilo: str):
    contexto = gen.construir_contexto(geometria, estilo)
    html, css = gen.renderizar_archivos(
        contexto,
        id_plantilla="prueba",
        nombre_es="Prueba",
        nombre_en="Test",
        pdf_referencia="prueba.pdf",
    )
    gen.escribir_plantilla(
        tmp_path,
        id_plantilla="prueba",
        nombre_es="Prueba",
        nombre_en="Test",
        html=html,
        css=css,
        capacidad_min=3,
        capacidad_max=5,
    )

    plantilla = html_templates.find_template(tmp_path, "prueba")
    assert plantilla is not None
    assert plantilla.name["es"] == "Prueba"
    assert plantilla.name["en"] == "Test"
    assert plantilla.capacity_min == 3
    assert plantilla.capacity_max == 5
    assert plantilla.has_stylesheet()


@pytest.mark.parametrize("estilo", sorted(gen.ESTILOS))
def test_plantilla_generada_declara_lo_que_el_ajuste_necesita(tmp_path: Path, geometria, estilo: str):
    """Same contract `test_web_cv_preview.py` requires for the two real
    templates: without `--cv-alto-pagina` or `var(--cv-escala` the fitting
    script (`cv_fit.js`) has nothing to measure."""
    contexto = gen.construir_contexto(geometria, estilo)
    _, css = gen.renderizar_archivos(
        contexto, id_plantilla="prueba", nombre_es="Prueba", nombre_en="Test", pdf_referencia="prueba.pdf"
    )
    assert "--cv-alto-pagina:" in css
    assert "var(--cv-escala" in css


def test_yaml_generado_se_lee_con_el_sidecar_compartido(tmp_path: Path, geometria):
    contexto = gen.construir_contexto(geometria, "clasico")
    html, css = gen.renderizar_archivos(
        contexto, id_plantilla="prueba", nombre_es="Prueba", nombre_en="Test", pdf_referencia="prueba.pdf"
    )
    gen.escribir_plantilla(
        tmp_path,
        id_plantilla="prueba",
        nombre_es="Prueba",
        nombre_en="Test",
        html=html,
        css=css,
        capacidad_min=3,
        capacidad_max=5,
    )
    datos = read_yaml_sidecar(tmp_path / "prueba.html")
    assert datos == {
        "nombre": {"es": "Prueba", "en": "Test"},
        "capacidad_experiencias_min": 3,
        "capacidad_experiencias_max": 5,
    }


def test_los_dos_estilos_difieren_en_la_estructura_del_html(geometria):
    """The two combinations already validated by hand in the app (name on
    one or two lines, bullets or running paragraph) have to produce genuinely
    different HTML, not the same template under another name."""
    html_clasico, _ = gen.renderizar_archivos(
        gen.construir_contexto(geometria, "clasico"),
        id_plantilla="p",
        nombre_es="P",
        nombre_en="P",
        pdf_referencia="p.pdf",
    )
    html_calido, _ = gen.renderizar_archivos(
        gen.construir_contexto(geometria, "calido"),
        id_plantilla="p",
        nombre_es="P",
        nombre_en="P",
        pdf_referencia="p.pdf",
    )
    assert "cv-nombre-primero" in html_calido
    assert "cv-nombre-primero" not in html_clasico
    assert "cv-parrafo" in html_calido
    assert "cv-bullets" in html_clasico
    assert "cv-parrafo" not in html_clasico
