"""Tests del archivo de CVs, del cliente de Groq y del soporte."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from cv_adaptativo.archivo import repositorio
from cv_adaptativo.ia.cliente import ErrorIA
from cv_adaptativo.ia.groq import ClienteGroq
from cv_adaptativo.perfil.errores import ErrorPerfil
from cv_adaptativo.perfil.modelo import (
    CVGuardado,
    EstadoCV,
    ExperienciaSeleccionada,
    Propuesta,
    SeleccionSobreMi,
)
from cv_adaptativo.soporte import mensajes


def _cv(id: str = "2026-07-24_acme_data-engineer", **cambios) -> CVGuardado:
    base = dict(
        id=id,
        fecha=date(2026, 7, 24),
        empresa="ACME",
        puesto="Data Engineer",
        vacante="Buscamos alguien con Python y SQL.",
        propuesta=Propuesta(
            idioma="es",
            sobre_mi=SeleccionSobreMi(
                grupo_a=["machine learning", "LLMs", "datos"],
                grupo_b=["Python", "SQL", "Java"],
                texto="Estudiante con conocimientos en machine learning...",
                motivo="La vacante prioriza datos.",
            ),
            skills=["python", "sql"],
            motivo_skills="Son los dos requisitos explícitos.",
            experiencias=[ExperienciaSeleccionada(id="ml-telco", motivo="Encaja.")],
            huecos=["Kubernetes"],
        ),
    )
    return CVGuardado(**{**base, **cambios})


# --------------------------------------------------------------------------
# Archivo
# --------------------------------------------------------------------------


def test_guardar_y_leer_conserva_la_propuesta(tmp_path: Path):
    repositorio.guardar(tmp_path, _cv())
    recuperado = repositorio.listar(tmp_path)[0]

    assert recuperado.empresa == "ACME"
    assert recuperado.fecha == date(2026, 7, 24)
    assert recuperado.propuesta.skills == ["python", "sql"]
    assert recuperado.propuesta.experiencias[0].motivo == "Encaja."
    assert recuperado.propuesta.huecos == ["Kubernetes"]


def test_el_archivo_guarda_ids_no_textos_del_perfil(tmp_path: Path):
    """La regla de fondo: corregir el perfil corrige los CV ya guardados."""
    repositorio.guardar(tmp_path, _cv())
    escrito = (tmp_path / "cvs" / "2026-07-24_acme_data-engineer.yaml").read_text("utf-8")

    assert "python" in escrito
    assert "ml-telco" in escrito
    # El título de la experiencia vive en el perfil, no aquí.
    assert "ML Developer" not in escrito


def test_listar_devuelve_del_mas_reciente_al_mas_antiguo(tmp_path: Path):
    repositorio.guardar(tmp_path, _cv(id="2026-07-01_uno", fecha=date(2026, 7, 1)))
    repositorio.guardar(tmp_path, _cv(id="2026-07-30_dos", fecha=date(2026, 7, 30)))

    assert [cv.id for cv in repositorio.listar(tmp_path)] == [
        "2026-07-30_dos",
        "2026-07-01_uno",
    ]


def test_listar_sin_carpeta_no_es_un_error(tmp_path: Path):
    assert repositorio.listar(tmp_path) == []


def test_un_cv_roto_no_tumba_la_lista(tmp_path: Path):
    """Se pierde una fila de una lista, no un CV entero: se omite y se sigue."""
    repositorio.guardar(tmp_path, _cv())
    (tmp_path / "cvs" / "roto.yaml").write_text("esto: [no cierra", encoding="utf-8")

    assert len(repositorio.listar(tmp_path)) == 1


def test_buscar_por_empresa_ignora_mayusculas_y_acentos(tmp_path: Path):
    repositorio.guardar(tmp_path, _cv(empresa="Telefónica"))

    assert len(repositorio.buscar_por_empresa(tmp_path, "TELEFONICA")) == 1
    assert repositorio.buscar_por_empresa(tmp_path, "otra") == []
    assert repositorio.buscar_por_empresa(tmp_path, "") == []


def test_cambiar_estado_no_toca_el_resto(tmp_path: Path):
    repositorio.guardar(tmp_path, _cv())
    repositorio.cambiar_estado(tmp_path, _cv().id, EstadoCV.ENTREVISTA)

    recuperado = repositorio.listar(tmp_path)[0]
    assert recuperado.estado is EstadoCV.ENTREVISTA
    assert recuperado.propuesta.skills == ["python", "sql"]


def test_adjuntar_copia_el_archivo_sea_del_formato_que_sea(tmp_path: Path):
    repositorio.guardar(tmp_path, _cv())
    origen = tmp_path / "CV_final.docx"
    origen.write_bytes(b"contenido")

    destino = repositorio.adjuntar(tmp_path, _cv().id, origen)

    assert destino.exists() and destino.suffix == ".docx"
    assert origen.exists(), "el original del usuario no se mueve ni se borra"
    assert repositorio.listar(tmp_path)[0].adjunto == destino.name


def test_un_id_con_travesia_de_rutas_no_escribe_fuera_del_perfil(tmp_path: Path):
    with pytest.raises(ErrorPerfil):
        repositorio.guardar(tmp_path, _cv(id="../../fuera"))


def test_nuevo_id_no_pisa_uno_existente(tmp_path: Path):
    primero = repositorio.nuevo_id(tmp_path, date(2026, 7, 24), "ACME", "Data Engineer")
    repositorio.guardar(tmp_path, _cv(id=primero))
    segundo = repositorio.nuevo_id(tmp_path, date(2026, 7, 24), "ACME", "Data Engineer")

    assert primero == "2026-07-24_acme_data-engineer"
    assert segundo != primero


def test_nuevo_id_aguanta_una_empresa_sin_nombre(tmp_path: Path):
    assert repositorio.nuevo_id(tmp_path, date(2026, 7, 24), "", "") == (
        "2026-07-24_sin-empresa"
    )


# --------------------------------------------------------------------------
# Cliente de Groq
# --------------------------------------------------------------------------


def test_sin_clave_no_esta_disponible_y_lo_dice_en_castellano():
    cliente = ClienteGroq(clave="")
    assert not cliente.disponible()

    with pytest.raises(ErrorIA) as fallo:
        cliente.completar("sistema", "usuario")
    assert "Ajustes" in str(fallo.value)


def test_los_fallos_del_proveedor_se_traducen_a_algo_accionable():
    explicar = ClienteGroq._explicar

    assert "clave" in explicar(Exception("Invalid API Key provided")).lower()
    assert "cuota" in explicar(Exception("rate limit exceeded")).lower()
    assert "conexi" in explicar(Exception("failed to connect")).lower()
    # Lo que no se reconoce no se disfraza: se enseña tal cual.
    assert "vaya cosa rara" in explicar(Exception("vaya cosa rara"))


# --------------------------------------------------------------------------
# Soporte
# --------------------------------------------------------------------------


def test_el_mensaje_se_guarda_siempre_en_local(tmp_path: Path):
    ruta = mensajes.guardar_mensaje(tmp_path, "No arranca", "Se queda en blanco.")

    assert ruta.exists()
    contenido = ruta.read_text("utf-8")
    assert "No arranca" in contenido and "Se queda en blanco." in contenido


def test_el_diagnostico_no_incluye_nada_del_perfil():
    """Un CV no puede acabar en una incidencia pública por reportar un botón roto."""
    diagnostico = mensajes.recoger(proveedor="groq", modelo="gpt-oss-120b")
    campos = set(vars(diagnostico))

    assert campos == {"version", "sistema", "python", "proveedor", "modelo", "error"}
    assert "clave" not in diagnostico.como_texto().lower()


def test_las_dos_salidas_llevan_el_mensaje_y_ningun_secreto():
    incidencia = mensajes.url_incidencia("Fallo", "El botón no responde")
    correo = mensajes.url_correo("Fallo", "El botón no responde")

    assert incidencia.startswith(mensajes.REPOSITORIO + "/issues/new?")
    assert correo.startswith("mailto:")
    for url in (incidencia, correo):
        assert "bot%C3%B3n" in url or "bot%C3%B3n".lower() in url.lower()
        assert "api_key" not in url.lower() and "password" not in url.lower()


def test_un_mensaje_larguisimo_se_recorta_avisando():
    cuerpo = mensajes.url_incidencia("Fallo", "a" * 20000)

    assert len(cuerpo) < 20000
    assert "recortado" in cuerpo or "recort" in cuerpo
