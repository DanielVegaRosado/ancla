"""Web interface: Flask + plain HTML/CSS/JS, no external dependencies or CDN.

Five screens: My profile, Adapt, Proposal, My CVs, and Settings. Bilingual
ES/EN interface (manual selector in the header, no auto-detection — see
`ajustes.idioma`). Runs locally; there are no accounts or authentication
because only the owner of the computer the profile lives on ever uses it.

Each screen is a module under `ancla/web/vistas/`, with its routes
registered on the single `Blueprint` in `ancla/web/blueprint.py`. This
factory only assembles the app: configuration, template filters, and error
handling — it knows nothing about any particular screen.
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, url_for
from flask_babel import Babel, get_locale

from ancla.web.routes import data_root

RAIZ_PERFIL_POR_DEFECTO = data_root() / "perfil"
# The Hugging Face Space starts the app with `ANCLA_DEMO=1` (see the
# Space's Dockerfile). In demo mode, several strangers share the same
# example profile and the same process: `contexto.ajustes_actuales()`
# stores the API key in each visitor's session instead of in
# `ajustes.json`, so no one sees a key another visitor tried out.
MODO_DEMO_POR_DEFECTO = os.environ.get("ANCLA_DEMO") == "1"


def create_app(
    raiz_perfil: Path | None = None,
    settings_path: Path | None = None,
    demo_mode: bool | None = None,
) -> Flask:
    from ancla.profile.errors import ProfileError
    from ancla.profile.model import LANGUAGES
    from ancla.web import settings as modulo_ajustes
    from ancla.web import context
    from ancla.web import views  # noqa: F401 — registers the routes on bp when imported
    from ancla.web.blueprint import bp
    from ancla.web.presentation import ETIQUETAS_ESTADO
    from ancla.web.util import list_to_csv, list_to_lines

    app = Flask(__name__)
    app.config["SECRET_KEY"] = secrets.token_hex(32)
    app.config["RAIZ_PERFIL"] = raiz_perfil or RAIZ_PERFIL_POR_DEFECTO
    app.config["RUTA_AJUSTES"] = settings_path or modulo_ajustes.RUTA_POR_DEFECTO
    app.config["MODO_DEMO"] = MODO_DEMO_POR_DEFECTO if demo_mode is None else demo_mode
    app.config["LANGUAGES"] = modulo_ajustes.IDIOMAS_INTERFAZ
    app.config["BABEL_DEFAULT_LOCALE"] = modulo_ajustes.IDIOMA_POR_DEFECTO
    # The catalogs live in ancla/translations/, one level above this
    # package (`web/`), which is where Babel looks by default.
    app.config["BABEL_TRANSLATION_DIRECTORIES"] = str(Path(__file__).resolve().parent.parent / "translations")
    app.register_blueprint(bp)
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

    @app.context_processor
    def _inject_globals():
        return {
            "idiomas": LANGUAGES,
            "etiquetas_estado": ETIQUETAS_ESTADO,
            "modo_demo": app.config["MODO_DEMO"],
        }

    @app.errorhandler(404)
    def _page_not_found(_error):
        return render_template("404.html"), 404

    @app.errorhandler(ProfileError)
    def _profile_error(error: ProfileError):
        # The message already comes translated and ready to show (see
        # perfil/errores.py): never a Python traceback.
        flash(str(error))
        return redirect(request.referrer or url_for("ancla.view_profile"))

    return app
