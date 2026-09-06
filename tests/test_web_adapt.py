"""HTTP tests for the Adapt screen and "Regenerate section" on Proposal,
end to end with a fake AI client (no network, no real key spent).

Real case that prompted this: `ancla/web/views/adapt.py` and `proposal.py`
both called `motor.adapt(...)` — a leftover from `ancla.selection.motor`
before it was renamed to `ancla.selection.engine` — but neither file
imported anything named `motor`. Nothing in `tests/test_engine.py` catches
this: it calls `engine.adapt()` directly, never through these two routes.
The bug only surfaced as a live 500 in production, because no test ever
posted to `/adaptar` and got as far as a successful AI response.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ancla.profile import store
from ancla.profile.model import (
    AboutMe,
    Bilingual,
    Experience,
    Proposal,
    SelectedAboutMe,
    Skill,
)
from ancla.web import draft as modulo_borrador

VACANTE = "Backend Engineer en Nubelia. Buscamos Python y FastAPI."


@pytest.fixture
def cliente_web(tmp_path: Path):
    from ancla.web import create_app

    root = tmp_path / "perfil"
    store.save_experience(
        root,
        Experience(
            id="api-pagos",
            title=Bilingual(es="API de pagos", en="Payments API"),
            period_start="2025", period_end="",
            bullets=Bilingual(es=["Bullet"], en=["Bullet"]),
            stack="Python",
        ),
    )
    store.save_skill(root, Skill(id="python", name=Bilingual(es="Python", en="Python")))
    store.save_about_me(
        root,
        AboutMe(template=Bilingual(es="Trabajo con {GROUP_A_1}.", en="I work with {GROUP_A_1}.")),
    )

    app = create_app(raiz_perfil=root, settings_path=tmp_path / "ajustes.json")
    app.config["TESTING"] = True
    client = app.test_client()
    client.post("/ajustes", data={"proveedor": "groq", "clave_api": "gsk_test123"})
    return client


def _respuesta_ia() -> str:
    return json.dumps(
        {
            "experiencias": [{"id": "api-pagos", "motivo": "Cubre Python."}],
            "skills": ["python"],
            "motivo_skills": "Es lo que pide la vacante.",
            "sobre_mi": {"grupo_a": ["Python"], "grupo_b": ["Python"], "motivo": "x"},
            "huecos": [],
        },
        ensure_ascii=False,
    )


class _ClienteFalsoDisponible:
    def __init__(self, respuesta: str):
        self.respuesta = respuesta

    def complete(self, sistema: str, usuario: str) -> str:
        return self.respuesta

    def available(self) -> bool:
        return True


def test_adaptar_genera_propuesta_y_redirige_a_propuesta(cliente_web, monkeypatch):
    import ancla.web.views.adapt as vista_adaptar

    monkeypatch.setattr(
        vista_adaptar,
        "create_client",
        lambda proveedor, clave, url_base="", modelo="": _ClienteFalsoDisponible(_respuesta_ia()),
    )

    respuesta = cliente_web.post("/adaptar", data={"vacante": VACANTE, "idioma": "es"})

    assert respuesta.status_code == 302
    assert respuesta.location.endswith("/propuesta")


def test_regenerar_seccion_no_revienta(cliente_web, monkeypatch):
    import ancla.web.views.adapt as vista_adaptar
    import ancla.web.views.proposal as vista_propuesta

    monkeypatch.setattr(
        vista_adaptar,
        "create_client",
        lambda proveedor, clave, url_base="", modelo="": _ClienteFalsoDisponible(_respuesta_ia()),
    )
    cliente_web.post("/adaptar", data={"vacante": VACANTE, "idioma": "es"})

    monkeypatch.setattr(
        vista_propuesta,
        "create_client",
        lambda proveedor, clave, url_base="", modelo="": _ClienteFalsoDisponible(_respuesta_ia()),
    )

    respuesta = cliente_web.post("/propuesta/regenerar/skills")

    assert respuesta.status_code == 302
    assert respuesta.location.endswith("/propuesta")


def test_la_propuesta_sin_borrador_devuelve_a_adaptar_explicando_el_orden(cliente_web):
    """The menu presents Adapt and Proposal as two steps of one flow, so
    reaching Proposal with nothing adapted has to land on Adapt and say why
    instead of showing an empty screen."""
    respuesta = cliente_web.get("/propuesta")
    assert respuesta.status_code == 302
    assert respuesta.location.endswith("/adaptar")

    pagina = cliente_web.get("/adaptar").get_data(as_text=True)
    assert "todavía no has adaptado ninguna" in pagina


def test_el_menu_nombra_los_dos_pasos_del_mismo_recorrido(cliente_web):
    pagina = cliente_web.get("/adaptar").get_data(as_text=True)
    assert "Adaptar a una vacante" in pagina
    assert "Última propuesta" in pagina


def test_el_menu_atenua_ultima_propuesta_sin_borrador(cliente_web):
    """Atenuado, no oculto: el enlace sigue llevando a su destino (que a su
    vez explica la relación paso 1 → paso 2), solo deja de leerse como una
    sección con contenido propio."""
    pagina = cliente_web.get("/adaptar").get_data(as_text=True)
    assert 'href="/propuesta" class="desactivado"' in pagina


def test_el_menu_no_atenua_ultima_propuesta_con_borrador(cliente_web, monkeypatch):
    import ancla.web.views.adapt as vista_adaptar

    monkeypatch.setattr(
        vista_adaptar,
        "create_client",
        lambda proveedor, clave, url_base="", modelo="": _ClienteFalsoDisponible(_respuesta_ia()),
    )
    cliente_web.post("/adaptar", data={"vacante": VACANTE, "idioma": "es"})

    pagina = cliente_web.get("/adaptar").get_data(as_text=True)
    assert "desactivado" not in pagina
    assert 'href="/propuesta" class="">' in pagina


def test_propuesta_ofrece_salida_para_adaptar_otra_vacante(cliente_web, monkeypatch):
    import ancla.web.views.adapt as vista_adaptar

    monkeypatch.setattr(
        vista_adaptar,
        "create_client",
        lambda proveedor, clave, url_base="", modelo="": _ClienteFalsoDisponible(_respuesta_ia()),
    )
    cliente_web.post("/adaptar", data={"vacante": VACANTE, "idioma": "es"})

    pagina = cliente_web.get("/propuesta").get_data(as_text=True)
    assert 'action="/adaptar"' in pagina
    assert "Adaptar otra vacante" in pagina
    assert "data-confirmar" in pagina.split('action="/adaptar"')[1][:400]


def test_el_formulario_de_adaptar_avisa_si_ya_hay_borrador(cliente_web):
    """The second door onto the same overwrite: entering through the menu
    and submitting the Adapt form replaces the draft exactly like the
    "Adaptar otra vacante" exit on Proposal, so it needs the same guard."""
    modulo_borrador.save_draft(
        cliente_web.application.config["RAIZ_PERFIL"],
        modulo_borrador.Draft(
            vacante="Otra vacante",
            empresa="ACME",
            puesto="Backend",
            propuesta=Proposal(
                language="es",
                about_me=SelectedAboutMe(group_a=[], group_b=[], text="x", reason=""),
                skills=["python"],
                experiences=[],
            ),
        ),
    )

    pagina = cliente_web.get("/adaptar").get_data(as_text=True)

    assert "data-confirmar" in pagina.split('action="/adaptar"')[1][:400]


def test_el_formulario_de_adaptar_no_avisa_sin_borrador(cliente_web):
    pagina = cliente_web.get("/adaptar").get_data(as_text=True)

    assert "data-confirmar" not in pagina.split('action="/adaptar"')[1][:400]


# --------------------------------------------------------------------------
# Adapting to a language the profile only half has
# --------------------------------------------------------------------------


def test_adaptar_a_un_idioma_incompleto_avisa_nombrando_las_entradas(cliente_web, tmp_path: Path):
    """The user decides, but knowing which entries would come out blank: a
    count is not something anyone can weigh against a posting."""
    store.save_skill(
        cliente_web.application.config["RAIZ_PERFIL"],
        Skill(id="sql", name=Bilingual(es="SQL avanzado", en="")),
    )

    respuesta = cliente_web.post("/adaptar", data={"vacante": VACANTE, "idioma": "en"})

    assert respuesta.status_code == 200
    assert "SQL avanzado".encode("utf-8") in respuesta.data
    assert b"forzar_idioma" in respuesta.data


def test_el_aviso_de_idioma_no_traduce_por_su_cuenta(cliente_web, tmp_path: Path, monkeypatch):
    """Translating here would spend a call nobody asked for, immediately
    before the big one."""
    import ancla.web.views.adapt as vista_adaptar

    store.save_skill(
        cliente_web.application.config["RAIZ_PERFIL"],
        Skill(id="sql", name=Bilingual(es="SQL avanzado", en="")),
    )
    llamadas = []
    monkeypatch.setattr(
        vista_adaptar,
        "create_client",
        lambda *args, **kwargs: llamadas.append(args) or _ClienteFalsoDisponible(_respuesta_ia()),
    )

    cliente_web.post("/adaptar", data={"vacante": VACANTE, "idioma": "en"})

    assert llamadas == []


def test_seguir_adelante_genera_la_propuesta_igualmente(cliente_web, monkeypatch):
    import ancla.web.views.adapt as vista_adaptar

    store.save_skill(
        cliente_web.application.config["RAIZ_PERFIL"],
        Skill(id="sql", name=Bilingual(es="SQL avanzado", en="")),
    )
    monkeypatch.setattr(
        vista_adaptar,
        "create_client",
        lambda proveedor, clave, url_base="", modelo="": _ClienteFalsoDisponible(_respuesta_ia()),
    )

    respuesta = cliente_web.post(
        "/adaptar", data={"vacante": VACANTE, "idioma": "en", "forzar_idioma": "1"}
    )

    assert respuesta.status_code == 302
    assert respuesta.location.endswith("/propuesta")


def test_un_perfil_completo_no_avisa_de_nada(cliente_web, monkeypatch):
    import ancla.web.views.adapt as vista_adaptar

    monkeypatch.setattr(
        vista_adaptar,
        "create_client",
        lambda proveedor, clave, url_base="", modelo="": _ClienteFalsoDisponible(_respuesta_ia()),
    )

    respuesta = cliente_web.post("/adaptar", data={"vacante": VACANTE, "idioma": "en"})

    assert respuesta.status_code == 302
