"""Interfaz web: Flask + HTML/CSS/JS plano, sin dependencias externas ni CDN.

Cinco pantallas: Mi perfil, Adaptar, Propuesta, Mis CVs y Ajustes. Interfaz
bilingüe ES/EN (selector manual en la cabecera, sin autodetección — ver
`ajustes.idioma`). Corre en local; no hay cuentas ni autenticación porque
solo la usa el dueño del ordenador donde vive el perfil.

Cada pantalla es un módulo en `cv_adaptativo/web/vistas/`, con sus rutas
registradas en el único `Blueprint` de `cv_adaptativo/web/blueprint.py`. Esta
fábrica solo monta la app: configuración, filtros de plantilla y manejo de
errores — no sabe nada de ninguna pantalla en concreto.
"""
from __future__ import annotations

import secrets
from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, url_for
from flask_babel import Babel, get_locale

from cv_adaptativo.web.rutas import raiz_datos

RAIZ_PERFIL_POR_DEFECTO = raiz_datos() / "perfil"


def crear_app(raiz_perfil: Path | None = None, ruta_ajustes: Path | None = None) -> Flask:
    from cv_adaptativo.perfil.errores import ErrorPerfil
    from cv_adaptativo.perfil.modelo import IDIOMAS
    from cv_adaptativo.web import ajustes as modulo_ajustes
    from cv_adaptativo.web import contexto
    from cv_adaptativo.web import vistas  # noqa: F401 — registra las rutas en bp al importarse
    from cv_adaptativo.web.blueprint import bp
    from cv_adaptativo.web.presentacion import ETIQUETAS_ESTADO
    from cv_adaptativo.web.util import lista_a_csv, lista_a_lineas

    app = Flask(__name__)
    app.config["SECRET_KEY"] = secrets.token_hex(32)
    app.config["RAIZ_PERFIL"] = raiz_perfil or RAIZ_PERFIL_POR_DEFECTO
    app.config["RUTA_AJUSTES"] = ruta_ajustes or modulo_ajustes.RUTA_POR_DEFECTO
    app.config["LANGUAGES"] = modulo_ajustes.IDIOMAS_INTERFAZ
    app.config["BABEL_DEFAULT_LOCALE"] = modulo_ajustes.IDIOMA_POR_DEFECTO
    # Los catálogos viven en cv_adaptativo/translations/, un nivel por encima
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
        return {"idiomas": IDIOMAS, "etiquetas_estado": ETIQUETAS_ESTADO}

    @app.errorhandler(404)
    def _pagina_no_encontrada(_error):
        return render_template("404.html"), 404

    @app.errorhandler(ErrorPerfil)
    def _error_de_perfil(error: ErrorPerfil):
        # El mensaje ya viene traducido y listo para enseñar (ver
        # perfil/errores.py): nunca una traza de Python.
        flash(str(error))
        return redirect(request.referrer or url_for("cv_adaptativo.ver_perfil"))

    return app
