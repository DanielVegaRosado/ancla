"""Account forms, without MySQL.

`tests/test_auth.py` covers accounts against the real database and is skipped
wherever there is none. What is checked here needs no database at all — a
rejected email never reaches the repository — so these run everywhere, which is
what keeps the Gmail-only rule and the shape of the forms verified in a
checkout with no `.env`.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from ancla.web import create_app


@pytest.fixture
def client(tmp_path: Path):
    app = create_app(raiz_perfil=tmp_path / "perfil", settings_path=tmp_path / "ajustes.json")
    app.config["TESTING"] = True
    return app.test_client()


def _form(email: str) -> dict:
    return {
        "first_name": "Ana", "last_name": "Pérez", "email": email,
        "password": "correcta123", "password2": "correcta123",
    }


@pytest.mark.parametrize("email", ["ana@example.com", "ana@gmail.es", "ana@notgmail.com", "ana"])
def test_registration_refuses_anything_but_a_gmail_address(client, email):
    response = client.post("/registro", data=_form(email))

    assert "solo se admiten correos de Gmail" in response.get_data(as_text=True)


def test_the_registration_form_asks_for_an_email_and_an_optional_phone(client):
    page = client.get("/registro").get_data(as_text=True)

    assert 'name="email"' in page
    assert 'name="phone_country"' in page
    assert 'name="phone_number"' in page
    assert 'name="username"' not in page


def test_the_registration_form_offers_a_country_dropdown_sorted_alphabetically(client):
    page = client.get("/registro").get_data(as_text=True)

    assert 'value="ES" selected' in page
    # "Alemania" (Germany) has to precede "España" (Spain) in the alphabetical order.
    assert page.index(">Alemania") < page.index(">España")


def test_the_login_form_asks_for_the_email(client):
    page = client.get("/login").get_data(as_text=True)

    assert 'name="email"' in page
    assert 'name="username"' not in page
