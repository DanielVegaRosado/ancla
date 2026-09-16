"""The login gate of the desktop build (`create_app(require_login=True)`):
nothing but the account screens is reachable without a session, while the
same app built the usual way (the web) keeps working with no account at all.

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
def app_escritorio(tmp_path: Path):
    return _app(tmp_path, require_login=True)


@pytest.fixture
def app_web(tmp_path: Path):
    return _app(tmp_path, require_login=False)


def _cliente(app, user_id: int | None = None):
    cliente = app.test_client()
    if user_id is not None:
        with cliente.session_transaction() as sesion:
            sesion["_user_id"] = str(user_id)
            sesion["_fresh"] = True
    return cliente


@pytest.mark.parametrize("ruta", GATED_PATHS)
def test_sin_sesion_toda_pantalla_lleva_al_login(app_escritorio, ruta):
    respuesta = _cliente(app_escritorio).get(ruta)

    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith("/login")


@pytest.mark.parametrize("ruta", OPEN_PATHS)
def test_las_pantallas_de_cuenta_siguen_abiertas(app_escritorio, ruta):
    assert _cliente(app_escritorio).get(ruta).status_code == 200


def test_una_ruta_inexistente_tambien_lleva_al_login(app_escritorio):
    """Without a session there is nothing to show, not even the 404 screen,
    which extends base.html and links to every gated screen."""
    respuesta = _cliente(app_escritorio).get("/no-existe")

    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith("/login")


@pytest.mark.parametrize("ruta", RENDERED_PATHS)
def test_con_sesion_se_ve_la_app_entera(app_escritorio, ruta):
    assert _cliente(app_escritorio, user_id=7).get(ruta).status_code == 200


@pytest.mark.parametrize("ruta", RENDERED_PATHS)
def test_la_web_sigue_funcionando_sin_cuenta(app_web, ruta):
    assert _cliente(app_web).get(ruta).status_code == 200


def test_la_web_es_el_comportamiento_por_defecto(tmp_path: Path):
    """`create_app()` with no arguments is what `run.py`, the Dockerfile and
    the tests use: the gate has to stay off unless it is asked for."""
    aplicacion = create_app(
        raiz_perfil=tmp_path / "perfil",
        settings_path=tmp_path / "ajustes.json",
        demo_mode=False,
    )

    assert aplicacion.config["REQUIERE_SESION"] is False


def test_sin_sesion_la_cabecera_no_enlaza_a_las_pantallas_cerradas(app_escritorio):
    html = _cliente(app_escritorio).get("/login").data.decode("utf-8")

    assert "/adaptar" not in html
    assert "/perfil" not in html


def test_sin_base_de_datos_avisa_en_vez_de_fallar(app_escritorio, monkeypatch):
    """Missing MySQL must not stop the desktop app from starting: it opens on
    the login screen with a clear notice, not on a raw error."""
    import ancla.auth.db

    monkeypatch.setattr(ancla.auth.db, "mysql_configured", lambda: False)
    aplicacion = _app(Path(app_escritorio.config["RAIZ_PERFIL"]).parent, require_login=True)

    respuesta = _cliente(aplicacion).get("/login")

    assert respuesta.status_code == 200
    assert "base de datos de cuentas" in respuesta.data.decode("utf-8")
