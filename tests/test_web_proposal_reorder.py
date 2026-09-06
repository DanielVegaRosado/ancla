"""HTTP tests for reordering the proposal's selected experiences by drag
(`/propuesta/orden-experiencias`) and for the Proposal screen offering the
HTML preview's "experiences that fit" field clamped to whichever template
is selected — the two pieces that let the user choose which experiences
make a template's cut once there are more of them than it has room for."""
from __future__ import annotations

from pathlib import Path

import pytest

from ancla.profile import store
from ancla.profile.model import (
    Bilingual,
    Experience,
    Proposal,
    SelectedAboutMe,
    SelectedExperience,
)
from ancla.web import create_app
from ancla.web import draft as modulo_borrador

_EXPERIENCIAS = ["exp-1", "exp-2", "exp-3"]


@pytest.fixture
def cliente_web(tmp_path: Path):
    root = tmp_path / "perfil"
    for id_ in _EXPERIENCIAS:
        store.save_experience(
            root,
            Experience(
                id=id_,
                title=Bilingual(es=f"Rol {id_}", en=f"Role {id_}"),
                period_start="2023", period_end="",
                bullets=Bilingual(es=["Bullet"], en=["Bullet"]),
                stack="Python",
            ),
        )
    app = create_app(raiz_perfil=root, settings_path=tmp_path / "ajustes.json")
    app.config["TESTING"] = True

    modulo_borrador.save_draft(
        root,
        modulo_borrador.Draft(
            vacante="Buscamos Python.", empresa="ACME", puesto="Backend",
            propuesta=Proposal(
                language="es",
                about_me=SelectedAboutMe(group_a=[], group_b=[], text="Sobre mí.", reason=""),
                skills=[],
                experiences=[SelectedExperience(id=id_, reason=f"Motivo {id_}") for id_ in _EXPERIENCIAS],
            ),
        ),
    )
    client = app.test_client()
    client._root = root  # type: ignore[attr-defined]
    return client


def _orden_guardado(cliente_web) -> list[str]:
    borrador = modulo_borrador.load_draft(cliente_web._root)
    assert borrador is not None
    return [seleccionada.id for seleccionada in borrador.propuesta.experiences]


# --------------------------------------------------------------------------
# Reordering persists to the draft, in the same order used for the CV
# --------------------------------------------------------------------------


def test_arrastrar_reordena_las_experiencias_del_borrador(cliente_web):
    respuesta = cliente_web.post(
        "/propuesta/orden-experiencias", json={"orden": ["exp-3", "exp-1", "exp-2"]}
    )

    assert respuesta.status_code == 200
    assert _orden_guardado(cliente_web) == ["exp-3", "exp-1", "exp-2"]


def test_el_orden_nuevo_se_refleja_en_la_pantalla_de_la_propuesta(cliente_web):
    cliente_web.post("/propuesta/orden-experiencias", json={"orden": ["exp-3", "exp-1", "exp-2"]})

    html = cliente_web.get("/propuesta").data.decode("utf-8")

    assert html.index("Rol exp-3") < html.index("Rol exp-1") < html.index("Rol exp-2")


def test_un_id_que_ya_no_esta_en_la_propuesta_se_ignora_sin_perder_los_demas(cliente_web):
    respuesta = cliente_web.post(
        "/propuesta/orden-experiencias", json={"orden": ["exp-3", "inventado", "exp-1"]}
    )

    assert respuesta.status_code == 200
    assert _orden_guardado(cliente_web) == ["exp-3", "exp-1", "exp-2"]


def test_un_id_omitido_del_nuevo_orden_se_queda_al_final(cliente_web):
    cliente_web.post("/propuesta/orden-experiencias", json={"orden": ["exp-2"]})

    assert _orden_guardado(cliente_web) == ["exp-2", "exp-1", "exp-3"]


def test_sin_borrador_devuelve_404_en_vez_de_reventar(tmp_path: Path):
    app = create_app(raiz_perfil=tmp_path / "perfil", settings_path=tmp_path / "ajustes.json")
    app.config["TESTING"] = True

    respuesta = app.test_client().post("/propuesta/orden-experiencias", json={"orden": []})

    assert respuesta.status_code == 404


def test_un_cuerpo_vacio_no_revienta(cliente_web):
    respuesta = cliente_web.post("/propuesta/orden-experiencias")

    assert respuesta.status_code == 200
    assert _orden_guardado(cliente_web) == _EXPERIENCIAS
