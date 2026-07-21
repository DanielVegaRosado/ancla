"""Pantalla Adaptar: pegar una vacante, elegir idioma y generar la propuesta."""
from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for

from cv_adaptativo.archivo import repositorio as archivo
from cv_adaptativo.ia.cliente import ErrorIA
from cv_adaptativo.perfil.modelo import N_EXPERIENCIAS, N_SKILLS
from cv_adaptativo.seleccion import motor
from cv_adaptativo.vacante import analisis
from cv_adaptativo.web import ajustes as modulo_ajustes
from cv_adaptativo.web import borrador as modulo_borrador
from cv_adaptativo.web import contexto
from cv_adaptativo.web.blueprint import bp
from cv_adaptativo.web.proveedores import crear_cliente


@bp.route("/adaptar", methods=["GET", "POST"])
def adaptar():
    if request.method == "GET":
        return render_template("adaptar.html", vacante="", idioma="es")

    vacante_texto = request.form.get("vacante", "").strip()
    idioma = request.form.get("idioma", "es")
    forzar = request.form.get("forzar") == "1"

    if not vacante_texto:
        flash("Pega el texto de la vacante antes de generar la propuesta.")
        return render_template("adaptar.html", vacante=vacante_texto, idioma=idioma)

    perfil = contexto.perfil_actual()
    if perfil.esta_vacio() or perfil.sobre_mi is None:
        flash("Tu perfil todavía no tiene experiencia, skills o «Sobre mí». Complétalo antes de adaptar un CV.")
        return redirect(url_for("cv_adaptativo.ver_perfil"))

    datos_vacante = analisis.extraer_datos(vacante_texto)

    if not forzar and datos_vacante.empresa:
        previos = archivo.buscar_por_empresa(contexto.raiz(), datos_vacante.empresa)
        if previos:
            return render_template(
                "adaptar.html",
                vacante=vacante_texto,
                idioma=idioma,
                previos=previos,
                empresa=datos_vacante.empresa,
            )

    ajustes = modulo_ajustes.cargar_ajustes(contexto.ruta_ajustes())
    try:
        cliente = crear_cliente(ajustes.proveedor, ajustes.clave_api)
    except ErrorIA as error:
        flash(str(error))
        return render_template("adaptar.html", vacante=vacante_texto, idioma=idioma)
    if not cliente.disponible():
        flash("Configura tu clave de API en Ajustes antes de generar una propuesta.")
        return redirect(url_for("cv_adaptativo.ver_ajustes"))

    try:
        propuesta = motor.adaptar(perfil, vacante_texto, idioma, cliente, N_EXPERIENCIAS, N_SKILLS)
    except (ErrorIA, ValueError) as error:
        flash(str(error))
        return render_template("adaptar.html", vacante=vacante_texto, idioma=idioma)

    modulo_borrador.guardar_borrador(
        contexto.raiz(),
        modulo_borrador.Borrador(
            vacante=vacante_texto,
            empresa=datos_vacante.empresa,
            puesto=datos_vacante.puesto,
            propuesta=propuesta,
        ),
    )
    return redirect(url_for("cv_adaptativo.ver_propuesta"))
