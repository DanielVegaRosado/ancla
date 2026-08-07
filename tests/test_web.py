"""Tests for the web layer that do not depend on modules other agents were
implementing in parallel (almacen, motor, archivo, vacante used to raise
NotImplementedError until they were integrated). These cover what is agent
C's exclusive responsibility: utilities, settings, the ephemeral work draft,
the provider factory and the Settings screen.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from ancla.ai.client import AIError
from ancla.profile.model import (
    Proposal,
    SelectedAboutMe,
    SelectedExperience,
)
from ancla.web import settings as modulo_ajustes
from ancla.web import draft as modulo_borrador
from ancla.web import create_app
from ancla.web.providers import create_client
from ancla.web.util import (
    csv_to_list,
    lines_to_list,
    list_to_csv,
    list_to_lines,
    slugify,
)


# --------------------------------------------------------------------------
# util.py
# --------------------------------------------------------------------------


def test_slugificar_quita_acentos_y_espacios():
    assert slugify("Ingeniero de Datos (Backend)") == "ingeniero-de-datos-backend"


def test_slugificar_texto_vacio_da_un_valor_por_defecto():
    assert slugify("   ") == "sin-titulo"


def test_lineas_a_lista_ignora_lineas_vacias():
    assert lines_to_list("Uno\n\n  Dos  \n\nTres") == ["Uno", "Dos", "Tres"]


def test_lista_a_lineas_es_el_inverso():
    assert list_to_lines(["Uno", "Dos"]) == "Uno\nDos"


def test_csv_a_lista_recorta_espacios():
    assert csv_to_list("python,  sql , gcp") == ["python", "sql", "gcp"]


def test_lista_a_csv_es_el_inverso():
    assert list_to_csv(["python", "sql"]) == "python, sql"


# --------------------------------------------------------------------------
# ajustes.py
# --------------------------------------------------------------------------


def test_cargar_ajustes_sin_fichero_da_valores_por_defecto(tmp_path: Path):
    ajustes = modulo_ajustes.load_settings(tmp_path / "ajustes.json")
    assert ajustes.proveedor == "groq"
    assert ajustes.clave_api == ""
    assert not ajustes.configured()


def test_guardar_y_cargar_ajustes_hace_ida_y_vuelta(tmp_path: Path):
    ruta = tmp_path / "ajustes.json"
    originales = modulo_ajustes.Settings(proveedor="groq", clave_api="gsk_secreta")
    modulo_ajustes.save_settings(originales, ruta)

    recargados = modulo_ajustes.load_settings(ruta)
    assert recargados == originales
    assert recargados.configured()


def test_ajustes_con_fichero_corrupto_no_rompe(tmp_path: Path):
    ruta = tmp_path / "ajustes.json"
    ruta.write_text("esto no es json", encoding="utf-8")
    ajustes = modulo_ajustes.load_settings(ruta)
    assert ajustes == modulo_ajustes.Settings()


# --------------------------------------------------------------------------
# borrador.py
# --------------------------------------------------------------------------


def _propuesta_de_prueba() -> Proposal:
    return Proposal(
        language="es",
        about_me=SelectedAboutMe(group_a=["a", "b", "c"], group_b=["d", "e", "f"], text="Texto."),
        skills=["python", "sql"],
        experiences=[SelectedExperience(id="proyecto-x", reason="Encaja.")],
        gaps=["Kubernetes"],
    )


def test_no_hay_borrador_si_no_se_ha_guardado_ninguno(tmp_path: Path):
    assert modulo_borrador.load_draft(tmp_path) is None


def test_guardar_y_cargar_borrador_hace_ida_y_vuelta(tmp_path: Path):
    original = modulo_borrador.Draft(
        vacante="Se busca ingeniero...",
        empresa="Acme",
        puesto="Backend Engineer",
        propuesta=_propuesta_de_prueba(),
    )
    modulo_borrador.save_draft(tmp_path, original)

    recargado = modulo_borrador.load_draft(tmp_path)
    assert recargado == original


def test_borrar_borrador_lo_deja_indisponible(tmp_path: Path):
    modulo_borrador.save_draft(
        tmp_path,
        modulo_borrador.Draft(vacante="x", empresa="", puesto="", propuesta=_propuesta_de_prueba()),
    )
    modulo_borrador.delete_draft(tmp_path)
    assert modulo_borrador.load_draft(tmp_path) is None


def test_borrar_borrador_sin_fichero_no_falla(tmp_path: Path):
    modulo_borrador.delete_draft(tmp_path)  # no debe lanzar


# --------------------------------------------------------------------------
# proveedores.py
# --------------------------------------------------------------------------


def test_crear_cliente_con_proveedor_desconocido_lanza_error_ia():
    with pytest.raises(AIError):
        create_client("proveedor-inventado", "clave")


# --------------------------------------------------------------------------
# Settings screen (end to end, does not depend on other agents)
# --------------------------------------------------------------------------


@pytest.fixture
def cliente_web(tmp_path: Path):
    app = create_app(raiz_perfil=tmp_path / "perfil", settings_path=tmp_path / "ajustes.json")
    app.config["TESTING"] = True
    return app.test_client()


def test_ver_ajustes_sin_configurar(cliente_web):
    respuesta = cliente_web.get("/ajustes")
    assert respuesta.status_code == 200
    assert "Todavía no has configurado ninguna clave".encode("utf-8") in respuesta.data


def test_ajustes_enlaza_directo_a_conseguir_la_clave(cliente_web):
    """The link has to be right here, before anyone gets it wrong — not
    only in the error message that comes after."""
    respuesta = cliente_web.get("/ajustes")
    assert b"console.groq.com/keys" in respuesta.data


def test_ajustes_explica_el_limite_diario_de_groq(cliente_web):
    """Verified live on 2026-07-23: the quota-exhausted warning is almost
    always the daily limit (200,000 tokens/day), not the per-minute one —
    Settings has to say so with that figure, not just "wait a while"."""
    respuesta = cliente_web.get("/ajustes")
    assert "200.000 tokens al día".encode("utf-8") in respuesta.data
    assert "segunda cuenta gratuita".encode("utf-8") in respuesta.data


def test_guardar_ajustes_los_persiste(cliente_web, tmp_path: Path):
    respuesta = cliente_web.post(
        "/ajustes", data={"proveedor": "groq", "clave_api": "gsk_123"}, follow_redirects=True
    )
    assert respuesta.status_code == 200
    guardados = modulo_ajustes.load_settings(tmp_path / "ajustes.json")
    assert guardados.clave_api == "gsk_123"
    assert guardados.configured()


def test_guardar_una_clave_de_grok_en_vez_de_groq_avisa_pero_no_bloquea(
    cliente_web, tmp_path: Path
):
    """The real case that prompted this: an xAI (Grok, «xai-...») key pasted
    by mistake instead of a Groq one («gsk_...»). It is saved all the same
    —it is not the app's place to prevent it— but it is flagged right when
    it is saved, not only when the first call fails."""
    respuesta = cliente_web.post(
        "/ajustes",
        data={"proveedor": "groq", "clave_api": "xai-abc123"},
        follow_redirects=True,
    )
    assert respuesta.status_code == 200
    assert "no empieza por «gsk_»".encode("utf-8") in respuesta.data
    assert "Grok".encode("utf-8") in respuesta.data
    # It is saved all the same: it is not up to the app to decide if a key is valid.
    guardados = modulo_ajustes.load_settings(tmp_path / "ajustes.json")
    assert guardados.clave_api == "xai-abc123"


def test_pagina_inexistente_da_404_en_espanol(cliente_web):
    respuesta = cliente_web.get("/esto-no-existe")
    assert respuesta.status_code == 404
    assert "Página no encontrada".encode("utf-8") in respuesta.data


# --------------------------------------------------------------------------
# Support (uses agent D's real module, already implemented)
# --------------------------------------------------------------------------


def test_ver_soporte(cliente_web):
    respuesta = cliente_web.get("/soporte")
    assert respuesta.status_code == 200
    assert "Soporte".encode("utf-8") in respuesta.data


def test_soporte_sin_mensaje_no_lo_envia(cliente_web):
    """The subject is optional on purpose (to lower the friction of leaving
    feedback); the message is the only thing that is required."""
    respuesta = cliente_web.post("/soporte", data={"asunto": "", "mensaje": ""})
    assert respuesta.status_code == 200
    assert "Cuéntanos qué ha pasado".encode("utf-8") in respuesta.data


def test_soporte_sin_asunto_pero_con_mensaje_si_se_envia(cliente_web, tmp_path: Path):
    respuesta = cliente_web.post(
        "/soporte", data={"asunto": "", "mensaje": "Esto podría ser más claro."}
    )
    assert respuesta.status_code == 302
    assert list((tmp_path / "perfil" / "support").iterdir())


def test_soporte_guarda_en_local_antes_de_redirigir(cliente_web, tmp_path: Path):
    respuesta = cliente_web.post(
        "/soporte",
        data={"asunto": "El botón de copiar no funciona", "mensaje": "Detalle del problema", "destino": "github"},
    )
    assert respuesta.status_code == 302
    assert respuesta.location.startswith("https://github.com/")

    guardados = list((tmp_path / "perfil" / "support").glob("*.yaml"))
    assert len(guardados) == 1


def test_soporte_por_correo_redirige_a_mailto(cliente_web):
    respuesta = cliente_web.post(
        "/soporte",
        data={"asunto": "Duda", "mensaje": "Un mensaje cualquiera", "destino": "correo"},
    )
    assert respuesta.status_code == 302
    assert respuesta.location.startswith("mailto:")


def test_soporte_ofrece_elegir_entre_problema_y_sugerencia(cliente_web):
    """Seeing an explicit "suggestion" option is what tells someone without
    a bug that they can write in too."""
    respuesta = cliente_web.get("/soporte")
    html = respuesta.data.decode("utf-8")
    assert 'value="problema"' in html
    assert 'value="sugerencia"' in html


def test_el_tipo_elegido_se_refleja_en_el_titulo_de_la_incidencia(cliente_web):
    respuesta = cliente_web.post(
        "/soporte",
        data={
            "asunto": "El botón de copiar no responde",
            "mensaje": "Detalle",
            "tipo": "problema",
            "destino": "github",
        },
    )
    assert "Problema" in respuesta.location


def test_una_sugerencia_tambien_queda_etiquetada(cliente_web):
    respuesta = cliente_web.post(
        "/soporte",
        data={
            "asunto": "",
            "mensaje": "Estaría bien poder duplicar una experiencia.",
            "tipo": "sugerencia",
            "destino": "correo",
        },
    )
    assert "Sugerencia" in respuesta.location


def test_un_tipo_desconocido_no_rompe_el_envio(cliente_web):
    """If someone tampers with the form by hand, it falls back to the
    default value instead of failing."""
    respuesta = cliente_web.post(
        "/soporte",
        data={"asunto": "x", "mensaje": "x", "tipo": "algo-raro", "destino": "github"},
    )
    assert respuesta.status_code == 302


# --------------------------------------------------------------------------
# Terms and conditions
# --------------------------------------------------------------------------


def test_terminos_explica_que_los_datos_no_salen_del_ordenador(cliente_web):
    respuesta = cliente_web.get("/terminos")
    assert respuesta.status_code == 200
    assert "no salen de tu ordenador".encode("utf-8") in respuesta.data
    assert "no hay servidor de este proyecto".encode("utf-8") in respuesta.data


def test_terminos_enlaza_al_repositorio_publico(cliente_web):
    from ancla.support.messages import REPOSITORIO

    respuesta = cliente_web.get("/terminos")
    assert REPOSITORIO.encode("utf-8") in respuesta.data


def test_terminos_identifica_al_autor_y_da_contacto(cliente_web):
    from ancla.support.messages import CORREO_SOPORTE

    respuesta = cliente_web.get("/terminos")
    assert "Daniel Vega Rosado".encode("utf-8") in respuesta.data
    assert CORREO_SOPORTE.encode("utf-8") in respuesta.data


def test_terminos_menciona_la_licencia_sin_garantia(cliente_web):
    respuesta = cliente_web.get("/terminos")
    assert "licencia MIT".encode("utf-8") in respuesta.data
    assert "tal cual".encode("utf-8") in respuesta.data


def test_terminos_explica_la_cookie_de_sesion(cliente_web):
    respuesta = cliente_web.get("/terminos")
    assert "cookie de sesión".encode("utf-8") in respuesta.data


def test_el_pie_de_cualquier_pantalla_enlaza_a_terminos(cliente_web):
    respuesta = cliente_web.get("/perfil")
    assert b'href="/terminos"' in respuesta.data


# --------------------------------------------------------------------------
# Demo mode (Hugging Face Space): without this flag nothing changes; with
# it, the API key is stored per session instead of in ajustes.json, because
# every visitor shares the same process and the same example profile.
# --------------------------------------------------------------------------


@pytest.fixture
def app_demo(tmp_path: Path):
    app = create_app(
        raiz_perfil=tmp_path / "perfil", settings_path=tmp_path / "ajustes.json", demo_mode=True
    )
    app.config["TESTING"] = True
    return app


@pytest.fixture
def cliente_demo(app_demo):
    return app_demo.test_client()


def test_fuera_de_modo_demo_no_aparece_el_aviso(cliente_web):
    respuesta = cliente_web.get("/perfil")
    assert "Demo pública".encode("utf-8") not in respuesta.data


def test_en_modo_demo_aparece_el_aviso(cliente_demo):
    respuesta = cliente_demo.get("/perfil")
    assert "Demo pública".encode("utf-8") in respuesta.data


def test_en_modo_demo_la_clave_no_se_escribe_en_ajustes_json(cliente_demo, tmp_path: Path):
    cliente_demo.post(
        "/ajustes", data={"proveedor": "groq", "clave_api": "gsk_visitante_a"}, follow_redirects=True
    )
    ruta = tmp_path / "ajustes.json"
    assert not ruta.exists()


def test_en_modo_demo_la_clave_persiste_para_la_misma_sesion(cliente_demo):
    cliente_demo.post(
        "/ajustes", data={"proveedor": "groq", "clave_api": "gsk_visitante_a"}, follow_redirects=True
    )
    respuesta = cliente_demo.get("/ajustes")
    assert b"gsk_visitante_a" in respuesta.data


def test_en_modo_demo_dos_sesiones_distintas_no_comparten_clave(app_demo, cliente_demo):
    """The real scenario that prompted demo mode: two different visitors to
    the same Space must not see the key the other one has tried."""
    otro_visitante = app_demo.test_client()

    cliente_demo.post(
        "/ajustes", data={"proveedor": "groq", "clave_api": "gsk_visitante_a"}, follow_redirects=True
    )
    respuesta = otro_visitante.get("/ajustes")
    assert b"gsk_visitante_a" not in respuesta.data
