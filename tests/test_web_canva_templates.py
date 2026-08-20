"""HTTP tests for the Templates screen: the gallery listing and the
in-app PDF preview — never a redirect out to canva.com."""
from __future__ import annotations

from pathlib import Path

import pytest

from ancla.web import create_app
from ancla.web import settings as modulo_ajustes


@pytest.fixture
def plantillas_canva(tmp_path: Path) -> Path:
    raiz = tmp_path / "canva-templates"
    raiz.mkdir()
    (raiz / "calida.pdf").write_bytes(b"%PDF-1.4 contenido falso")
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


def test_la_vista_de_una_plantilla_embebe_su_pdf(tmp_path: Path, plantillas_canva: Path):
    cliente = _cliente(tmp_path, plantillas_canva)
    respuesta = cliente.get("/plantillas/calida")
    assert respuesta.status_code == 200
    html = respuesta.data.decode("utf-8")
    assert 'src="/plantillas/calida/archivo"' in html
    assert 'type="application/pdf"' in html
    # No debe redirigir a Canva en ningún sitio de esta pantalla.
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
