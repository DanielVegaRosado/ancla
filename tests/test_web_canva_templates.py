"""HTTP tests for the Templates screen: the gallery listing and the
in-app PDF preview — never a redirect out to canva.com."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from ancla.web import create_app
from ancla.web import settings as modulo_ajustes


def _pdf_minimo() -> bytes:
    """A byte-for-byte valid, blank one-page PDF — real enough for
    pypdfium2 to render, unlike a `%PDF` prefix on arbitrary bytes."""
    objetos = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 400]>>",
    ]
    partes = [b"%PDF-1.4\n"]
    offsets = [0]
    for n, cuerpo in enumerate(objetos, start=1):
        offsets.append(sum(len(p) for p in partes))
        partes.append(f"{n} 0 obj".encode() + cuerpo + b"endobj\n")
    inicio_xref = sum(len(p) for p in partes)
    xref = [b"xref\n", f"0 {len(objetos) + 1}\n".encode(), b"0000000000 65535 f \n"]
    for offset in offsets[1:]:
        xref.append(f"{offset:010d} 00000 n \n".encode())
    partes += xref
    partes.append(f"trailer<</Size {len(objetos) + 1}/Root 1 0 R>>\nstartxref\n{inicio_xref}\n%%EOF".encode())
    return b"".join(partes)


@pytest.fixture
def plantillas_canva(tmp_path: Path) -> Path:
    raiz = tmp_path / "canva-templates"
    raiz.mkdir()
    (raiz / "calida.pdf").write_bytes(b"%PDF-1.4 contenido falso")
    (raiz / "calida.yaml").write_text(
        "nombre:\n  es: Minimalista Cálida\n  en: Warm Minimalist\n", encoding="utf-8"
    )
    return raiz


@pytest.fixture
def plantillas_canva_reales(tmp_path: Path) -> Path:
    raiz = tmp_path / "canva-templates"
    raiz.mkdir()
    (raiz / "calida.pdf").write_bytes(_pdf_minimo())
    (raiz / "calida.yaml").write_text(
        "nombre:\n  es: Minimalista Cálida\n  en: Warm Minimalist\n", encoding="utf-8"
    )
    return raiz


def _cliente(tmp_path: Path, canva_templates_root: Path, idioma: str = "es"):
    ruta_ajustes = tmp_path / "ajustes.json"
    modulo_ajustes.save_settings(modulo_ajustes.Settings(idioma=idioma), ruta_ajustes)
    app = create_app(
        raiz_perfil=tmp_path / "perfil",
        settings_path=ruta_ajustes,
        canva_templates_root=canva_templates_root,
    )
    app.config["TESTING"] = True
    return app.test_client()


def test_la_galeria_vacia_no_rompe_la_pantalla(tmp_path: Path):
    cliente = _cliente(tmp_path, tmp_path / "no-existe")
    respuesta = cliente.get("/plantillas")
    assert respuesta.status_code == 200


def test_la_galeria_enlaza_a_la_vista_de_cada_plantilla(tmp_path: Path, plantillas_canva: Path):
    cliente = _cliente(tmp_path, plantillas_canva)
    respuesta = cliente.get("/plantillas")
    html = respuesta.data.decode("utf-8")
    assert "Minimalista Cálida" in html
    assert 'href="/plantillas/calida"' in html


def test_el_nombre_sigue_el_idioma_de_la_interfaz(tmp_path: Path, plantillas_canva: Path):
    cliente = _cliente(tmp_path, plantillas_canva, idioma="en")

    lista = cliente.get("/plantillas").data.decode("utf-8")
    assert "Warm Minimalist" in lista
    assert "Minimalista Cálida" not in lista

    detalle = cliente.get("/plantillas/calida").data.decode("utf-8")
    assert "Warm Minimalist" in detalle


def test_la_vista_de_una_plantilla_muestra_su_imagen_sin_visor_de_pdf(tmp_path: Path, plantillas_canva: Path):
    cliente = _cliente(tmp_path, plantillas_canva)
    respuesta = cliente.get("/plantillas/calida")
    assert respuesta.status_code == 200
    html = respuesta.data.decode("utf-8")
    assert 'src="/plantillas/calida/vista-detalle.png"' in html
    assert "<embed" not in html
    # The original PDF stays reachable, just not embedded with viewer chrome.
    assert 'href="/plantillas/calida/archivo"' in html
    # Must not redirect to Canva anywhere on this screen.
    assert "canva.com" not in html


def test_el_archivo_de_una_plantilla_sirve_el_pdf_real(tmp_path: Path, plantillas_canva: Path):
    cliente = _cliente(tmp_path, plantillas_canva)
    respuesta = cliente.get("/plantillas/calida/archivo")
    assert respuesta.status_code == 200
    assert respuesta.mimetype == "application/pdf"
    assert respuesta.data == b"%PDF-1.4 contenido falso"


def test_una_plantilla_desconocida_da_404(tmp_path: Path, plantillas_canva: Path):
    cliente = _cliente(tmp_path, plantillas_canva)
    assert cliente.get("/plantillas/no-existe").status_code == 404
    assert cliente.get("/plantillas/no-existe/archivo").status_code == 404
    assert cliente.get("/plantillas/no-existe/vista-previa.png").status_code == 404


def test_la_galeria_muestra_una_imagen_de_vista_previa_no_el_pdf_embebido(
    tmp_path: Path, plantillas_canva: Path
):
    cliente = _cliente(tmp_path, plantillas_canva)
    html = cliente.get("/plantillas").data.decode("utf-8")
    assert 'src="/plantillas/calida/vista-previa.png"' in html
    assert "<embed" not in html


def test_la_vista_previa_renderiza_la_primera_pagina_del_pdf_como_png(
    tmp_path: Path, plantillas_canva_reales: Path
):
    cliente = _cliente(tmp_path, plantillas_canva_reales)
    respuesta = cliente.get("/plantillas/calida/vista-previa.png")
    assert respuesta.status_code == 200
    assert respuesta.mimetype == "image/png"
    assert respuesta.data[:8] == b"\x89PNG\r\n\x1a\n"


def test_la_vista_de_detalle_renderiza_a_mayor_resolucion_en_su_propia_cache(
    tmp_path: Path, plantillas_canva_reales: Path
):
    cliente = _cliente(tmp_path, plantillas_canva_reales)
    respuesta = cliente.get("/plantillas/calida/vista-detalle.png")
    assert respuesta.status_code == 200
    assert respuesta.mimetype == "image/png"
    assert respuesta.data[:8] == b"\x89PNG\r\n\x1a\n"
    assert (plantillas_canva_reales / "calida-detalle.png").exists()
    # Does not share a cache file with the gallery thumbnail.
    assert not (plantillas_canva_reales / "calida.png").exists()


def test_la_vista_previa_se_cachea_junto_al_pdf(tmp_path: Path, plantillas_canva_reales: Path):
    cliente = _cliente(tmp_path, plantillas_canva_reales)
    cliente.get("/plantillas/calida/vista-previa.png")
    cacheada = plantillas_canva_reales / "calida.png"
    assert cacheada.exists()

    mtime_tras_primera = cacheada.stat().st_mtime
    cliente.get("/plantillas/calida/vista-previa.png")
    assert cacheada.stat().st_mtime == mtime_tras_primera


def test_la_vista_previa_se_regenera_si_el_pdf_cambia(tmp_path: Path, plantillas_canva_reales: Path):
    cliente = _cliente(tmp_path, plantillas_canva_reales)
    cliente.get("/plantillas/calida/vista-previa.png")
    cacheada = plantillas_canva_reales / "calida.png"
    mtime_tras_primera = cacheada.stat().st_mtime

    pdf_path = plantillas_canva_reales / "calida.pdf"
    nuevo_mtime = mtime_tras_primera + 5
    pdf_path.write_bytes(pdf_path.read_bytes())
    os.utime(pdf_path, (nuevo_mtime, nuevo_mtime))

    cliente.get("/plantillas/calida/vista-previa.png")
    assert cacheada.stat().st_mtime > mtime_tras_primera


def test_la_vista_previa_no_escribe_junto_al_pdf_dentro_de_un_flatpak(
    tmp_path: Path, plantillas_canva_reales: Path, monkeypatch
):
    """Inside a Flatpak, canva-templates/ ships installed read-only — writing
    there blows up the request with a 500. FLATPAK_ID, which Flatpak always
    sets inside the sandbox, redirects the cache to a writable folder instead
    of attempting it."""
    plantillas_canva_reales.chmod(0o555)
    monkeypatch.setenv("FLATPAK_ID", "com.danielvegarosado.Ancla")
    try:
        cliente = _cliente(tmp_path, plantillas_canva_reales)
        respuesta = cliente.get("/plantillas/calida/vista-previa.png")
        assert respuesta.status_code == 200
        assert respuesta.mimetype == "image/png"
        assert not (plantillas_canva_reales / "calida.png").exists()
        cacheada = list((tmp_path / "cache" / "plantillas").glob("calida.png"))
        assert len(cacheada) == 1
    finally:
        plantillas_canva_reales.chmod(0o755)


def test_la_vista_previa_no_escribe_junto_al_pdf_en_la_app_empaquetada(
    tmp_path: Path, plantillas_canva_reales: Path, monkeypatch
):
    """On Windows the templates sit next to the .exe, which may be under
    Program Files and not writable."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    cliente = _cliente(tmp_path, plantillas_canva_reales)
    respuesta = cliente.get("/plantillas/calida/vista-previa.png")
    assert respuesta.status_code == 200
    assert not (plantillas_canva_reales / "calida.png").exists()
    assert (tmp_path / "cache" / "plantillas" / "calida.png").exists()
