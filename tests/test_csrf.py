"""Proves CSRF protection is actually active, without the suite-wide bypass
`conftest.py` installs for every other test (`_csrf_disabled_for_tests` — see
its docstring). Overriding that fixture to a no-op here means this is the one
file where `create_app()` runs with `CSRFProtect` doing real work.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from ancla.web import create_app


@pytest.fixture(autouse=True)
def _csrf_disabled_for_tests() -> None:
    """No-op override of the conftest fixture of the same name: this file
    exists specifically to test what that fixture bypasses elsewhere."""


@pytest.fixture
def cliente_web(tmp_path: Path):
    app = create_app(raiz_perfil=tmp_path / "perfil", settings_path=tmp_path / "ajustes.json")
    with app.test_client() as cliente:
        yield cliente


def test_un_post_sin_token_csrf_no_se_procesa(cliente_web):
    respuesta = cliente_web.post("/login", data={"email": "a@example.com", "password": "x"})
    # Rejected before reaching the login view: a redirect back with a flash
    # (see the CSRFError handler in ancla/web/__init__.py). The login view
    # itself never redirects on a plain POST (right, wrong, or unreachable
    # database all re-render login.html — see views/auth.py::login), so a
    # 302 here can only mean CSRFProtect stepped in first.
    assert respuesta.status_code == 302


def test_un_post_con_el_token_csrf_de_la_pagina_se_procesa(cliente_web):
    formulario = cliente_web.get("/login").get_data(as_text=True)
    inicio = formulario.index('name="csrf_token" value="') + len('name="csrf_token" value="')
    token = formulario[inicio : formulario.index('"', inicio)]

    respuesta = cliente_web.post(
        "/login",
        data={"email": "a@example.com", "password": "x", "csrf_token": token},
    )
    # A valid token reaches the login view, which always answers 200 on a
    # plain POST (see views/auth.py::login) — the CSRFError redirect from
    # the previous test is what a rejected request looks like instead.
    assert respuesta.status_code == 200
