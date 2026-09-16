"""The login gate (`create_app(require_login=True)`, the default everywhere):
nothing but the account screens is reachable without a session. The same app
built with the explicit `require_login=False` opt-out — what the tests aimed
at one screen use — keeps working with no account at all.

The user loader is swapped for an in-memory one so these tests never touch
MySQL: what is under test is the gate, not how an account is looked up."""
from __future__ import annotations

from pathlib import Path

import pytest
from flask_login import UserMixin

from ancla.web import create_app

GATED_PATHS = ["/perfil", "/adaptar", "/propuesta", "/cvs", "/plantillas", "/ajustes", "/soporte"]
OPEN_PATHS = ["/login", "/registro", "/reenviar-verificacion", "/terminos"]
# "/propuesta" redirects to "Adaptar" whenever there is no draft yet, which is
# the case in these tests: it can only be checked for where the gate sends it.
RENDERED_PATHS = [ruta for ruta in GATED_PATHS if ruta != "/propuesta"]


class _Usuario(UserMixin):
    def __init__(self, id: int) -> None:
        self.id = id


def _app(tmp_path: Path, *, require_login: bool):
    aplicacion = create_app(
        raiz_perfil=tmp_path / "perfil",
        settings_path=tmp_path / "ajustes.json",
        profiles_root=tmp_path / "perfiles",
        demo_mode=False,
        require_login=require_login,
    )
    aplicacion.config["TESTING"] = True
    aplicacion.login_manager.user_loader(lambda user_id: _Usuario(int(user_id)))
    return aplicacion


@pytest.fixture
def app_con_gate(tmp_path: Path):
    return _app(tmp_path, require_login=True)


@pytest.fixture
def app_sin_gate(tmp_path: Path):
    return _app(tmp_path, require_login=False)


def _cliente(app, user_id: int | None = None):
    cliente = app.test_client()
    if user_id is not None:
        with cliente.session_transaction() as sesion:
            sesion["_user_id"] = str(user_id)
            sesion["_fresh"] = True
    return cliente


@pytest.mark.parametrize("ruta", GATED_PATHS)
def test_sin_sesion_toda_pantalla_lleva_al_login(app_con_gate, ruta):
    respuesta = _cliente(app_con_gate).get(ruta)

    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith("/login")


@pytest.mark.parametrize("ruta", OPEN_PATHS)
def test_las_pantallas_de_cuenta_siguen_abiertas(app_con_gate, ruta):
    assert _cliente(app_con_gate).get(ruta).status_code == 200


def test_una_ruta_inexistente_tambien_lleva_al_login(app_con_gate):
    """Without a session there is nothing to show, not even the 404 screen,
    which extends base.html and links to every gated screen."""
    respuesta = _cliente(app_con_gate).get("/no-existe")

    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith("/login")


@pytest.mark.parametrize("ruta", RENDERED_PATHS)
def test_con_sesion_se_ve_la_app_entera(app_con_gate, ruta):
    assert _cliente(app_con_gate, user_id=7).get(ruta).status_code == 200


@pytest.mark.parametrize("ruta", RENDERED_PATHS)
def test_el_opt_out_explicito_sigue_abriendo_toda_la_app(app_sin_gate, ruta):
    """`require_login=False` is the only way left to reach a screen without an
    account, and the tests aimed at one screen depend on it still working."""
    assert _cliente(app_sin_gate).get(ruta).status_code == 200


def test_el_gate_es_el_comportamiento_por_defecto(tmp_path: Path):
    """`create_app()` with no arguments is what `run.py` and the Dockerfile
    use: the gate has to be on unless someone explicitly opts out."""
    aplicacion = create_app(
        raiz_perfil=tmp_path / "perfil",
        settings_path=tmp_path / "ajustes.json",
        demo_mode=False,
    )

    assert aplicacion.config["REQUIERE_SESION"] is True


def test_sin_sesion_la_cabecera_no_enlaza_a_las_pantallas_cerradas(app_con_gate):
    html = _cliente(app_con_gate).get("/login").data.decode("utf-8")

    assert "/adaptar" not in html
    assert "/perfil" not in html


def test_sin_base_de_datos_avisa_en_vez_de_fallar(app_con_gate, monkeypatch):
    """Missing MySQL must not stop the desktop app from starting: it opens on
    the login screen with a clear notice, not on a raw error."""
    import ancla.auth.db

    monkeypatch.setattr(ancla.auth.db, "mysql_configured", lambda: False)
    aplicacion = _app(Path(app_con_gate.config["RAIZ_PERFIL"]).parent, require_login=True)

    respuesta = _cliente(aplicacion).get("/login")

    assert respuesta.status_code == 200
    assert "base de datos de cuentas" in respuesta.data.decode("utf-8")
