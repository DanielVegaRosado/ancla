"""Account screens: register, log in, log out, and the verification link.

They run alongside the rest of the app without gating it: no existing route
requires a login. Every database call is wrapped so that an unreachable or
unconfigured MySQL shows a notice instead of an error page — the rest of the
app keeps working without it.

Email verification follows `ANCLA_VERIFICACION_EMAIL`: "auto" (default) turns
it on only when SMTP is configured, "on" always, "off" never. With it off,
accounts are created already verified, since nobody could ever receive the
link.
"""
from __future__ import annotations

import os
import re

from flask import current_app, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _
from flask_login import current_user, login_user, logout_user

from ancla.auth import mail
from ancla.auth.users import VERIFICATION_HOURS, UserRepository
from ancla.web.blueprint import bp

MIN_PASSWORD_LENGTH = 8
MIN_USERNAME_LENGTH = 3
# Deliberately loose — no domain restriction, just the shape of an address.
# Whether it really exists is what the verification link proves.
_EMAIL_SHAPE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def verification_active() -> bool:
    mode = os.getenv("ANCLA_VERIFICACION_EMAIL", "auto")
    return mode == "on" or (mode == "auto" and mail.configured())


def users() -> UserRepository:
    """The app's repository, creating the table the first time it is needed
    rather than at startup, so starting the app never requires MySQL."""
    repository = current_app.extensions.get("ancla_users")
    if repository is None:
        repository = UserRepository()
        repository.initialize()
        current_app.extensions["ancla_users"] = repository
    return repository


def _database_unavailable() -> None:
    flash(_("No se puede conectar con la base de datos de cuentas. Inténtalo más tarde."))


def _public_link(endpoint: str, **values) -> str:
    """Absolute URL for links that travel by email. Without
    `ANCLA_URL_PUBLICA` it falls back to the request's host, which is only
    right when the app is reached at the same address the recipient will use."""
    base = os.getenv("ANCLA_URL_PUBLICA", "").rstrip("/")
    if base:
        return base + url_for(endpoint, **values)
    return url_for(endpoint, _external=True, **values)


def _send_verification_email(email: str) -> bool:
    token = users().generate_verification_token(email, VERIFICATION_HOURS)
    if not token:
        return False
    link = _public_link("ancla.verify_email", token=token)
    body = _(
        "Hola:\n\nGracias por registrarte en Ancla. Para activar tu cuenta, abre "
        "este enlace (caduca en %(horas)s horas):\n\n%(enlace)s\n\n"
        "Si no has creado esta cuenta, ignora este mensaje.",
        horas=VERIFICATION_HOURS,
        enlace=link,
    )
    return mail.send(email, _("Ancla — Verifica tu cuenta"), body)


def _registration_errors(form: dict) -> dict[str, str]:
    errors = {}
    if not form["first_name"]:
        errors["first_name"] = _("Escribe tu nombre.")
    if not form["last_name"]:
        errors["last_name"] = _("Escribe tus apellidos.")
    if len(form["username"]) < MIN_USERNAME_LENGTH:
        errors["username"] = _(
            "El nombre de usuario debe tener al menos %(n)s caracteres.", n=MIN_USERNAME_LENGTH
        )
    if not _EMAIL_SHAPE.match(form["email"]):
        errors["email"] = _("Escribe un correo válido.")
    password = form["password"]
    if len(password) < MIN_PASSWORD_LENGTH:
        errors["password"] = _(
            "La contraseña debe tener al menos %(n)s caracteres.", n=MIN_PASSWORD_LENGTH
        )
    elif not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        errors["password"] = _("La contraseña debe incluir al menos una letra y un número.")
    elif password != form["password2"]:
        errors["password2"] = _("Las contraseñas no coinciden.")
    return errors


@bp.route("/registro", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("ancla.view_profile"))
    if request.method == "GET":
        return render_template("register.html", form={}, errors={})

    form = {
        "first_name": request.form.get("first_name", "").strip(),
        "last_name": request.form.get("last_name", "").strip(),
        "username": request.form.get("username", "").strip(),
        "email": request.form.get("email", "").strip().lower(),
        "password": request.form.get("password", ""),
        "password2": request.form.get("password2", ""),
    }
    errors = _registration_errors(form)
    try:
        if "username" not in errors and users().username_exists(form["username"]):
            errors["username"] = _("Ese nombre de usuario ya está cogido.")
        if "email" not in errors and users().email_exists(form["email"]):
            errors["email"] = _("Ya hay una cuenta con ese correo.")
        if errors:
            return render_template("register.html", form=form, errors=errors)
        verify = verification_active()
        users().create(
            form["first_name"], form["last_name"], form["username"], form["email"],
            form["password"], email_verified=not verify,
        )
        if not verify:
            flash(_("Cuenta creada. Ya puedes iniciar sesión."))
        elif _send_verification_email(form["email"]):
            flash(_("Cuenta creada. Te hemos enviado un correo: abre el enlace para activarla."))
        else:
            flash(_("Cuenta creada, pero no hemos podido enviar el correo de verificación."))
    except Exception:
        _database_unavailable()
        return render_template("register.html", form=form, errors=errors)
    return redirect(url_for("ancla.login"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("ancla.view_profile"))
    if request.method == "GET":
        return render_template("login.html", username="")

    username = request.form.get("username", "").strip()
    try:
        user = users().authenticate(username, request.form.get("password", ""))
    except Exception:
        _database_unavailable()
        return render_template("login.html", username=username)
    if user is None:
        flash(_("Usuario o contraseña incorrectos."))
    elif verification_active() and not user.email_verified:
        flash(_("Tu cuenta aún no está verificada. Abre el enlace que te enviamos por correo."))
        return render_template("login.html", username=username, offer_resend=True)
    else:
        login_user(user)
        return redirect(url_for("ancla.view_profile"))
    return render_template("login.html", username=username)


@bp.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("ancla.login"))


@bp.route("/verificar/<token>")
def verify_email(token: str):
    try:
        verified = users().verify_by_token(token)
    except Exception:
        _database_unavailable()
        return redirect(url_for("ancla.login"))
    if verified:
        flash(_("¡Cuenta verificada! Ya puedes iniciar sesión."))
    else:
        flash(_("Este enlace de verificación no es válido o ha caducado. Puedes pedir uno nuevo."))
        return redirect(url_for("ancla.resend_verification"))
    return redirect(url_for("ancla.login"))


@bp.route("/reenviar-verificacion", methods=["GET", "POST"])
def resend_verification():
    """Always answers the same, whether the account exists, is already
    verified, or the database failed: otherwise this form would reveal which
    emails are registered."""
    if request.method == "GET":
        return render_template("resend_verification.html")
    try:
        _send_verification_email(request.form.get("email", "").strip().lower())
    except Exception:
        pass
    flash(_("Si hay una cuenta pendiente de verificar con ese correo, le hemos enviado un enlace nuevo."))
    return redirect(url_for("ancla.login"))
