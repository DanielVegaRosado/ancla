"""User persistence in MySQL.

- Queries are always parameterized.
- `initialize()` creates the table idempotently, so it can run on every start.
- Passwords are stored only as a hash (werkzeug, pbkdf2-sha256), never in clear.
- `User` implements Flask-Login's interface, so it can be the session's
  authenticated user as is.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from ancla.auth.db import get_connection

ROLE_USER = "user"
ROLE_ADMIN = "admin"
PASSWORD_HASH_METHOD = "pbkdf2:sha256"
VERIFICATION_HOURS = 48

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS users (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    role                VARCHAR(16)  NOT NULL DEFAULT 'user',
    first_name          VARCHAR(100) NOT NULL,
    last_name           VARCHAR(200) NOT NULL,
    username            VARCHAR(100) NOT NULL UNIQUE,
    email               VARCHAR(190) NOT NULL UNIQUE,
    password_hash       VARCHAR(255) NOT NULL,
    email_verified      TINYINT(1)   NOT NULL DEFAULT 0,
    verification_token  VARCHAR(64)  NULL,
    token_expires       DATETIME     NULL,
    deleted             TINYINT(1)   NOT NULL DEFAULT 0,
    date_created        DATETIME     NOT NULL,
    date_modified       DATETIME     NOT NULL,
    INDEX idx_verification_token (verification_token)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
"""

_PUBLIC_COLUMNS = "id, role, first_name, last_name, username, email, deleted, email_verified"


class User(UserMixin):
    """An account's public data. The password hash never leaves the database:
    it is checked inside `UserRepository.authenticate()`."""

    def __init__(self, id: int, role: str, first_name: str, last_name: str,
                 username: str, email: str, deleted: bool = False,
                 email_verified: bool = True):
        self.id = id
        self.role = role
        self.first_name = first_name
        self.last_name = last_name
        self.username = username
        self.email = email
        self.deleted = deleted
        self.email_verified = email_verified

    def get_id(self) -> str:
        return str(self.id)

    @property
    def is_active(self) -> bool:
        # Soft delete: a deleted account can never log in.
        return not self.deleted

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN

    @classmethod
    def _from_row(cls, row) -> User:
        (uid, role, first_name, last_name, username, email, deleted, verified) = row
        return cls(uid, role, first_name, last_name, username, email,
                   bool(deleted), bool(verified))


class UserRepository:
    def __init__(self, connection_factory=get_connection):
        self._connect = connection_factory

    def available(self) -> bool:
        try:
            self._connect().close()
            return True
        except Exception:
            return False

    def initialize(self) -> None:
        conn = self._connect()
        try:
            conn.cursor().execute(CREATE_TABLE)
            conn.commit()
        finally:
            conn.close()

    # ── Writes ────────────────────────────────────────────────────────────────

    def create(self, first_name: str, last_name: str, username: str, email: str,
               password: str, role: str = ROLE_USER,
               email_verified: bool = True) -> int:
        """Creates an account and returns its id.

        `email_verified=False` creates it pending verification: the login
        route refuses it until the emailed link is opened.
        """
        now = datetime.now()
        password_hash = generate_password_hash(password, method=PASSWORD_HASH_METHOD)
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO users
                   (role, first_name, last_name, username, email, password_hash,
                    email_verified, deleted, date_created, date_modified)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, 0, %s, %s)""",
                (role, first_name, last_name, username, email, password_hash,
                 int(bool(email_verified)), now, now),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    # ── Email verification ────────────────────────────────────────────────────

    def generate_verification_token(self, email: str,
                                    hours_valid: int = VERIFICATION_HOURS) -> str | None:
        """Generates (or renews) the verification token of the account with
        that email, for the link sent to it.

        Returns None both when there is no such account and when it is already
        verified, without saying which: callers must answer the same in both
        cases, or the form becomes a way to find out which emails exist.
        """
        token = secrets.token_urlsafe(32)
        now = datetime.now()
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """UPDATE users
                   SET verification_token = %s, token_expires = %s, date_modified = %s
                   WHERE email = %s AND email_verified = 0 AND deleted = 0""",
                (token, now + timedelta(hours=hours_valid), now, email),
            )
            conn.commit()
            return token if cur.rowcount else None
        finally:
            conn.close()

    def verify_by_token(self, token: str) -> bool:
        """Marks the account verified if the token exists and has not expired.

        Single use: the token is cleared on success, so the same link cannot
        verify twice. False if it does not exist, was used, or expired.
        """
        if not token:
            return False
        now = datetime.now()
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """UPDATE users
                   SET email_verified = 1, verification_token = NULL,
                       token_expires = NULL, date_modified = %s
                   WHERE verification_token = %s AND token_expires >= %s
                     AND deleted = 0""",
                (now, token, now),
            )
            conn.commit()
            return bool(cur.rowcount)
        finally:
            conn.close()

    # ── Reads ─────────────────────────────────────────────────────────────────

    def username_exists(self, username: str) -> bool:
        return self._exists("username", username)

    def email_exists(self, email: str) -> bool:
        return self._exists("email", email)

    def _exists(self, column: str, value: str) -> bool:
        # `column` is never user input: only "username" or "email" above.
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(f"SELECT 1 FROM users WHERE {column} = %s LIMIT 1", (value,))
            return cur.fetchone() is not None
        finally:
            conn.close()

    def by_id(self, id: int) -> User | None:
        """Loads an account by id — what Flask-Login calls on every request."""
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(f"SELECT {_PUBLIC_COLUMNS} FROM users WHERE id = %s", (id,))
            row = cur.fetchone()
        finally:
            conn.close()
        return User._from_row(row) if row else None

    def authenticate(self, username: str, password: str) -> User | None:
        """The account if the credentials are right and it is not deleted;
        None otherwise.

        An unverified account is still returned, with `email_verified=False`:
        refusing it is the login route's decision, so it can say why instead
        of pretending the password was wrong.
        """
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                f"SELECT {_PUBLIC_COLUMNS}, password_hash FROM users WHERE username = %s",
                (username,),
            )
            row = cur.fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        *public, password_hash = row
        user = User._from_row(public)
        if user.deleted or not check_password_hash(password_hash, password):
            return None
        return user
