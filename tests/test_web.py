"""Tests de la capa web que no dependen de los módulos que otros agentes
están implementando en paralelo (almacen, motor, archivo, vacante siguen
lanzando NotImplementedError hasta que se integren). Cubren lo que sí es
responsabilidad exclusiva del agente C: utilidades, ajustes, el borrador de
trabajo efímero, la fábrica de proveedores y la pantalla de Ajustes.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from cv_adaptativo.ia.cliente import ErrorIA
from cv_adaptativo.perfil.modelo import (
    ExperienciaSeleccionada,
    Propuesta,
    SeleccionSobreMi,
)
from cv_adaptativo.web import ajustes as modulo_ajustes
from cv_adaptativo.web import borrador as modulo_borrador
from cv_adaptativo.web import crear_app
from cv_adaptativo.web.proveedores import crear_cliente
from cv_adaptativo.web.util import (
    csv_a_lista,
    lineas_a_lista,
    lista_a_csv,
    lista_a_lineas,
    slugificar,
)


# --------------------------------------------------------------------------
# util.py
# --------------------------------------------------------------------------


def test_slugificar_quita_acentos_y_espacios():
    assert slugificar("Ingeniero de Datos (Backend)") == "ingeniero-de-datos-backend"


def test_slugificar_texto_vacio_da_un_valor_por_defecto():
    assert slugificar("   ") == "sin-titulo"


def test_lineas_a_lista_ignora_lineas_vacias():
    assert lineas_a_lista("Uno\n\n  Dos  \n\nTres") == ["Uno", "Dos", "Tres"]


def test_lista_a_lineas_es_el_inverso():
    assert lista_a_lineas(["Uno", "Dos"]) == "Uno\nDos"


def test_csv_a_lista_recorta_espacios():
    assert csv_a_lista("python,  sql , gcp") == ["python", "sql", "gcp"]


def test_lista_a_csv_es_el_inverso():
    assert lista_a_csv(["python", "sql"]) == "python, sql"


# --------------------------------------------------------------------------
# ajustes.py
# --------------------------------------------------------------------------


def test_cargar_ajustes_sin_fichero_da_valores_por_defecto(tmp_path: Path):
    ajustes = modulo_ajustes.cargar_ajustes(tmp_path / "ajustes.json")
    assert ajustes.proveedor == "groq"
    assert ajustes.clave_api == ""
    assert not ajustes.configurado()


def test_guardar_y_cargar_ajustes_hace_ida_y_vuelta(tmp_path: Path):
    ruta = tmp_path / "ajustes.json"
    originales = modulo_ajustes.Ajustes(proveedor="groq", clave_api="gsk_secreta")
    modulo_ajustes.guardar_ajustes(originales, ruta)

    recargados = modulo_ajustes.cargar_ajustes(ruta)
    assert recargados == originales
    assert recargados.configurado()


def test_ajustes_con_fichero_corrupto_no_rompe(tmp_path: Path):
    ruta = tmp_path / "ajustes.json"
    ruta.write_text("esto no es json", encoding="utf-8")
    ajustes = modulo_ajustes.cargar_ajustes(ruta)
    assert ajustes == modulo_ajustes.Ajustes()


# --------------------------------------------------------------------------
# borrador.py
# --------------------------------------------------------------------------


def _propuesta_de_prueba() -> Propuesta:
    return Propuesta(
        idioma="es",
        sobre_mi=SeleccionSobreMi(grupo_a=["a", "b", "c"], grupo_b=["d", "e", "f"], texto="Texto."),
        skills=["python", "sql"],
        experiencias=[ExperienciaSeleccionada(id="proyecto-x", motivo="Encaja.")],
        huecos=["Kubernetes"],
    )


def test_no_hay_borrador_si_no_se_ha_guardado_ninguno(tmp_path: Path):
    assert modulo_borrador.cargar_borrador(tmp_path) is None


def test_guardar_y_cargar_borrador_hace_ida_y_vuelta(tmp_path: Path):
    original = modulo_borrador.Borrador(
        vacante="Se busca ingeniero...",
        empresa="Acme",
        puesto="Backend Engineer",
        propuesta=_propuesta_de_prueba(),
    )
    modulo_borrador.guardar_borrador(tmp_path, original)

    recargado = modulo_borrador.cargar_borrador(tmp_path)
    assert recargado == original


def test_borrar_borrador_lo_deja_indisponible(tmp_path: Path):
    modulo_borrador.guardar_borrador(
        tmp_path,
        modulo_borrador.Borrador(vacante="x", empresa="", puesto="", propuesta=_propuesta_de_prueba()),
    )
    modulo_borrador.borrar_borrador(tmp_path)
    assert modulo_borrador.cargar_borrador(tmp_path) is None


def test_borrar_borrador_sin_fichero_no_falla(tmp_path: Path):
    modulo_borrador.borrar_borrador(tmp_path)  # no debe lanzar


# --------------------------------------------------------------------------
# proveedores.py
# --------------------------------------------------------------------------


def test_crear_cliente_con_proveedor_desconocido_lanza_error_ia():
    with pytest.raises(ErrorIA):
        crear_cliente("proveedor-inventado", "clave")


# --------------------------------------------------------------------------
# Pantalla de Ajustes (extremo a extremo, no depende de otros agentes)
# --------------------------------------------------------------------------


@pytest.fixture
def cliente_web(tmp_path: Path):
    app = crear_app(raiz_perfil=tmp_path / "perfil", ruta_ajustes=tmp_path / "ajustes.json")
    app.config["TESTING"] = True
    return app.test_client()


def test_ver_ajustes_sin_configurar(cliente_web):
    respuesta = cliente_web.get("/ajustes")
    assert respuesta.status_code == 200
    assert "Todavía no has configurado ninguna clave".encode("utf-8") in respuesta.data


def test_ajustes_enlaza_directo_a_conseguir_la_clave(cliente_web):
    """El enlace tiene que estar aquí, antes de que alguien se equivoque —
    no solo en el mensaje de error de después."""
    respuesta = cliente_web.get("/ajustes")
    assert b"console.groq.com/keys" in respuesta.data


def test_guardar_ajustes_los_persiste(cliente_web, tmp_path: Path):
    respuesta = cliente_web.post(
        "/ajustes", data={"proveedor": "groq", "clave_api": "gsk_123"}, follow_redirects=True
    )
    assert respuesta.status_code == 200
    guardados = modulo_ajustes.cargar_ajustes(tmp_path / "ajustes.json")
    assert guardados.clave_api == "gsk_123"
    assert guardados.configurado()


def test_guardar_una_clave_de_grok_en_vez_de_groq_avisa_pero_no_bloquea(
    cliente_web, tmp_path: Path
):
    """El caso real que motivó esto: una clave de xAI (Grok, «xai-...») pegada
    por error en vez de una de Groq («gsk_...»). Se guarda igual —no es a la
    app a quien le toca impedirlo— pero se avisa en el momento de guardar, no
    solo cuando falle la primera llamada."""
    respuesta = cliente_web.post(
        "/ajustes",
        data={"proveedor": "groq", "clave_api": "xai-abc123"},
        follow_redirects=True,
    )
    assert respuesta.status_code == 200
    assert "no empieza por «gsk_»".encode("utf-8") in respuesta.data
    assert "Grok".encode("utf-8") in respuesta.data
    # Se guarda igual: no es la app quien decide si una clave es válida.
    guardados = modulo_ajustes.cargar_ajustes(tmp_path / "ajustes.json")
    assert guardados.clave_api == "xai-abc123"


def test_pagina_inexistente_da_404_en_espanol(cliente_web):
    respuesta = cliente_web.get("/esto-no-existe")
    assert respuesta.status_code == 404
    assert "Página no encontrada".encode("utf-8") in respuesta.data


# --------------------------------------------------------------------------
# Soporte (usa el módulo real de Agente D, ya implementado)
# --------------------------------------------------------------------------


def test_ver_soporte(cliente_web):
    respuesta = cliente_web.get("/soporte")
    assert respuesta.status_code == 200
    assert "Soporte".encode("utf-8") in respuesta.data


def test_soporte_sin_mensaje_no_lo_envia(cliente_web):
    respuesta = cliente_web.post("/soporte", data={"asunto": "", "mensaje": ""})
    assert respuesta.status_code == 200
    assert "Rellena el asunto".encode("utf-8") in respuesta.data


def test_soporte_guarda_en_local_antes_de_redirigir(cliente_web, tmp_path: Path):
    respuesta = cliente_web.post(
        "/soporte",
        data={"asunto": "El botón de copiar no funciona", "mensaje": "Detalle del problema", "destino": "github"},
    )
    assert respuesta.status_code == 302
    assert respuesta.location.startswith("https://github.com/")

    guardados = list((tmp_path / "perfil" / "soporte").glob("*.yaml"))
    assert len(guardados) == 1


def test_soporte_por_correo_redirige_a_mailto(cliente_web):
    respuesta = cliente_web.post(
        "/soporte",
        data={"asunto": "Duda", "mensaje": "Un mensaje cualquiera", "destino": "correo"},
    )
    assert respuesta.status_code == 302
    assert respuesta.location.startswith("mailto:")
