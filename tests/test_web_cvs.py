"""HTTP tests for the My CVs screen, in particular the per-status summary
shown above the archive (the figures panel)."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from ancla.archive import repository as archivo
from ancla.profile.model import (
    CVStatus,
    SavedCV,
    SelectedAboutMe,
    SelectedExperience,
    Proposal,
)
from ancla.web import create_app
from ancla.web import settings as modulo_ajustes


@pytest.fixture
def cliente_web(tmp_path: Path):
    app = create_app(raiz_perfil=tmp_path / "perfil", settings_path=tmp_path / "ajustes.json")
    app.config["TESTING"] = True
    return app.test_client()


def _cv(id: str, estado: CVStatus = CVStatus.DRAFT) -> SavedCV:
    return SavedCV(
        id=id,
        date=date(2026, 7, 24),
        company="ACME",
        position="Data Engineer",
        posting="Buscamos alguien con Python y SQL.",
        status=estado,
        proposal=Proposal(
            language="es",
            about_me=SelectedAboutMe(group_a=[], group_b=[], text="", reason=""),
            skills=["python"],
            skills_reason="Requisito explícito.",
            experiences=[SelectedExperience(id="ml-telco", reason="Encaja.")],
        ),
    )


def test_el_resumen_por_estado_cuenta_cada_cv_una_vez(cliente_web, tmp_path: Path):
    root = tmp_path / "perfil"
    archivo.save(root, _cv("cv-1", CVStatus.SENT))
    archivo.save(root, _cv("cv-2", CVStatus.SENT))
    archivo.save(root, _cv("cv-3", CVStatus.INTERVIEW))

    respuesta = cliente_web.get("/cvs")

    assert respuesta.status_code == 200
    html = respuesta.data.decode("utf-8")
    assert '<span class="bento-cifra">2</span>' in html  # Enviado
    assert '<span class="bento-cifra">1</span>' in html  # Entrevista
    assert '<span class="bento-cifra">0</span>' in html  # el resto, en 0


def test_un_archivo_vacio_no_muestra_el_resumen(cliente_web):
    respuesta = cliente_web.get("/cvs")
    assert b'class="bento"' not in respuesta.data


def _adjuntar(cliente_web, id_: str, contenido: bytes, nombre: str):
    from io import BytesIO

    return cliente_web.post(
        f"/cvs/{id_}/adjuntar",
        data={"adjunto": (BytesIO(contenido), nombre)},
        content_type="multipart/form-data",
        follow_redirects=True,
    )


def test_guardar_un_cv_final_lo_deja_ver_y_descargar(cliente_web, tmp_path: Path):
    archivo.save(tmp_path / "perfil", _cv("cv-1"))

    respuesta = _adjuntar(cliente_web, "cv-1", b"contenido del cv", "CV_final.docx")
    assert respuesta.status_code == 200
    html = respuesta.data.decode("utf-8")
    assert "CV_final.docx" in html

    nombre_en_disco = archivo.list_all(tmp_path / "perfil")[0].attachments[0]
    descarga = cliente_web.get(f"/cvs/cv-1/adjunto/{nombre_en_disco}")
    assert descarga.status_code == 200
    assert descarga.data == b"contenido del cv"


def test_guardar_varios_cv_finales_no_sobrescribe_los_anteriores(cliente_web, tmp_path: Path):
    archivo.save(tmp_path / "perfil", _cv("cv-1"))

    _adjuntar(cliente_web, "cv-1", b"version docx", "corporativa.docx")
    respuesta = _adjuntar(cliente_web, "cv-1", b"version pdf", "minimalista.pdf")

    html = respuesta.data.decode("utf-8")
    assert "corporativa.docx" in html
    assert "minimalista.pdf" in html
    assert len(archivo.list_all(tmp_path / "perfil")[0].attachments) == 2


def test_borrar_un_adjunto_no_borra_los_demas(cliente_web, tmp_path: Path):
    archivo.save(tmp_path / "perfil", _cv("cv-1"))
    _adjuntar(cliente_web, "cv-1", b"version docx", "corporativa.docx")
    _adjuntar(cliente_web, "cv-1", b"version pdf", "minimalista.pdf")
    a_borrar = archivo.list_all(tmp_path / "perfil")[0].attachments[0]

    respuesta = cliente_web.post(f"/cvs/cv-1/adjunto/{a_borrar}/borrar", follow_redirects=True)

    assert respuesta.status_code == 200
    adjuntos = archivo.list_all(tmp_path / "perfil")[0].attachments
    assert len(adjuntos) == 1
    assert a_borrar not in adjuntos


def test_el_archivo_de_un_cv_sin_adjunto_da_404(cliente_web, tmp_path: Path):
    archivo.save(tmp_path / "perfil", _cv("cv-1"))
    assert cliente_web.get("/cvs/cv-1/adjunto/cv.pdf").status_code == 404


def test_el_archivo_de_un_cv_desconocido_da_404(cliente_web):
    assert cliente_web.get("/cvs/no-existe/adjunto/cv.pdf").status_code == 404


def test_las_etiquetas_de_estado_siguen_el_idioma_de_la_interfaz(tmp_path: Path):
    """`etiquetas_estado()` builds its dict inside the request, not once at
    import time — a module-level dict would freeze whichever language
    happened to be active first (see `ancla/web/presentation.py`)."""
    root = tmp_path / "perfil"
    archivo.save(root, _cv("cv-1", CVStatus.SENT))
    ruta_ajustes = tmp_path / "ajustes.json"
    modulo_ajustes.save_settings(modulo_ajustes.Settings(idioma="en"), ruta_ajustes)
    app = create_app(raiz_perfil=root, settings_path=ruta_ajustes)
    app.config["TESTING"] = True

    html = app.test_client().get("/cvs").data.decode("utf-8")

    assert "Sent" in html
    assert "Enviado" not in html
