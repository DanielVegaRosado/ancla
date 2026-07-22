"""Pantalla Importar: sube tu CV (PDF/Word) o pega el texto, la IA propone
experiencias y skills, y tú confirmas qué guardar antes de que toque el perfil.

Dos pasos con estado efímero entre medias (`web/importacion.py`), mismo
patrón que Adaptar → Propuesta con el borrador: nada se guarda en el perfil
hasta la confirmación explícita del segundo paso.
"""
from __future__ import annotations

from dataclasses import replace

from flask import flash, redirect, render_template, request, url_for

from cv_adaptativo.ia.cliente import ErrorIA
from cv_adaptativo.perfil import almacen, importador, validacion
from cv_adaptativo.perfil.extraccion import ErrorExtraccion, extraer_texto
from cv_adaptativo.perfil.modelo import Bilingue, Experiencia, Skill
from cv_adaptativo.web import ajustes as modulo_ajustes
from cv_adaptativo.web import contexto
from cv_adaptativo.web import importacion as modulo_importacion
from cv_adaptativo.web.blueprint import bp
from cv_adaptativo.web.proveedores import crear_cliente
from cv_adaptativo.web.util import lineas_a_lista


@bp.route("/perfil/importar", methods=["GET", "POST"])
def importar():
    if request.method == "GET":
        return render_template("importar.html")

    fichero = request.files.get("fichero")
    texto_pegado = request.form.get("texto", "").strip()

    try:
        texto_cv = _texto_de_entrada(fichero, texto_pegado)
    except ErrorExtraccion as error:
        flash(str(error))
        return render_template("importar.html")

    ajustes = modulo_ajustes.cargar_ajustes(contexto.ruta_ajustes())
    try:
        cliente = crear_cliente(ajustes.proveedor, ajustes.clave_api)
    except ErrorIA as error:
        flash(str(error))
        return render_template("importar.html")
    if not cliente.disponible():
        flash("Configura tu clave de API en Ajustes antes de importar un CV.")
        return redirect(url_for("cv_adaptativo.ver_ajustes"))

    resultado = importador.analizar_cv(cliente, texto_cv, contexto.perfil_actual())
    if not resultado.experiencias and not resultado.skills:
        for aviso in resultado.avisos:
            flash(aviso)
        return render_template("importar.html")

    modulo_importacion.guardar_importacion(
        contexto.raiz(),
        modulo_importacion.Importacion(
            experiencias=resultado.experiencias,
            skills=resultado.skills,
            avisos=resultado.avisos,
        ),
    )
    return redirect(url_for("cv_adaptativo.revisar_importacion"))


def _texto_de_entrada(fichero, texto_pegado: str) -> str:
    if fichero is not None and fichero.filename:
        return extraer_texto(fichero.filename, fichero.read())
    if texto_pegado:
        return texto_pegado
    raise ErrorExtraccion("Sube un fichero o pega el texto de tu CV antes de continuar.")


@bp.route("/perfil/importar/revisar")
def revisar_importacion():
    importacion = modulo_importacion.cargar_importacion(contexto.raiz())
    if importacion is None:
        flash("No hay ninguna importación pendiente de revisar.")
        return redirect(url_for("cv_adaptativo.importar"))
    return render_template("importar_revisar.html", importacion=importacion)


@bp.route("/perfil/importar/guardar", methods=["POST"])
def guardar_importacion():
    importacion = modulo_importacion.cargar_importacion(contexto.raiz())
    if importacion is None:
        flash("Esa importación ya no está disponible: vuelve a subir el CV.")
        return redirect(url_for("cv_adaptativo.importar"))

    guardadas = 0
    con_error = 0
    for indice, experiencia in enumerate(importacion.experiencias):
        if request.form.get(f"exp-{indice}") != "1":
            continue
        editada = _experiencia_editada(request.form, indice, experiencia)
        errores = validacion.validar_experiencia(editada)
        if errores:
            con_error += 1
            continue
        almacen.guardar_experiencia(contexto.raiz(), editada)
        guardadas += 1

    for indice, skill in enumerate(importacion.skills):
        if request.form.get(f"skill-{indice}") != "1":
            continue
        editada = _skill_editada(request.form, indice, skill)
        errores = validacion.validar_skill(editada)
        if errores:
            con_error += 1
            continue
        almacen.guardar_skill(contexto.raiz(), editada)
        guardadas += 1

    modulo_importacion.borrar_importacion(contexto.raiz())

    if guardadas:
        flash(f"{guardadas} elemento(s) añadidos al perfil.")
    if con_error:
        flash(
            f"{con_error} elemento(s) no se pudieron guardar por falta de datos "
            "(faltaba el nombre en algún idioma, o palabras clave). Añádelos a mano "
            "en «Mi perfil»."
        )
    return redirect(url_for("cv_adaptativo.ver_perfil"))


def _experiencia_editada(form, indice: int, original: Experiencia) -> Experiencia:
    prefijo = f"exp-{indice}"
    return replace(
        original,
        titulo=Bilingue(
            es=form.get(f"{prefijo}-titulo_es", original.titulo["es"]).strip(),
            en=form.get(f"{prefijo}-titulo_en", original.titulo["en"]).strip(),
        ),
        periodo=Bilingue(
            es=form.get(f"{prefijo}-periodo_es", original.periodo["es"]).strip(),
            en=form.get(f"{prefijo}-periodo_en", original.periodo["en"]).strip(),
        ),
        bullets=Bilingue(
            es=lineas_a_lista(form.get(f"{prefijo}-bullets_es", "")),
            en=lineas_a_lista(form.get(f"{prefijo}-bullets_en", "")),
        ),
        stack=Bilingue(
            es=form.get(f"{prefijo}-stack_es", original.stack["es"]).strip(),
            en=form.get(f"{prefijo}-stack_en", original.stack["en"]).strip(),
        ),
    )


def _skill_editada(form, indice: int, original: Skill) -> Skill:
    prefijo = f"skill-{indice}"
    return replace(
        original,
        nombre=Bilingue(
            es=form.get(f"{prefijo}-nombre_es", original.nombre["es"]).strip(),
            en=form.get(f"{prefijo}-nombre_en", original.nombre["en"]).strip(),
        ),
        categoria=form.get(f"{prefijo}-categoria", original.categoria).strip(),
    )


@bp.route("/perfil/importar/descartar", methods=["POST"])
def descartar_importacion():
    modulo_importacion.borrar_importacion(contexto.raiz())
    flash("Importación descartada. No se ha guardado nada.")
    return redirect(url_for("cv_adaptativo.importar"))
