"""Tests for the web layer that do not depend on modules other agents were
implementing in parallel (almacen, motor, archivo, vacante used to raise
NotImplementedError until they were integrated). These cover what is agent
C's exclusive responsibility: utilities, settings, the ephemeral work draft,
the provider factory and the Settings screen.
"""
from __future__ import annotations

import re
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


def test_un_ajustes_json_con_una_sola_clave_se_lee_sin_perderla(tmp_path: Path):
    """The shape before per-provider keys existed: a single top-level
    `clave_api`, with no `claves_api` map at all. An installation that
    already has one of these must keep working exactly as before."""
    import json

    ruta = tmp_path / "ajustes.json"
    ruta.write_text(
        json.dumps({"proveedor": "groq", "clave_api": "gsk_de_antes", "modelo": "", "url_base": ""}),
        encoding="utf-8",
    )

    ajustes = modulo_ajustes.load_settings(ruta)
    assert ajustes.clave_api == "gsk_de_antes"
    assert ajustes.claves_api == {"groq": "gsk_de_antes"}
    assert ajustes.configured()


def test_guardar_la_clave_de_un_proveedor_no_pisa_la_de_otro(tmp_path: Path):
    ruta = tmp_path / "ajustes.json"
    modulo_ajustes.save_settings(
        modulo_ajustes.Settings(proveedor="groq", clave_api="gsk_groq"), ruta
    )

    actuales = modulo_ajustes.load_settings(ruta)
    modulo_ajustes.save_settings(
        modulo_ajustes.Settings(
            proveedor="openai",
            claves_api={**actuales.claves_api, "openai": "sk-openai"},
            modelo="gpt-4o-mini",
        ),
        ruta,
    )

    recargados = modulo_ajustes.load_settings(ruta)
    assert recargados.claves_api == {"groq": "gsk_groq", "openai": "sk-openai"}
    assert recargados.clave_api == "sk-openai"
    assert recargados.saved_key("groq") == "gsk_groq"


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


def test_modelo_inexistente_en_proveedor_openai_compatible_nombra_el_modelo(cliente_web):
    """Same known cost documented in `Provider.default_model`'s docstring: a
    default model can be retired by the provider later, and the 404 message
    has to name it, same pattern as `groq.py`'s own 404 handling."""
    import httpx
    from openai import NotFoundError

    from ancla.ai.openai_compatible import OpenAICompatibleClient

    peticion = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    error = NotFoundError(
        "model not found",
        response=httpx.Response(404, request=peticion),
        body=None,
    )
    cliente = OpenAICompatibleClient("clave", "https://api.openai.com/v1", "gpt-inventado")
    with cliente_web.application.test_request_context():
        explicacion = cliente._explain(error)
    assert "gpt-inventado" in explicacion


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


def test_una_clave_con_otro_prefijo_avisa_pero_no_bloquea(cliente_web, tmp_path: Path):
    """The real case that prompted this: an xAI (Grok, «xai-...») key pasted
    by mistake instead of a Groq one («gsk_...»). It is saved all the same
    —it is not the app's place to decide whether a key is valid— but it is
    flagged when it is saved, not only when the first call fails.

    Asserting on where to go and what shape to look for, not on the wording:
    the message has to leave the person able to fix it, and that is the part
    that must survive the next rewrite."""
    respuesta = cliente_web.post(
        "/ajustes",
        data={"proveedor": "groq", "clave_api": "xai-abc123"},
        follow_redirects=True,
    )
    assert respuesta.status_code == 200
    assert "console.groq.com".encode("utf-8") in respuesta.data
    assert "gsk_".encode("utf-8") in respuesta.data
    guardados = modulo_ajustes.load_settings(tmp_path / "ajustes.json")
    assert guardados.clave_api == "xai-abc123"


def test_guardar_la_clave_de_un_proveedor_no_pisa_la_de_otro_en_el_formulario(
    cliente_web, tmp_path: Path
):
    """The bug this card exists to close: switching provider used to leave
    the previous provider's key sitting in the field, so saving without
    retyping it saved that key under the new provider's name."""
    cliente_web.post(
        "/ajustes", data={"proveedor": "groq", "clave_api": "gsk_groq"}, follow_redirects=True
    )
    cliente_web.post(
        "/ajustes", data={"proveedor": "openai", "clave_api": "sk-openai"}, follow_redirects=True
    )

    guardados = modulo_ajustes.load_settings(tmp_path / "ajustes.json")
    assert guardados.saved_key("groq") == "gsk_groq"
    assert guardados.saved_key("openai") == "sk-openai"


def test_el_mensaje_de_clave_guardada_refleja_el_proveedor_elegido(cliente_web, tmp_path: Path):
    """Only a key already saved for the *selected* provider should say so —
    saving Groq's key must not make OpenAI's line claim one is saved too."""
    cliente_web.post(
        "/ajustes", data={"proveedor": "groq", "clave_api": "gsk_groq"}, follow_redirects=True
    )

    html = cliente_web.get("/ajustes").data.decode("utf-8")
    assert "Ya tienes una clave de Groq guardada." in html
    assert "Todavía no has configurado ninguna clave de OpenAI." in html


def _bloque_del_modelo(html: str) -> str:
    """The `<div class="campo" data-mostrar-si-proveedor="personalizado" ...>`
    wrapper that holds Model and Base URL — where the `hidden` attribute
    that decides whether it shows actually lives."""
    inicio = html.index('<div class="campo" data-mostrar-si-proveedor="personalizado"')
    return html[inicio : inicio + 100]


def test_un_proveedor_conocido_no_ensena_el_campo_de_modelo(cliente_web, tmp_path: Path):
    """With a known provider, only the key is asked for — the model uses
    `Provider.default_model` silently, with no field to see or fill."""
    cliente_web.post(
        "/ajustes", data={"proveedor": "groq", "clave_api": "gsk_groq"}, follow_redirects=True
    )

    html = cliente_web.get("/ajustes").data.decode("utf-8")
    assert 'id="modelo"' in html
    assert "hidden" in _bloque_del_modelo(html)


def test_otra_api_ensena_modelo_y_url_directamente_sin_plegable(cliente_web, tmp_path: Path):
    cliente_web.post(
        "/ajustes",
        data={"proveedor": "personalizado", "clave_api": "clave", "modelo": "m", "url_base": "https://x"},
        follow_redirects=True,
    )

    html = cliente_web.get("/ajustes").data.decode("utf-8")
    assert "<details" not in html
    assert 'id="modelo"' in html
    assert "hidden" not in _bloque_del_modelo(html)


def test_un_unico_input_de_modelo_en_el_dom_sea_cual_sea_el_proveedor(cliente_web, tmp_path: Path):
    """Two `name="modelo"` inputs would both be submitted, and the server
    keeps whichever appears first in the HTML — never the visible one."""
    for proveedor in ("groq", "openai", "anthropic", "personalizado"):
        cliente_web.post("/ajustes", data={"proveedor": proveedor, "clave_api": "x"}, follow_redirects=True)
        html = cliente_web.get("/ajustes").data.decode("utf-8")
        assert html.count('name="modelo"') == 1


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
    assert "licencia AGPL-3.0".encode("utf-8") in respuesta.data
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


# --------------------------------------------------------------------------
# Anthropic: what the user is told before and after it fails
# --------------------------------------------------------------------------


def _error_de_anthropic(clase, mensaje: str, codigo: int):
    import httpx

    peticion = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return clase(mensaje, response=httpx.Response(codigo, request=peticion), body=None)


def _explicacion_de_anthropic(cliente_web, excepcion: Exception) -> str:
    """`_explain` returns translated text, and gettext needs an app context."""
    from ancla.ai.anthropic import AnthropicClient

    with cliente_web.application.test_request_context():
        return AnthropicClient("clave-inventada", "claude-inventado")._explain(excepcion)


def test_ajustes_avisa_de_que_anthropic_necesita_saldo(cliente_web):
    """The failure the app has to prevent, not just report: Anthropic has no
    free tier, so a key created for a first try fails until the account has
    credit. Asserting on the actionable part (that money is needed, and
    where the key comes from), not on the wording."""
    respuesta = cliente_web.get("/ajustes").data.decode("utf-8")
    assert "saldo" in respuesta
    assert "console.anthropic.com/settings/keys" in respuesta


def test_ajustes_enlaza_a_la_pagina_de_claves_de_cada_proveedor(cliente_web):
    from ancla.web.providers import PROVIDERS

    respuesta = cliente_web.get("/ajustes").data.decode("utf-8")
    for entrada in PROVIDERS.values():
        if entrada.key_url:
            assert entrada.key_url in respuesta


def test_el_proveedor_personalizado_no_inventa_una_pagina_de_claves():
    """There is no key page to point at when the endpoint is the user's own."""
    from ancla.web.providers import PROVIDERS

    assert PROVIDERS["personalizado"].key_url == ""


def test_todo_proveedor_ofrecido_en_ajustes_tiene_entrada_en_el_registro():
    """The dropdown and the factory registry must not drift apart: an option
    with no entry would be a provider that cannot be built."""
    from ancla.web.providers import PROVIDERS

    assert set(modulo_ajustes.PROVEEDORES) == set(PROVIDERS)


def test_guardar_ajustes_con_anthropic_los_persiste(cliente_web, tmp_path: Path):
    cliente_web.post(
        "/ajustes",
        data={"proveedor": "anthropic", "clave_api": "sk-ant-inventada", "modelo": "claude-x"},
        follow_redirects=True,
    )
    guardados = modulo_ajustes.load_settings(tmp_path / "ajustes.json")
    assert guardados.proveedor == "anthropic"
    assert guardados.configured()


@pytest.mark.parametrize("proveedor", ["openai", "anthropic", "mistral", "openrouter"])
def test_pegar_solo_la_clave_deja_el_proveedor_configurado(cliente_web, tmp_path: Path, proveedor: str):
    """The bug this card exists to close: for every known provider except
    Groq, the model used to be required text with no value of its own — the
    exact spot where someone types "Claude" instead of a real model id.
    Posting only the provider and the key (no "modelo" field at all, same as
    a form where the Model input was never touched) must be enough."""
    from ancla.web.providers import PROVIDERS

    cliente_web.post(
        "/ajustes",
        data={"proveedor": proveedor, "clave_api": "clave-inventada"},
        follow_redirects=True,
    )
    guardados = modulo_ajustes.load_settings(tmp_path / "ajustes.json")
    assert guardados.proveedor == proveedor
    assert guardados.configured()
    assert guardados.modelo == PROVIDERS[proveedor].default_model


def test_pegar_solo_la_clave_de_otra_api_no_deja_el_proveedor_configurado(
    cliente_web, tmp_path: Path
):
    """`personalizado` is the one exception: there is no endpoint to guess a
    default model for, so leaving Model (and URL base) blank must keep it
    unconfigured rather than silently making one up."""
    cliente_web.post(
        "/ajustes",
        data={"proveedor": "personalizado", "clave_api": "clave-inventada"},
        follow_redirects=True,
    )
    guardados = modulo_ajustes.load_settings(tmp_path / "ajustes.json")
    assert guardados.proveedor == "personalizado"
    assert not guardados.configured()
    assert guardados.modelo == ""


def test_el_desplegable_de_proveedores_no_se_puede_desincronizar_del_registro(cliente_web):
    """The dropdown is generated from `PROVIDERS`, in the same order, so a
    provider added there shows up here with no second edit — and
    "personalizado" (the only one with no known default) stays last."""
    from ancla.web.providers import PROVIDERS

    respuesta = cliente_web.get("/ajustes").data.decode("utf-8")
    for clave in PROVIDERS:
        assert f'value="{clave}"' in respuesta
    assert list(PROVIDERS)[-1] == "personalizado"


def test_otra_api_sigue_pidiendo_url_base(cliente_web):
    respuesta = cliente_web.get("/ajustes").data.decode("utf-8")
    assert 'id="url_base"' in respuesta


def test_la_etiqueta_de_otra_api_se_traduce(cliente_web):
    """`Provider.name` for "personalizado" is a plain Python string, frozen
    at import time — it cannot be the text shown, or the option would stay
    in Spanish with the English interface. `display_name` resolves it with
    `_()` at request time instead."""
    cliente_web.post(
        "/ajustes",
        data={"proveedor": "groq", "clave_api": "gsk_1", "idioma": "en"},
        follow_redirects=True,
    )
    respuesta = cliente_web.get("/ajustes").data.decode("utf-8")
    assert "Other (manual URL)" in respuesta


def test_guardar_una_clave_mal_pegada_de_anthropic_avisa_pero_no_bloquea(
    cliente_web, tmp_path: Path
):
    """Same pattern already in place for Groq's `gsk_` prefix: flag a key
    that does not look like Anthropic's at save time, without refusing it."""
    respuesta = cliente_web.post(
        "/ajustes",
        data={"proveedor": "anthropic", "clave_api": "sk-otra-cosa", "modelo": "claude-x"},
        follow_redirects=True,
    )
    assert respuesta.status_code == 200
    assert "sk-ant-".encode("utf-8") in respuesta.data
    guardados = modulo_ajustes.load_settings(tmp_path / "ajustes.json")
    assert guardados.clave_api == "sk-otra-cosa"


def test_una_clave_con_la_forma_correcta_no_avisa(cliente_web):
    """Right prefix and long enough: no warning, only the generic
    "Ajustes guardados." flash."""
    respuesta = cliente_web.post(
        "/ajustes",
        data={"proveedor": "groq", "clave_api": "gsk_" + "a" * 50},
        follow_redirects=True,
    )
    assert "no parece de Groq".encode("utf-8") not in respuesta.data


def test_una_clave_demasiado_corta_avisa_aunque_tenga_el_prefijo_correcto(cliente_web):
    """The prefix alone does not make a key plausible: `gsk_prueba` starts
    right but is nowhere near a real Groq key's length."""
    respuesta = cliente_web.post(
        "/ajustes",
        data={"proveedor": "groq", "clave_api": "gsk_prueba"},
        follow_redirects=True,
    )
    assert "no parece de Groq".encode("utf-8") in respuesta.data


def test_avisar_de_una_clave_con_forma_sospechosa_no_impide_guardarla(
    cliente_web, tmp_path: Path
):
    """The shape check is a warning, never a gate: only the provider's own
    API call can actually confirm a key works, so an implausible-looking
    key is still saved as typed."""
    respuesta = cliente_web.post(
        "/ajustes",
        data={"proveedor": "groq", "clave_api": "gsk_prueba"},
        follow_redirects=True,
    )
    assert respuesta.status_code == 200
    guardados = modulo_ajustes.load_settings(tmp_path / "ajustes.json")
    assert guardados.clave_api == "gsk_prueba"
    assert guardados.configured()


def test_un_proveedor_sin_prefijo_conocido_nunca_avisa(cliente_web):
    """`personalizado` has no confirmed key shape (`key_hint` empty), so any
    string is accepted without a warning — any format is legitimate there."""
    respuesta = cliente_web.post(
        "/ajustes",
        data={
            "proveedor": "personalizado",
            "clave_api": "x",
            "modelo": "m",
            "url_base": "https://x",
        },
        follow_redirects=True,
    )
    assert "no parece de".encode("utf-8") not in respuesta.data


def test_sin_saldo_en_anthropic_dice_que_comprar_credito_o_cambiar_a_groq(cliente_web):
    """The most likely first failure with Anthropic, and the one that used to
    read as a generic bad request: it arrives as a plain 400, so the user has
    to be told where to add credit and that Groq is the free way out."""
    import anthropic

    error = _error_de_anthropic(
        anthropic.BadRequestError,
        "Your credit balance is too low to access the Anthropic API.",
        400,
    )
    explicacion = _explicacion_de_anthropic(cliente_web, error)
    assert "console.anthropic.com/settings/billing" in explicacion
    assert "Groq" in explicacion


def test_clave_invalida_de_anthropic_dice_donde_generar_otra(cliente_web):
    import anthropic

    error = _error_de_anthropic(anthropic.AuthenticationError, "invalid x-api-key", 401)
    explicacion = _explicacion_de_anthropic(cliente_web, error)
    assert "console.anthropic.com/settings/keys" in explicacion
    assert "Ajustes" in explicacion


def test_modelo_inexistente_en_anthropic_nombra_el_modelo_configurado(cliente_web):
    """Naming the model the user actually typed is the whole point: the fix
    is a typo in Settings, and they cannot see it from a generic message."""
    import anthropic

    error = _error_de_anthropic(anthropic.NotFoundError, "model not found", 404)
    explicacion = _explicacion_de_anthropic(cliente_web, error)
    assert "claude-inventado" in explicacion
    assert "Ajustes" in explicacion


def test_timeout_de_anthropic_dice_volver_a_generar(cliente_web):
    import anthropic
    import httpx

    error = anthropic.APITimeoutError(
        request=httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    )
    assert "propuesta" in _explicacion_de_anthropic(cliente_web, error)
