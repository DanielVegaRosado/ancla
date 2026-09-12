"""MySQL connection for user accounts.

Same environment variables as any MySQL client expects (`MYSQL_HOST`,
`MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE`), read from the
process environment or, failing that, from the `.env` file at the root of the
app. The `.env` is loaded lazily, on the first call, so importing this module
has no side effects and the rest of the app never touches it.
"""
from __future__ import annotations

import os
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
# A request to an unreachable server must fail in seconds, not hang the page:
# the account screens turn that failure into a "try again later" notice.
CONNECTION_TIMEOUT_SECONDS = 10


def mysql_settings() -> dict:
    # override=False: a variable already set in the environment (a hosting
    # platform's secrets, a test) always wins over the file.
    load_dotenv(ENV_FILE, override=False)
    return {
        "host": os.getenv("MYSQL_HOST", "localhost"),
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.getenv("MYSQL_USER"),
        "password": os.getenv("MYSQL_PASSWORD"),
        "database": os.getenv("MYSQL_DATABASE"),
    }


def mysql_configured() -> bool:
    """True when there are enough settings to even try connecting."""
    settings = mysql_settings()
    return bool(settings["user"] and settings["password"] and settings["database"])


def get_connection():
    return mysql.connector.connect(
        **mysql_settings(), connection_timeout=CONNECTION_TIMEOUT_SECONDS
    )
