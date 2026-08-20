"""Tests for `ancla/design/gallery.py`: discovering Canva template PDF
previews from their YAML sidecars — same discovery rules as
`ancla/export/templates.py`'s `.docx` templates, tested separately because
it's a different, unrelated concept (a preview, not something rendered)."""
from __future__ import annotations

from pathlib import Path

from ancla.design import gallery


def test_lista_plantillas_lee_el_nombre_del_yaml(tmp_path: Path):
    (tmp_path / "calida.pdf").write_bytes(b"contenido falso")
    (tmp_path / "calida.yaml").write_text(
        "nombre:\n  es: Minimalista Cálida\n  en: Warm Minimalist\n", encoding="utf-8"
    )

    plantillas = gallery.list_templates(tmp_path)

    assert len(plantillas) == 1
    assert plantillas[0].id == "calida"
    assert plantillas[0].name.es == "Minimalista Cálida"
    assert plantillas[0].name.en == "Warm Minimalist"
    assert plantillas[0].path == tmp_path / "calida.pdf"


def test_un_nombre_de_texto_plano_se_aplica_a_los_dos_idiomas(tmp_path: Path):
    (tmp_path / "clasica.pdf").write_bytes(b"contenido falso")
    (tmp_path / "clasica.yaml").write_text("nombre: Corporativa Clásica\n", encoding="utf-8")

    plantilla = gallery.find_template(tmp_path, "clasica")

    assert plantilla is not None
    assert plantilla.name.es == "Corporativa Clásica"
    assert plantilla.name.en == "Corporativa Clásica"


def test_un_pdf_sin_yaml_hermano_se_ignora(tmp_path: Path):
    (tmp_path / "huerfano.pdf").write_bytes(b"contenido falso")
    assert gallery.list_templates(tmp_path) == []


def test_un_yaml_con_formato_invalido_se_ignora(tmp_path: Path):
    (tmp_path / "rota.pdf").write_bytes(b"contenido falso")
    (tmp_path / "rota.yaml").write_text("esto: [no cierra", encoding="utf-8")
    assert gallery.list_templates(tmp_path) == []


def test_carpeta_inexistente_no_da_error(tmp_path: Path):
    assert gallery.list_templates(tmp_path / "no-existe") == []


def test_find_template_devuelve_none_si_no_existe(tmp_path: Path):
    assert gallery.find_template(tmp_path, "no-existe") is None


def test_find_template_encuentra_por_id(tmp_path: Path):
    (tmp_path / "clasica.pdf").write_bytes(b"contenido falso")
    (tmp_path / "clasica.yaml").write_text("nombre: Corporativa Clásica\n", encoding="utf-8")

    plantilla = gallery.find_template(tmp_path, "clasica")

    assert plantilla is not None
    assert plantilla.id == "clasica"
