"""Outgoing email (SMTP with STARTTLS), used for account verification links.

Degraded mode: without SMTP credentials (`configured()` is False) nothing is
sent and `send()` returns False without raising. Callers decide what to do —
registration still creates the account. Credentials come only from the
environment (`ANCLA_SMTP_*`), never from the repository.
"""
from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage


def _smtp_settings() -> dict:
    user = os.getenv("ANCLA_SMTP_USER", "")
    return {
        "host": os.getenv("ANCLA_SMTP_HOST", "smtp.gmail.com"),
        "port": int(os.getenv("ANCLA_SMTP_PORT", "587")),
        "user": user,
        "password": os.getenv("ANCLA_SMTP_PASSWORD", ""),
        # The SMTP login is a technical credential and may differ from the
        # address the recipient should see as the sender.
        "sender": os.getenv("ANCLA_SMTP_REMITENTE", "") or user,
    }


def configured() -> bool:
    settings = _smtp_settings()
    return bool(settings["user"] and settings["password"])


def send(recipient: str, subject: str, body: str) -> bool:
    """Sends a plain-text email; True if the server accepted it.

    Never raises: any failure (credentials, network, mailbox) returns False,
    so a mail problem can never break a web request.
    """
    if not configured():
        return False
    settings = _smtp_settings()
    message = EmailMessage()
    message["From"] = settings["sender"]
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    try:
        with smtplib.SMTP(settings["host"], settings["port"], timeout=15) as smtp:
            smtp.starttls()
            smtp.login(settings["user"], settings["password"])
            smtp.send_message(message)
        return True
    except Exception:
        return False
