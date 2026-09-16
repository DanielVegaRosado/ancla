"""Per-account data isolation: with a logged-in user, the profile, the
archived CVs and the settings live in `perfiles/<user id>/`; without a
session, everything keeps using the single shared folder.

The user loader is swapped for an in-memory one so these tests never touch
MySQL: what is under test is where the data goes once Flask-Login says who
is logged in, not how the account itself is looked up."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from flask_login import UserMixin

from ancla.archive import repository as archivo
from ancla.profile import store
from ancla.profile.model import CVStatus, Proposal, SavedCV, SelectedAboutMe, SelectedExperience
from ancla.web import create_app
from ancla.web import settings as modulo_ajustes


class _Usuario(UserMixin):
    def __init__(self, id: int) -> None:
        self.id = id


@pytest.fixture
def app(tmp_path: Path):
    aplicacion = create_app(
        raiz_perfil=tmp_path / "perfil",
        settings_path=tmp_path / "ajustes.json",
        profiles_root=tmp_path / "perfiles",
        demo_mode=False,
        require_login=False,
    )
    aplicacion.config["TESTING"] = True
    aplicacion.login_manager.user_loader(lambda user_id: _Usuario(int(user_id)))
    return aplicacion


def _cliente(app, user_id: int | None = None):
    cliente = app.test_client()
    if user_id is not None:
        with cliente.session_transaction() as sesion:
            sesion["_user_id"] = str(user_id)
            sesion["_fresh"] = True
    return cliente


def _crear_skill(cliente, nombre: str) -> None:
    respuesta = cliente.post(
        "/perfil/skills-personales/nueva",
        data={"nombre_es": nombre, "nombre_en": nombre, "keywords": ""},
        follow_redirects=True,
    )
    assert respuesta.status_code == 200


def _perfil(cliente) -> str:
    return cliente.get("/perfil").data.decode("utf-8")


def _cv(id: str, empresa: str) -> SavedCV:
    return SavedCV(
        id=id,
        date=date(2026, 9, 13),
        company=empresa,
        position="Data Engineer",
        posting="Buscamos alguien con Python.",
        status=CVStatus.SENT,
        proposal=Proposal(
            language="es",
            about_me=SelectedAboutMe(group_a=[], group_b=[], text="", reason=""),
            skills=["python"],
            skills_reason="Requisito explícito.",
            experiences=[SelectedExperience(id="x", reason="Encaja.")],
        ),
    )


def test_dos_usuarios_a_la_vez_no_ven_el_perfil_del_otro(app, tmp_path: Path):
    ana, luis = _cliente(app, 1), _cliente(app, 2)

    _crear_skill(ana, "Negociación de Ana")
    _crear_skill(luis, "Liderazgo de Luis")

    assert "Negociación de Ana" in _perfil(ana)
    assert "Liderazgo de Luis" not in _perfil(ana)
    assert "Liderazgo de Luis" in _perfil(luis)
    assert "Negociación de Ana" not in _perfil(luis)
    assert (tmp_path / "perfiles" / "1").is_dir()
    assert (tmp_path / "perfiles" / "2").is_dir()
    # Nothing leaked into the shared, no-session folder either.
    assert not (tmp_path / "perfil").exists()


def test_un_usuario_no_puede_tocar_los_datos_del_otro(app, tmp_path: Path):
    ana, luis = _cliente(app, 1), _cliente(app, 2)
    _crear_skill(ana, "Negociación de Ana")
    raiz_ana = tmp_path / "perfiles" / "1"
    (skill_de_ana,) = store.load_profile(raiz_ana).personal_skills
    antes = store.load_profile(raiz_ana)

    # Even knowing the id, Luis's requests resolve against his own folder.
    luis.post(f"/perfil/skills-personales/{skill_de_ana.id}/borrar", follow_redirects=True)
    luis.post("/perfil/orden", json={"orden": ["idiomas", "skills"]})
    luis.post("/perfil/skills/borrar-todas", follow_redirects=True)

    assert store.load_profile(raiz_ana) == antes
    assert "Negociación de Ana" in _perfil(ana)


def test_dos_usuarios_a_la_vez_tienen_ajustes_aislados(app, tmp_path: Path):
    ana, luis = _cliente(app, 1), _cliente(app, 2)

    ana.post("/ajustes", data={"proveedor": "groq", "clave_api": "gsk_ana"}, follow_redirects=True)
    luis.post("/ajustes", data={"proveedor": "groq", "clave_api": "gsk_luis"}, follow_redirects=True)

    de_ana = modulo_ajustes.load_settings(tmp_path / "perfiles" / "1" / "ajustes.json")
    de_luis = modulo_ajustes.load_settings(tmp_path / "perfiles" / "2" / "ajustes.json")
    assert de_ana.clave_api == "gsk_ana"
    assert de_luis.clave_api == "gsk_luis"
    assert not (tmp_path / "ajustes.json").exists()


def test_el_idioma_de_la_interfaz_es_de_cada_usuario(app):
    ana, luis = _cliente(app, 1), _cliente(app, 2)
    ana.post("/ajustes", data={"proveedor": "groq", "clave_api": "", "idioma": "en"}, follow_redirects=True)

    assert 'lang="en"' in _perfil(ana)
    assert 'lang="es"' in _perfil(luis)


def test_el_archivo_de_cvs_es_de_cada_usuario(app, tmp_path: Path):
    archivo.save(tmp_path / "perfiles" / "1", _cv("cv-ana", "Empresa de Ana"))
    ana, luis = _cliente(app, 1), _cliente(app, 2)

    assert "Empresa de Ana" in ana.get("/cvs").data.decode("utf-8")
    assert "Empresa de Ana" not in luis.get("/cvs").data.decode("utf-8")
    assert ana.get("/cvs/cv-ana").status_code == 200
    ajeno = luis.get("/cvs/cv-ana", follow_redirects=True)
    assert "Empresa de Ana" not in ajeno.data.decode("utf-8")


def test_un_usuario_nuevo_ve_un_perfil_vacio_no_un_error(app, tmp_path: Path):
    _crear_skill(_cliente(app), "Skill de la carpeta compartida")

    respuesta = _cliente(app, 7).get("/perfil")

    assert respuesta.status_code == 200
    assert "Skill de la carpeta compartida" not in respuesta.data.decode("utf-8")
    assert _cliente(app, 7).get("/ajustes").status_code == 200


def test_sin_sesion_se_sigue_usando_la_carpeta_unica_de_siempre(app, tmp_path: Path):
    visitante = _cliente(app)
    _crear_skill(visitante, "Skill local")
    visitante.post("/ajustes", data={"proveedor": "groq", "clave_api": "gsk_local"}, follow_redirects=True)

    assert "Skill local" in _perfil(_cliente(app))
    assert (tmp_path / "perfil").is_dir()
    assert modulo_ajustes.load_settings(tmp_path / "ajustes.json").clave_api == "gsk_local"
    assert not (tmp_path / "perfiles").exists()
    # And a logged-in user does not see the shared local data.
    assert "Skill local" not in _perfil(_cliente(app, 1))


def test_al_cerrar_sesion_se_vuelve_a_la_carpeta_compartida(app):
    _crear_skill(_cliente(app), "Skill local")
    cliente = _cliente(app, 1)
    _crear_skill(cliente, "Skill de Ana")

    with cliente.session_transaction() as sesion:
        sesion.pop("_user_id")

    html = _perfil(cliente)
    assert "Skill local" in html
    assert "Skill de Ana" not in html


def test_en_modo_demo_una_sesion_no_cambia_de_carpeta(tmp_path: Path):
    """Demo visitors share the example profile by design; logging in there
    must not silently swap it for an empty per-account folder."""
    app = create_app(
        raiz_perfil=tmp_path / "perfil",
        settings_path=tmp_path / "ajustes.json",
        profiles_root=tmp_path / "perfiles",
        demo_mode=True,
        require_login=False,
    )
    app.config["TESTING"] = True
    app.login_manager.user_loader(lambda user_id: _Usuario(int(user_id)))

    _crear_skill(_cliente(app, 1), "Skill de la demo")

    assert "Skill de la demo" in _perfil(_cliente(app))
    assert not (tmp_path / "perfiles").exists()
