"""Interfaz web: Flask + HTML/CSS/JS plano, sin dependencias externas ni CDN.

Cinco pantallas: Mi perfil, Adaptar, Propuesta, Mis CVs y Ajustes. Todo en
español. Corre en local; no hay cuentas ni autenticación porque solo la usa
el dueño del ordenador donde vive el perfil.

Cada pantalla es un módulo en `cv_adaptativo/web/vistas/`, con sus rutas
registradas en el único `Blueprint` de `cv_adaptativo/web/blueprint.py`. Esta
fábrica solo monta la app: configuración, filtros de plantilla y manejo de
errores — no sabe nada de ninguna pantalla en concreto.
"""
from __future__ import annotations

import secrets
from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, url_for

RAIZ_APP = Path(__file__).resolve().parents[2]
RAIZ_PERFIL_POR_DEFECTO = RAIZ_APP / "perfil"


def crear_app(raiz_perfil: Path | None = None, ruta_ajustes: Path | None = None) -> Flask:
    from cv_adaptativo.perfil.errores import ErrorPerfil
    from cv_adaptativo.perfil.modelo import IDIOMAS
    from cv_adaptativo.web import ajustes as modulo_ajustes
    from cv_adaptativo.web import vistas  # noqa: F401 — registra las rutas en bp al importarse
    from cv_adaptativo.web.blueprint import bp
    from cv_adaptativo.web.presentacion import ETIQUETAS_ESTADO
    from cv_adaptativo.web.util import lista_a_csv, lista_a_lineas

    app = Flask(__name__)
    app.config["SECRET_KEY"] = secrets.token_hex(32)
    app.config["RAIZ_PERFIL"] = raiz_perfil or RAIZ_PERFIL_POR_DEFECTO
    app.config["RUTA_AJUSTES"] = ruta_ajustes or modulo_ajustes.RUTA_POR_DEFECTO
    app.register_blueprint(bp)
    app.jinja_env.filters["lista_a_lineas"] = lista_a_lineas
    app.jinja_env.filters["lista_a_csv"] = lista_a_csv

    @app.context_processor
    def _inyectar_globales():
        return {"idiomas": IDIOMAS, "etiquetas_estado": ETIQUETAS_ESTADO}

    @app.errorhandler(404)
    def _pagina_no_encontrada(_error):
        return render_template("404.html"), 404

    @app.errorhandler(ErrorPerfil)
    def _error_de_perfil(error: ErrorPerfil):
        # El mensaje ya viene en español y listo para enseñar (ver
        # perfil/errores.py): nunca una traza de Python.
        flash(str(error))
        return redirect(request.referrer or url_for("cv_adaptativo.ver_perfil"))

    return app
