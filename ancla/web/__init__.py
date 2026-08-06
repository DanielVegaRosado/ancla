"""Interfaz web: Flask + HTML/CSS/JS plano, sin dependencias externas ni CDN.

Cinco pantallas: Mi perfil, Adaptar, Propuesta, Mis CVs y Ajustes. Interfaz
bilingüe ES/EN (selector manual en la cabecera, sin autodetección — ver
`ajustes.idioma`). Corre en local; no hay cuentas ni autenticación porque
solo la usa el dueño del ordenador donde vive el perfil.

Cada pantalla es un módulo en `ancla/web/vistas/`, con sus rutas
registradas en el único `Blueprint` de `ancla/web/blueprint.py`. Esta
fábrica solo monta la app: configuración, filtros de plantilla y manejo de
errores — no sabe nada de ninguna pantalla en concreto.
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, url_for
from flask_babel import Babel, get_locale

from ancla.web.rutas import raiz_datos

RAIZ_PERFIL_POR_DEFECTO = raiz_datos() / "perfil"
# El Space de Hugging Face arranca la app con `ANCLA_DEMO=1` (ver
# Dockerfile del Space). En modo demo, varios desconocidos comparten el mismo
# perfil de ejemplo y el mismo proceso: `contexto.ajustes_actuales()` guarda
# la clave de API en la sesión de cada visitante en vez de en `ajustes.json`,
# para que nadie vea la clave que otro visitante haya probado.
MODO_DEMO_POR_DEFECTO = os.environ.get("ANCLA_DEMO") == "1"


def crear_app(
    raiz_perfil: Path | None = None,
    ruta_ajustes: Path | None = None,
    modo_demo: bool | None = None,
) -> Flask:
    from ancla.perfil.errores import ErrorPerfil
    from ancla.perfil.modelo import IDIOMAS
    from ancla.web import ajustes as modulo_ajustes
    from ancla.web import contexto
    from ancla.web import vistas  # noqa: F401 — registra las rutas en bp al importarse
    from ancla.web.blueprint import bp
    from ancla.web.presentacion import ETIQUETAS_ESTADO
    from ancla.web.util import lista_a_csv, lista_a_lineas

    app = Flask(__name__)
    app.config["SECRET_KEY"] = secrets.token_hex(32)
    app.config["RAIZ_PERFIL"] = raiz_perfil or RAIZ_PERFIL_POR_DEFECTO
    app.config["RUTA_AJUSTES"] = ruta_ajustes or modulo_ajustes.RUTA_POR_DEFECTO
    app.config["MODO_DEMO"] = MODO_DEMO_POR_DEFECTO if modo_demo is None else modo_demo
    app.config["LANGUAGES"] = modulo_ajustes.IDIOMAS_INTERFAZ
    app.config["BABEL_DEFAULT_LOCALE"] = modulo_ajustes.IDIOMA_POR_DEFECTO
    # Los catálogos viven en ancla/translations/, un nivel por encima
    # de este paquete (`web/`), que es donde Babel busca por defecto.
    app.config["BABEL_TRANSLATION_DIRECTORIES"] = str(Path(__file__).resolve().parent.parent / "translations")
    app.register_blueprint(bp)
    app.jinja_env.filters["lista_a_lineas"] = lista_a_lineas
    app.jinja_env.filters["lista_a_csv"] = lista_a_csv

    def _seleccionar_idioma() -> str:
        # Manual, no `request.accept_languages`: la preferencia guardada en
        # ajustes.json es la única fuente de verdad (ver historial.md).
        return contexto.idioma_actual()

    Babel(app, locale_selector=_seleccionar_idioma)
    # flask-babel registra `_` como global de Jinja, pero no `get_locale`
    # (lo usa base.html para el atributo `lang` y el selector ES/EN).
    app.jinja_env.globals["get_locale"] = get_locale

    @app.context_processor
    def _inyectar_globales():
        return {
            "idiomas": IDIOMAS,
            "etiquetas_estado": ETIQUETAS_ESTADO,
            "modo_demo": app.config["MODO_DEMO"],
        }

    @app.errorhandler(404)
    def _pagina_no_encontrada(_error):
        return render_template("404.html"), 404

    @app.errorhandler(ErrorPerfil)
    def _error_de_perfil(error: ErrorPerfil):
        # El mensaje ya viene traducido y listo para enseñar (ver
        # perfil/errores.py): nunca una traza de Python.
        flash(str(error))
        return redirect(request.referrer or url_for("ancla.ver_perfil"))

    return app
