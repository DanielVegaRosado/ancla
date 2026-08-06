"""Tests HTTP de la pantalla Mis CVs, en particular el resumen por estado
que se enseña arriba del archivo (panel de cifras)."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from ancla.archivo import repositorio as archivo
from ancla.perfil.modelo import (
    CVGuardado,
    EstadoCV,
    ExperienciaSeleccionada,
    Propuesta,
    SeleccionSobreMi,
)
from ancla.web import crear_app


@pytest.fixture
def cliente_web(tmp_path: Path):
    app = crear_app(raiz_perfil=tmp_path / "perfil", ruta_ajustes=tmp_path / "ajustes.json")
    app.config["TESTING"] = True
    return app.test_client()


def _cv(id: str, estado: EstadoCV = EstadoCV.BORRADOR) -> CVGuardado:
    return CVGuardado(
        id=id,
        fecha=date(2026, 7, 24),
        empresa="ACME",
        puesto="Data Engineer",
        vacante="Buscamos alguien con Python y SQL.",
        estado=estado,
        propuesta=Propuesta(
            idioma="es",
            sobre_mi=SeleccionSobreMi(grupo_a=[], grupo_b=[], texto="", motivo=""),
            skills=["python"],
            motivo_skills="Requisito explícito.",
            experiencias=[ExperienciaSeleccionada(id="ml-telco", motivo="Encaja.")],
        ),
    )


def test_el_resumen_por_estado_cuenta_cada_cv_una_vez(cliente_web, tmp_path: Path):
    raiz = tmp_path / "perfil"
    archivo.guardar(raiz, _cv("cv-1", EstadoCV.ENVIADO))
    archivo.guardar(raiz, _cv("cv-2", EstadoCV.ENVIADO))
    archivo.guardar(raiz, _cv("cv-3", EstadoCV.ENTREVISTA))

    respuesta = cliente_web.get("/cvs")

    assert respuesta.status_code == 200
    html = respuesta.data.decode("utf-8")
    assert '<span class="bento-cifra">2</span>' in html  # Enviado
    assert '<span class="bento-cifra">1</span>' in html  # Entrevista
    assert '<span class="bento-cifra">0</span>' in html  # el resto, en 0


def test_un_archivo_vacio_no_muestra_el_resumen(cliente_web):
    respuesta = cliente_web.get("/cvs")
    assert b'class="bento"' not in respuesta.data
