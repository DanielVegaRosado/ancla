"""Pantalla Propuesta: el resultado de Adaptar, con motivo, huecos, copiar,
ajuste directo por elemento y regenerar por sección."""
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime

from flask import flash, redirect, render_template, request, url_for
from flask_babel import gettext as _

from cv_adaptativo.ia.cliente import ErrorIA
from cv_adaptativo.perfil.modelo import (
    N_EXPERIENCIAS,
    N_SKILLS,
    CVGuardado,
    EstadoCV,
    ExperienciaSeleccionada,
    SeleccionSobreMi,
)
from cv_adaptativo.propuesta.formato import (
    a_markdown,
    a_texto,
    lineas_idiomas,
    nombres_skills_personales,
    texto_experiencia,
)
from cv_adaptativo.archivo import repositorio as archivo
from cv_adaptativo.seleccion import motor
from cv_adaptativo.web import borrador as modulo_borrador
from cv_adaptativo.web import contexto
from cv_adaptativo.web.blueprint import bp
from cv_adaptativo.web.proveedores import crear_cliente

_SECCIONES = ("sobre-mi", "skills", "experiencias")


@bp.route("/propuesta")
def ver_propuesta():
    borrador = modulo_borrador.cargar_borrador(contexto.raiz())
    if borrador is None:
        flash(_("Todavía no has generado ninguna propuesta. Empieza por pegar una vacante."))
        return redirect(url_for("cv_adaptativo.adaptar"))

    perfil = contexto.perfil_actual()
    propuesta = borrador.propuesta
    experiencias = [
        (sel, experiencia, texto_experiencia(experiencia, propuesta.idioma) if experiencia else None)
        for sel, experiencia in (
            (sel, perfil.experiencia(sel.id)) for sel in propuesta.experiencias
        )
    ]
    skills = [(id_, perfil.skill(id_)) for id_ in propuesta.skills]
    texto_skills = " · ".join(skill.nombre[propuesta.idioma] for _, skill in skills if skill)

    # Skills personales e idiomas no pasan por Propuesta ni por el borrador:
    # se leen en vivo del perfil en cada render, porque no hay selección de
    # IA que guardar — se muestran siempre completos.
    texto_skills_personales = " · ".join(nombres_skills_personales(perfil, propuesta.idioma))
    texto_idiomas = " · ".join(lineas_idiomas(perfil, propuesta.idioma))

    return render_template(
        "propuesta.html",
        borrador=borrador,
        propuesta=propuesta,
        perfil=perfil,
        experiencias=experiencias,
        skills=skills,
        texto_skills=texto_skills,
        texto_skills_personales=texto_skills_personales,
        texto_idiomas=texto_idiomas,
        texto_plano=a_texto(propuesta, perfil),
        texto_markdown=a_markdown(propuesta, perfil),
        hoy=date.today().isoformat(),
    )


def _con_borrador_o_redirigir():
    borrador = modulo_borrador.cargar_borrador(contexto.raiz())
    if borrador is None:
        flash(_("Esa propuesta ya no está disponible, genera una nueva."))
        return None
    return borrador


@bp.route("/propuesta/ajustar-sobre-mi", methods=["POST"])
def ajustar_sobre_mi():
    borrador = _con_borrador_o_redirigir()
    if borrador is None:
        return redirect(url_for("cv_adaptativo.adaptar"))

    perfil = contexto.perfil_actual()
    if perfil.sobre_mi is None:
        flash(_("Tu perfil ya no tiene plantilla de «Sobre mí»."))
        return redirect(url_for("cv_adaptativo.ver_propuesta"))

    f = request.form
    grupo_a = [f.get(f"grupo_a_{n}", "").strip() for n in (1, 2, 3)]
    grupo_b = [f.get(f"grupo_b_{n}", "").strip() for n in (1, 2, 3)]
    motivo = f.get("motivo", "").strip()

    try:
        texto = perfil.sobre_mi.render(grupo_a, grupo_b, borrador.propuesta.idioma)
    except ValueError as error:
        flash(str(error))
        return redirect(url_for("cv_adaptativo.ver_propuesta"))

    nueva_seleccion = SeleccionSobreMi(grupo_a=grupo_a, grupo_b=grupo_b, texto=texto, motivo=motivo)
    borrador.propuesta = replace(borrador.propuesta, sobre_mi=nueva_seleccion)
    modulo_borrador.guardar_borrador(contexto.raiz(), borrador)
    flash(_("«Sobre mí» actualizado."))
    return redirect(url_for("cv_adaptativo.ver_propuesta"))


@bp.route("/propuesta/ajustar-skill", methods=["POST"])
def ajustar_skill():
    borrador = _con_borrador_o_redirigir()
    if borrador is None:
        return redirect(url_for("cv_adaptativo.adaptar"))

    indice = int(request.form.get("indice", -1))
    nuevo_id = request.form.get("skill_id", "")
    skills = list(borrador.propuesta.skills)
    if 0 <= indice < len(skills) and nuevo_id:
        skills[indice] = nuevo_id
        borrador.propuesta = replace(borrador.propuesta, skills=skills)
        modulo_borrador.guardar_borrador(contexto.raiz(), borrador)
        flash(_("Skill actualizada."))
    return redirect(url_for("cv_adaptativo.ver_propuesta"))


@bp.route("/propuesta/ajustar-motivo-skills", methods=["POST"])
def ajustar_motivo_skills():
    borrador = _con_borrador_o_redirigir()
    if borrador is None:
        return redirect(url_for("cv_adaptativo.adaptar"))

    borrador.propuesta = replace(borrador.propuesta, motivo_skills=request.form.get("motivo", "").strip())
    modulo_borrador.guardar_borrador(contexto.raiz(), borrador)
    return redirect(url_for("cv_adaptativo.ver_propuesta"))


@bp.route("/propuesta/ajustar-experiencia", methods=["POST"])
def ajustar_experiencia():
    borrador = _con_borrador_o_redirigir()
    if borrador is None:
        return redirect(url_for("cv_adaptativo.adaptar"))

    indice = int(request.form.get("indice", -1))
    nuevo_id = request.form.get("experiencia_id", "")
    motivo = request.form.get("motivo", "").strip()
    experiencias = list(borrador.propuesta.experiencias)
    if 0 <= indice < len(experiencias) and nuevo_id:
        experiencias[indice] = ExperienciaSeleccionada(id=nuevo_id, motivo=motivo)
        borrador.propuesta = replace(borrador.propuesta, experiencias=experiencias)
        modulo_borrador.guardar_borrador(contexto.raiz(), borrador)
        flash(_("Experiencia actualizada."))
    return redirect(url_for("cv_adaptativo.ver_propuesta"))


@bp.route("/propuesta/regenerar/<seccion>", methods=["POST"])
def regenerar_seccion(seccion: str):
    borrador = _con_borrador_o_redirigir()
    if borrador is None:
        return redirect(url_for("cv_adaptativo.adaptar"))

    if seccion not in _SECCIONES:
        flash(_("Sección desconocida."))
        return redirect(url_for("cv_adaptativo.ver_propuesta"))

    ajustes = contexto.ajustes_actuales()
    try:
        cliente = crear_cliente(ajustes.proveedor, ajustes.clave_api, ajustes.url_base, ajustes.modelo)
    except ErrorIA as error:
        flash(str(error))
        return redirect(url_for("cv_adaptativo.ver_propuesta"))
    if not cliente.disponible():
        flash(_("Configura tu clave de API en Ajustes antes de regenerar."))
        return redirect(url_for("cv_adaptativo.ver_ajustes"))

    try:
        nueva_propuesta = motor.adaptar(
            contexto.perfil_actual(), borrador.vacante, borrador.propuesta.idioma, cliente, N_EXPERIENCIAS, N_SKILLS
        )
    except (ErrorIA, ValueError) as error:
        flash(str(error))
        return redirect(url_for("cv_adaptativo.ver_propuesta"))

    if seccion == "sobre-mi":
        borrador.propuesta = replace(borrador.propuesta, sobre_mi=nueva_propuesta.sobre_mi)
    elif seccion == "skills":
        borrador.propuesta = replace(
            borrador.propuesta, skills=nueva_propuesta.skills, motivo_skills=nueva_propuesta.motivo_skills
        )
    else:
        borrador.propuesta = replace(borrador.propuesta, experiencias=nueva_propuesta.experiencias)

    borrador.propuesta = replace(borrador.propuesta, huecos=nueva_propuesta.huecos)
    modulo_borrador.guardar_borrador(contexto.raiz(), borrador)
    flash(_("Sección regenerada."))
    return redirect(url_for("cv_adaptativo.ver_propuesta"))


@bp.route("/propuesta/descartar", methods=["POST"])
def descartar_propuesta():
    modulo_borrador.borrar_borrador(contexto.raiz())
    flash(_("Propuesta descartada."))
    return redirect(url_for("cv_adaptativo.adaptar"))


@bp.route("/propuesta/guardar", methods=["POST"])
def guardar_propuesta():
    borrador = _con_borrador_o_redirigir()
    if borrador is None:
        return redirect(url_for("cv_adaptativo.adaptar"))

    empresa = request.form.get("empresa", "").strip() or borrador.empresa or "Empresa"
    puesto = request.form.get("puesto", "").strip() or borrador.puesto
    notas = request.form.get("notas", "").strip()
    # Las dos salen del mismo instante para no cruzar medianoche entre una
    # captura y la otra si se leyeran por separado.
    ahora = datetime.now()
    id_ = archivo.nuevo_id(contexto.raiz(), ahora.date(), empresa, puesto)

    cv = CVGuardado(
        id=id_,
        fecha=ahora.date(),
        hora=ahora.time(),
        empresa=empresa,
        puesto=puesto,
        vacante=borrador.vacante,
        propuesta=borrador.propuesta,
        estado=EstadoCV.BORRADOR,
        notas=notas,
    )
    archivo.guardar(contexto.raiz(), cv)
    modulo_borrador.borrar_borrador(contexto.raiz())
    flash(_("CV guardado en el archivo para %(empresa)s.", empresa=empresa))
    return redirect(url_for("cv_adaptativo.ver_cv", id_=id_))
