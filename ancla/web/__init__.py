"""Web interface: Flask + plain HTML/CSS/JS, no external dependencies or CDN.

Five screens: My profile, Adapt, Proposal, My CVs, and Settings. Bilingual
ES/EN interface (manual selector in the header, no auto-detection — see
`ajustes.idioma`). User accounts (`ancla/auth/`, screens in
`views/auth.py`) gate every screen, everywhere the app runs: a local
browser, the hosted demo and the desktop build all start on the account
screens, and nothing else is reachable until there is a session. Once
logged in, each account works on its own folder under `perfiles/` (see
`context.root()`). Building the app with `require_login=False` lifts the
gate onto the single shared local profile — a deliberate opt-out, used by
the tests that are checking one screen rather than the gate.

Each screen is a module under `ancla/web/views/`, with its routes
registered on the single `Blueprint` in `ancla/web/blueprint.py`. This
factory only assembles the app: configuration, template filters, and error
handling — it knows nothing about any particular screen.
"""
from __future__ import annotations

import logging
import os
import secrets
from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, url_for
from flask_babel import Babel, get_locale
from flask_babel import gettext as _
from flask_login import LoginManager, current_user

from ancla.web.routes import (
    PROFILE_DIR_NAME,
    PROFILES_DIR_NAME,
    data_root,
    templates_root,
)

# Signs session cookies. Left unset, a single local process still works
# (see `_secret_key()`) — but a production deployment with several gunicorn
# workers needs it fixed, or each worker signs cookies with a different
# random key and a logged-in visitor bounces between "logged in" and
# "logged out" depending on which worker answers the request, and any
# server restart signs everyone out at once.
VARIABLE_ENTORNO_SECRET_KEY = "ANCLA_SECRET_KEY"

_log = logging.getLogger(__name__)

RAIZ_PERFIL_POR_DEFECTO = data_root() / PROFILE_DIR_NAME
RAIZ_PERFILES_POR_DEFECTO = data_root() / PROFILES_DIR_NAME
RAIZ_PLANTILLAS_CANVA_POR_DEFECTO = templates_root() / "canva-templates"
RAIZ_PLANTILLAS_HTML_POR_DEFECTO = templates_root() / "html-templates"
# Caps any single upload (CV import, profile zip restore). Flask enforces
# this before the view even runs, so it protects the shared Render demo
# from a stranger exhausting memory with an oversized request body.
TAMANO_MAXIMO_SUBIDA = 20 * 1024 * 1024  # 20 MB
# The Hugging Face Space starts the app with `ANCLA_DEMO=1` (see the
# Space's Dockerfile). In demo mode, several strangers share the same
# example profile and the same process: `contexto.ajustes_actuales()`
# stores the API key in each visitor's session instead of in
# `ajustes.json`, so no one sees a key another visitor tried out.
MODO_DEMO_POR_DEFECTO = os.environ.get("ANCLA_DEMO") == "1"


def _secret_key() -> str:
    """Reads `ANCLA_SECRET_KEY` from the environment; falls back to a random
    key, logging a warning, when it is unset. A single local process (the
    desktop build, a lone dev server) never notices the difference — but a
    deployment with more than one worker process needs the variable fixed,
    or each worker signs session cookies with a different key (see the
    module docstring above `VARIABLE_ENTORNO_SECRET_KEY`). Never raises:
    unlike `ANCLA_CLAVE_CIFRADO`, this is not a case where an unset variable
    should block startup, since the single-process case has no problem."""
    clave = os.environ.get(VARIABLE_ENTORNO_SECRET_KEY, "").strip()
    if clave:
        return clave
    _log.warning(
        "Falta la variable de entorno %s: se ha generado una clave aleatoria para este "
        "proceso. En un despliegue con varios workers (p. ej. gunicorn) cada worker "
        "firmaría las cookies de sesión con una clave distinta, y cualquier reinicio "
        "cerraría todas las sesiones activas. Define %s con un valor fijo antes de "
        "desplegar con más de un worker.",
        VARIABLE_ENTORNO_SECRET_KEY,
        VARIABLE_ENTORNO_SECRET_KEY,
    )
    return secrets.token_hex(32)


def create_app(
    raiz_perfil: Path | None = None,
    settings_path: Path | None = None,
    demo_mode: bool | None = None,
    canva_templates_root: Path | None = None,
    html_templates_root: Path | None = None,
    profiles_root: Path | None = None,
    require_login: bool = True,
) -> Flask:
    """`require_login` gates every screen behind an account, and is on by
    default wherever the app runs.

    Nobody uses Ancla without an account: not the packaged desktop build, not
    `run.py` in a local browser, not the hosted demo. Passing `False` is the
    explicit opt-out, and the only callers that do are the tests aimed at one
    screen rather than at the gate itself.

    It is an argument rather than something read from `routes.is_packaged()`
    or from the environment on purpose: whether an account is required is a
    product decision, not a packaging or deployment detail.
    """
    from flask_wtf import CSRFProtect
    from flask_wtf.csrf import CSRFError

    from ancla.auth.db import mysql_configured
    from ancla.profile.errors import ProfileError
    from ancla.profile.model import LANGUAGES, period_text
    from ancla.profile.validation import language_name
    from ancla.web import (
        context,
        views,  # noqa: F401 — registers the routes on bp when imported
    )
    from ancla.web import draft as modulo_borrador
    from ancla.web import settings as modulo_ajustes
    from ancla.web.blueprint import bp
    from ancla.web.presentation import (
        etiquetas_estado,
        period_marker_labels,
        skill_level_labels,
        years_for_period,
    )
    from ancla.web.util import list_to_csv, list_to_lines

    app = Flask(__name__)
    app.config["SECRET_KEY"] = _secret_key()
    app.config["MAX_CONTENT_LENGTH"] = TAMANO_MAXIMO_SUBIDA
    app.config["RAIZ_PERFIL"] = raiz_perfil or RAIZ_PERFIL_POR_DEFECTO
    app.config["RUTA_AJUSTES"] = settings_path or modulo_ajustes.RUTA_POR_DEFECTO
    # One folder per account (`perfiles/<user id>/`, profile and settings
    # together), used instead of the two above while someone is logged in
    # (see `context.root()`).
    app.config["RAIZ_PERFILES"] = profiles_root or RAIZ_PERFILES_POR_DEFECTO
    app.config["RAIZ_PLANTILLAS_CANVA"] = canva_templates_root or RAIZ_PLANTILLAS_CANVA_POR_DEFECTO
    app.config["RAIZ_PLANTILLAS_HTML"] = html_templates_root or RAIZ_PLANTILLAS_HTML_POR_DEFECTO
    app.config["MODO_DEMO"] = MODO_DEMO_POR_DEFECTO if demo_mode is None else demo_mode
    app.config["REQUIERE_SESION"] = require_login
    app.config["LANGUAGES"] = modulo_ajustes.IDIOMAS_INTERFAZ
    app.config["BABEL_DEFAULT_LOCALE"] = modulo_ajustes.IDIOMA_POR_DEFECTO
    # The catalogs live in ancla/translations/, one level above this
    # package (`web/`), which is where Babel looks by default.
    app.config["BABEL_TRANSLATION_DIRECTORIES"] = str(Path(__file__).resolve().parent.parent / "translations")
    app.register_blueprint(bp)
    CSRFProtect(app)
    _set_up_login(app)
    _require_login_everywhere(app)
    cuentas_disponibles = mysql_configured()
    app.jinja_env.filters["lista_a_lineas"] = list_to_lines
    app.jinja_env.filters["lista_a_csv"] = list_to_csv

    def _select_language() -> str:
        # Manual, not `request.accept_languages`: the preference saved in
        # ajustes.json is the single source of truth (see historial.md).
        return context.current_language()

    Babel(app, locale_selector=_select_language)
    # flask-babel registers `_` as a Jinja global, but not `get_locale`
    # (base.html uses it for the `lang` attribute and the ES/EN selector).
    app.jinja_env.globals["get_locale"] = get_locale

    def _period_of(elemento, idioma: str) -> str:
        """A stored period written out, for templates that only display it.
        The two halves are a storage detail; every screen wants the sentence."""
        return period_text(elemento.period_start, elemento.period_end, idioma)

    @app.context_processor
    def _inject_globals():
        return {
            "idiomas": LANGUAGES,
            "etiquetas_estado": etiquetas_estado(),
            "modo_demo": app.config["MODO_DEMO"],
            "anios": years_for_period(),
            "marcadores_periodo": period_marker_labels(),
            "niveles_skill": skill_level_labels(),
            "periodo": _period_of,
            # Screens that talk about a missing translation name the
            # language ("Traducir al inglés"), and the name has to follow
            # the interface's own language, not the CV's.
            "nombre_idioma": language_name,
            # The interface's own language, for chrome that names something
            # bilingual (a template's name) rather than showing CV content:
            # those follow the language of the CV, this one does not.
            "idioma_interfaz": context.current_language(),
            # Lets the nav dim "Última propuesta" while there is nothing to
            # show there yet, without hiding the link (see base.html).
            "hay_borrador": modulo_borrador.load_draft(context.root()) is not None,
            # Without MySQL the account links would only lead to a "database
            # unavailable" notice, so they are not shown.
            "cuentas_disponibles": cuentas_disponibles,
            # Lets the account screens explain that the app cannot be used
            # without an account. False only under the `require_login=False`
            # opt-out, where the rest of the app is reachable anyway.
            "requiere_sesion": app.config["REQUIERE_SESION"],
        }

    @app.errorhandler(404)
    def _page_not_found(_error):
        return render_template("404.html"), 404

    @app.errorhandler(413)
    def _payload_too_large(_error):
        flash(
            _(
                "El fichero es demasiado grande (máximo %(maximo)s MB).",
                maximo=TAMANO_MAXIMO_SUBIDA // (1024 * 1024),
            )
        )
        return redirect(request.referrer or url_for("ancla.view_profile"))

    @app.errorhandler(ProfileError)
    def _profile_error(error: ProfileError):
        # The message already comes translated and ready to show (see
        # perfil/errores.py): never a Python traceback.
        flash(str(error))
        return redirect(request.referrer or url_for("ancla.view_profile"))

    @app.errorhandler(modulo_ajustes.SettingsError)
    def _settings_error(error: modulo_ajustes.SettingsError):
        # Same convention as ProfileError: a message ready to show, never a
        # traceback — this is what "avisar con claridad" means when the
        # encryption env var is missing or wrong, instead of failing
        # silently or saving the key unencrypted.
        flash(str(error))
        return redirect(request.referrer or url_for("ancla.view_settings"))

    @app.errorhandler(CSRFError)
    def _csrf_error(_error: CSRFError):
        # A missing or expired token (the usual cause: a form left open past
        # the session's lifetime) — same convention as ProfileError/
        # SettingsError: a flash the visitor can act on, never a raw 400.
        flash(_("La sesión del formulario ha caducado. Inténtalo de nuevo."))
        return redirect(request.referrer or url_for("ancla.view_profile"))

    return app


# Reachable without a session while the gate is on: the account screens
# themselves, the static files they need, and the terms the login screen
# links to in its footer.
ENDPOINTS_SIN_SESION = frozenset({
    "static",
    "ancla.login",
    "ancla.register",
    "ancla.verify_email",
    "ancla.resend_verification",
    "ancla.terms",
})


def _require_login_everywhere(app: Flask) -> None:
    """Sends anyone without a session to the login screen, for every screen
    but the account ones.

    A single `before_request` instead of decorating each view: there are
    dozens of routes across `views/`, and the rest of the app is written so
    that no view knows accounts exist (see `context.root()`). This is the
    normal state of the app everywhere; it does nothing only when someone
    built it with the explicit `require_login=False` opt-out.
    """
    if not app.config["REQUIERE_SESION"]:
        return

    @app.before_request
    def _gate():
        if current_user.is_authenticated or request.endpoint in ENDPOINTS_SIN_SESION:
            return None
        # An unknown endpoint (request.endpoint is None on a 404) is sent to
        # the login screen too: without a session there is nothing to show.
        return redirect(url_for("ancla.login"))


def _set_up_login(app: Flask) -> None:
    from ancla.web.views.auth import users

    login_manager = LoginManager(app)
    login_manager.login_view = "ancla.login"

    @login_manager.user_loader
    def _load_user(user_id: str):
        # Only runs when the session carries a logged-in id. If the database
        # is unreachable the visitor is treated as logged out rather than
        # getting an error on a screen that does not even need an account.
        try:
            return users().by_id(int(user_id))
        except Exception:
            return None
