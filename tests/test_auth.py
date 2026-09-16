"""Accounts against the real MySQL database in `.env` — no mocks.

Every account a test creates gets an email starting with a per-run prefix, and
the fixture deletes exactly those rows afterwards, so the suite leaves the
shared database as it found it. Skipped when no MySQL is configured (a
checkout without `.env`), since there is nothing real to test against.
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from ancla.auth.db import get_connection, mysql_configured
from ancla.auth.users import UserRepository
from ancla.web import create_app

pytestmark = pytest.mark.skipif(not mysql_configured(), reason="MySQL not configured in .env")

RUN_PREFIX = f"pytest-{uuid.uuid4().hex[:8]}-"
PASSWORD = "correcta123"


@pytest.fixture(scope="module")
def repository() -> UserRepository:
    repository = UserRepository()
    repository.initialize()
    yield repository
    conn = get_connection()
    try:
        conn.cursor().execute("DELETE FROM users WHERE email LIKE %s", (RUN_PREFIX + "%",))
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def new_account():
    """Unique email for one account, so tests never collide with each other or
    with a real user. Gmail because registration accepts nothing else."""
    suffix = uuid.uuid4().hex[:10]
    return {"email": f"{RUN_PREFIX}{suffix}@gmail.com"}


def _create(repository: UserRepository, account: dict, *, verified: bool) -> int:
    return repository.create(
        "Ana", "Pérez", account["email"], PASSWORD, email_verified=verified,
    )


@pytest.fixture
def client(tmp_path: Path, repository: UserRepository, monkeypatch: pytest.MonkeyPatch):
    # Verification on, whatever SMTP there is: that is the mode in which an
    # unverified account must be refused. With no SMTP configured the
    # registration still succeeds and just reports that the email did not go.
    monkeypatch.setenv("ANCLA_VERIFICACION_EMAIL", "on")
    monkeypatch.delenv("ANCLA_SMTP_USER", raising=False)
    monkeypatch.delenv("ANCLA_SMTP_PASSWORD", raising=False)
    app = create_app(raiz_perfil=tmp_path / "perfil", settings_path=tmp_path / "ajustes.json")
    app.config["TESTING"] = True
    return app.test_client()


def _logged_in_id(client) -> str | None:
    with client.session_transaction() as session:
        return session.get("_user_id")


def _register_form(account: dict, **overrides) -> dict:
    form = {
        "first_name": "Ana", "last_name": "Pérez", "email": account["email"],
        "password": PASSWORD, "password2": PASSWORD,
    }
    form.update(overrides)
    return form


# ── Repository ────────────────────────────────────────────────────────────────

def test_create_stores_a_hash_and_loads_by_id(repository, new_account):
    user_id = _create(repository, new_account, verified=True)

    user = repository.by_id(user_id)
    assert user.email == new_account["email"]
    assert user.get_id() == str(user_id)
    assert user.is_active and user.email_verified
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT password_hash FROM users WHERE id = %s", (user_id,))
        stored = cur.fetchone()[0]
    finally:
        conn.close()
    assert stored.startswith("pbkdf2:sha256:")
    assert PASSWORD not in stored


def test_by_id_of_a_missing_account_is_none(repository):
    assert repository.by_id(-1) is None


def test_authenticate_with_right_and_wrong_password(repository, new_account):
    _create(repository, new_account, verified=True)

    assert repository.authenticate(new_account["email"], PASSWORD).email == new_account["email"]
    assert repository.authenticate(new_account["email"], "incorrecta123") is None
    assert repository.authenticate(RUN_PREFIX + "nobody@gmail.com", PASSWORD) is None


def test_verification_token_is_single_use(repository, new_account):
    _create(repository, new_account, verified=False)
    assert repository.authenticate(new_account["email"], PASSWORD).email_verified is False

    token = repository.generate_verification_token(new_account["email"])

    assert token
    assert repository.verify_by_token(token) is True
    assert repository.authenticate(new_account["email"], PASSWORD).email_verified is True
    assert repository.verify_by_token(token) is False


def test_no_token_for_an_already_verified_or_unknown_account(repository, new_account):
    _create(repository, new_account, verified=True)

    assert repository.generate_verification_token(new_account["email"]) is None
    assert repository.generate_verification_token(RUN_PREFIX + "nobody@gmail.com") is None


def test_an_expired_token_does_not_verify(repository, new_account):
    _create(repository, new_account, verified=False)

    token = repository.generate_verification_token(new_account["email"], hours_valid=-1)

    assert repository.verify_by_token(token) is False
    assert repository.verify_by_token("") is False


# ── Web ───────────────────────────────────────────────────────────────────────

def test_register_creates_an_unverified_account_and_stores_the_optional_phone(
    client, repository, new_account
):
    response = client.post(
        "/registro",
        data=_register_form(new_account, phone_country="ES", phone_number="600111222"),
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
    user = repository.authenticate(new_account["email"], PASSWORD)
    assert user is not None and user.email_verified is False
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT phone FROM users WHERE email = %s", (new_account["email"],))
        assert cur.fetchone()[0] == "+34600111222"
    finally:
        conn.close()


def test_register_strips_spaces_the_user_typed_inside_the_phone_number(
    client, repository, new_account
):
    client.post(
        "/registro",
        data=_register_form(new_account, phone_country="ES", phone_number="600 111 222"),
    )

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT phone FROM users WHERE email = %s", (new_account["email"],))
        assert cur.fetchone()[0] == "+34600111222"
    finally:
        conn.close()


def test_register_without_a_phone_stores_null(client, repository, new_account):
    client.post("/registro", data=_register_form(new_account))

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT phone FROM users WHERE email = %s", (new_account["email"],))
        assert cur.fetchone()[0] is None
    finally:
        conn.close()


def test_register_rejects_a_non_gmail_address(client, repository, new_account):
    outside = "x" + new_account["email"].replace("@gmail.com", "@example.com")

    response = client.post("/registro", data=_register_form(new_account, email=outside))

    assert "solo se admiten correos de Gmail" in response.get_data(as_text=True)
    assert not repository.email_exists(outside)


def test_register_rejects_a_taken_email_and_mismatched_passwords(client, repository, new_account):
    _create(repository, new_account, verified=True)
    free = {"email": "x" + new_account["email"]}

    taken = client.post("/registro", data=_register_form(new_account))
    mismatch = client.post("/registro", data=_register_form(free, password2="otra123456"))

    assert "Ya hay una cuenta con ese correo." in taken.get_data(as_text=True)
    assert "Las contraseñas no coinciden." in mismatch.get_data(as_text=True)
    assert not repository.email_exists(free["email"])


def test_login_with_right_password_logs_in_and_wrong_one_does_not(client, repository, new_account):
    _create(repository, new_account, verified=True)

    wrong = client.post("/login", data={"email": new_account["email"], "password": "incorrecta123"})
    assert "Correo o contraseña incorrectos." in wrong.get_data(as_text=True)
    assert _logged_in_id(client) is None

    right = client.post("/login", data={"email": new_account["email"], "password": PASSWORD})
    assert right.status_code == 302
    assert _logged_in_id(client) is not None

    client.get("/logout")
    assert _logged_in_id(client) is None


def test_unverified_account_cannot_log_in_until_the_link_is_opened(client, repository, new_account):
    client.post("/registro", data=_register_form(new_account))

    refused = client.post("/login", data={"email": new_account["email"], "password": PASSWORD})
    assert "aún no está verificada" in refused.get_data(as_text=True)
    assert _logged_in_id(client) is None

    token = repository.generate_verification_token(new_account["email"])
    client.get(f"/verificar/{token}")
    client.post("/login", data={"email": new_account["email"], "password": PASSWORD})
    assert _logged_in_id(client) is not None


def test_existing_screens_now_require_logging_in(client):
    """The gate is on by default everywhere (see `tests/test_login_gate.py`);
    checked here too because this client is built the way the real app is,
    with the MySQL-backed user loader rather than an in-memory stand-in."""
    response = client.get("/ajustes")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
