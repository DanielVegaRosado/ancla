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
