"""Account screens: register, log in, log out, and the verification link.

They run alongside the rest of the app without gating it: no existing route
requires a login. Every database call is wrapped so that an unreachable or
unconfigured MySQL shows a notice instead of an error page — the rest of the
app keeps working without it.

Email verification follows `ANCLA_VERIFICACION_EMAIL`: "auto" (default) turns
it on only when SMTP is configured, "on" always, "off" never. With it off,
accounts are created already verified, since nobody could ever receive the
link.

"Continue with Google" (OpenID Connect through Authlib) is an alternative way
into the same accounts: the account is its Gmail address, whichever way it
arrives. It is offered only when `GOOGLE_CLIENT_ID` and
`GOOGLE_CLIENT_SECRET` are set.
"""
from __future__ import annotations

import os
import re

from authlib.integrations.base_client import OAuthError
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv
from flask import current_app, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _
from flask_login import current_user, login_user, logout_user

from ancla.auth import mail
from ancla.auth.db import ENV_FILE
from ancla.auth.users import VERIFICATION_HOURS, PasswordlessAccount, UserRepository
from ancla.web.blueprint import bp
from ancla.web.countries import COUNTRIES, DEFAULT_COUNTRY_ISO, dial_code_for

MIN_PASSWORD_LENGTH = 8
# The account is identified by its email, and only Gmail addresses are
# accepted: the later social login is Google-first, so an account created here
# must be the same account that arrives through it.
_EMAIL_SHAPE = re.compile(r"^[^@\s]+@gmail\.com$")
# The local part the user types next to the country dropdown: digits only,
# no leading zero (that belongs to national dialing, not the E.164 number).
_PHONE_NUMBER_SHAPE = re.compile(r"^[1-9]\d{5,13}$")
GOOGLE_METADATA_URL = "https://accounts.google.com/.well-known/openid-configuration"


def _register_form_context(form: dict, errors: dict) -> dict:
    return {"form": form, "errors": errors, "countries": COUNTRIES,
            "default_country": DEFAULT_COUNTRY_ISO}


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


def google_configured() -> bool:
    load_dotenv(ENV_FILE, override=False)
    return bool(os.getenv("GOOGLE_CLIENT_ID") and os.getenv("GOOGLE_CLIENT_SECRET"))


def _google():
    """The app's Google client, registered the first time it is needed, like
    `users()`, so the app starts the same with or without credentials."""
    oauth = current_app.extensions.get("authlib.integrations.flask_client")
    if oauth is None:
        oauth = OAuth(current_app)
        oauth.register(
            "google",
            client_id=os.getenv("GOOGLE_CLIENT_ID"),
            client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
            server_metadata_url=GOOGLE_METADATA_URL,
            client_kwargs={"scope": "openid email profile"},
        )
    return oauth.google


@bp.app_context_processor
def _google_login_offered() -> dict:
    return {"google_login": google_configured()}


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
    if not _EMAIL_SHAPE.match(form["email"]):
        errors["email"] = _("De momento solo se admiten correos de Gmail (@gmail.com).")
    if form["phone_number"]:
        if dial_code_for(form["phone_country"]) is None:
            errors["phone_number"] = _("Elige un país de la lista.")
        elif not _PHONE_NUMBER_SHAPE.match(form["phone_number"]):
            errors["phone_number"] = _("Escribe el número sin el prefijo, solo dígitos.")
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
        return render_template("register.html", **_register_form_context({}, {}))

    form = {
        "first_name": request.form.get("first_name", "").strip(),
        "last_name": request.form.get("last_name", "").strip(),
        "email": request.form.get("email", "").strip().lower(),
        "phone_country": request.form.get("phone_country", "").strip(),
        # Spaces are how people naturally group digits ("600 111 222"), so
        # collapse them instead of asking the user to type it a way nobody
        # actually would.
        "phone_number": re.sub(r"\s+", "", request.form.get("phone_number", "")),
        "password": request.form.get("password", ""),
        "password2": request.form.get("password2", ""),
    }
    errors = _registration_errors(form)
    try:
        if "email" not in errors and users().email_exists(form["email"]):
            errors["email"] = _("Ya hay una cuenta con ese correo.")
        if errors:
            return render_template("register.html", **_register_form_context(form, errors))
        verify = verification_active()
        phone = None
        if form["phone_number"]:
            phone = dial_code_for(form["phone_country"]) + form["phone_number"]
        users().create(
            form["first_name"], form["last_name"], form["email"], form["password"],
            phone=phone, email_verified=not verify,
        )
        if not verify:
            flash(_("Cuenta creada. Ya puedes iniciar sesión."))
        elif _send_verification_email(form["email"]):
            flash(_("Cuenta creada. Te hemos enviado un correo: abre el enlace para activarla."))
        else:
            flash(_("Cuenta creada, pero no hemos podido enviar el correo de verificación."))
    except Exception:
        _database_unavailable()
        return render_template("register.html", **_register_form_context(form, errors))
    return redirect(url_for("ancla.login"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("ancla.view_profile"))
    if request.method == "GET":
        return render_template("login.html", email="")

    email = request.form.get("email", "").strip().lower()
    try:
        user = users().authenticate(email, request.form.get("password", ""))
    except PasswordlessAccount:
        flash(_("Esta cuenta se creó con Google: entra con «Continuar con Google»."))
        return render_template("login.html", email=email)
    except Exception:
        _database_unavailable()
        return render_template("login.html", email=email)
    if user is None:
        flash(_("Correo o contraseña incorrectos."))
    elif verification_active() and not user.email_verified:
        flash(_("Tu cuenta aún no está verificada. Abre el enlace que te enviamos por correo."))
        return render_template("login.html", email=email, offer_resend=True)
    else:
        login_user(user)
        return redirect(url_for("ancla.view_profile"))
    return render_template("login.html", email=email)


@bp.route("/login/google")
def login_google():
    if current_user.is_authenticated:
        return redirect(url_for("ancla.view_profile"))
    if not google_configured():
        flash(_("El acceso con Google no está configurado en esta copia de la app."))
        return redirect(url_for("ancla.login"))
    return _google().authorize_redirect(_public_link("ancla.login_google_callback"))


def _google_identity() -> dict | None:
    """The verified profile Google sent back, or None if the round trip failed
    (the user cancelled, the state did not match, the token was invalid).
    Authlib validates the ID token's signature, audience and nonce."""
    try:
        token = _google().authorize_access_token()
    except OAuthError:
        return None
    return token.get("userinfo")


@bp.route("/login/google/callback")
def login_google_callback():
    if not google_configured():
        return redirect(url_for("ancla.login"))
    identity = _google_identity()
    if identity is None:
        flash(_("No se pudo completar el acceso con Google. Inténtalo de nuevo."))
        return redirect(url_for("ancla.login"))
    email = (identity.get("email") or "").strip().lower()
    if not identity.get("email_verified") or not _EMAIL_SHAPE.match(email):
        flash(_("De momento solo se admiten cuentas de Gmail (@gmail.com)."))
        return redirect(url_for("ancla.login"))
    try:
        user = users().by_email(email)
        if user is None:
            users().create(
                identity.get("given_name") or email.split("@")[0],
                identity.get("family_name") or "",
                email, None, email_verified=True,
            )
            user = users().by_email(email)
        elif not user.email_verified:
            users().confirm_email_through_google(user.id)
    except Exception:
        _database_unavailable()
        return redirect(url_for("ancla.login"))
    if not login_user(user):
        flash(_("Esta cuenta está dada de baja."))
        return redirect(url_for("ancla.login"))
    return redirect(url_for("ancla.view_profile"))


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
