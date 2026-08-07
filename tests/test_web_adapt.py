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
from ancla.profile.model import AboutMe, Bilingual, Experience, Skill

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
            period=Bilingual(es="2025", en="2025"),
            bullets=Bilingual(es=["Bullet"], en=["Bullet"]),
            stack=Bilingual(es="Python", en="Python"),
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
