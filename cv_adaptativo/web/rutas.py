"""Todas las rutas de la app, en un único blueprint.

Cinco pantallas: Mi perfil, Adaptar, Propuesta, Mis CVs, Ajustes. La capa web
es la única responsable de: dónde vive el estado de trabajo efímero (el
`borrador` de una adaptación en curso) y de instanciar el cliente de IA a
partir de lo guardado en Ajustes — el motor de selección no sabe nada de
ninguna de las dos cosas.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename

from cv_adaptativo.archivo import repositorio as archivo
from cv_adaptativo.ia.cliente import ErrorIA
from cv_adaptativo.perfil import almacen, validacion
from cv_adaptativo.perfil.modelo import (
    IDIOMAS,
    N_EXPERIENCIAS,
    N_SKILLS,
    Bilingue,
    CVGuardado,
    EstadoCV,
    Experiencia,
    ExperienciaSeleccionada,
    SeleccionSobreMi,
    Skill,
    SobreMi,
)
from cv_adaptativo.propuesta.formato import a_markdown, a_texto, texto_experiencia
from cv_adaptativo.seleccion import motor
from cv_adaptativo.vacante import analisis
from cv_adaptativo.web import ajustes as modulo_ajustes
from cv_adaptativo.web import borrador as modulo_borrador
from cv_adaptativo.web.proveedores import crear_cliente
from cv_adaptativo.web.util import csv_a_lista, lineas_a_lista, slugificar

bp = Blueprint("cv_adaptativo", __name__)

ETIQUETAS_ESTADO = {
    EstadoCV.BORRADOR: "Borrador",
    EstadoCV.ENVIADO: "Enviado",
    EstadoCV.ENTREVISTA: "Entrevista",
    EstadoCV.DESCARTADO: "Descartado",
    EstadoCV.ACEPTADO: "Aceptado",
}


# --------------------------------------------------------------------------
# Helpers de contexto
# --------------------------------------------------------------------------


def _raiz():
    return current_app.config["RAIZ_PERFIL"]


def _ruta_ajustes():
    return current_app.config["RUTA_AJUSTES"]


def _perfil():
    return almacen.cargar_perfil(_raiz())


@bp.context_processor
def _inyectar_globales():
    return {"idiomas": IDIOMAS, "etiquetas_estado": ETIQUETAS_ESTADO}


# --------------------------------------------------------------------------
# Portada
# --------------------------------------------------------------------------


@bp.route("/")
def portada():
    return redirect(url_for("cv_adaptativo.ver_perfil"))


# --------------------------------------------------------------------------
# Mi perfil
# --------------------------------------------------------------------------


@bp.route("/perfil")
def ver_perfil():
    perfil = _perfil()
    return render_template("perfil.html", perfil=perfil)


def _experiencia_desde_formulario(id_: str) -> Experiencia:
    f = request.form
    return Experiencia(
        id=id_,
        titulo=Bilingue(es=f.get("titulo_es", "").strip(), en=f.get("titulo_en", "").strip()),
        periodo=Bilingue(es=f.get("periodo_es", "").strip(), en=f.get("periodo_en", "").strip()),
        bullets=Bilingue(
            es=lineas_a_lista(f.get("bullets_es", "")),
            en=lineas_a_lista(f.get("bullets_en", "")),
        ),
        stack=Bilingue(es=f.get("stack_es", "").strip(), en=f.get("stack_en", "").strip()),
        keywords=csv_a_lista(f.get("keywords", "")),
        estado=f.get("estado", "").strip(),
    )


@bp.route("/perfil/experiencias/nueva", methods=["GET", "POST"])
def nueva_experiencia():
    if request.method == "GET":
        return render_template("experiencia_form.html", experiencia=None, errores=[], nueva=True)

    id_ = slugificar(request.form.get("id") or request.form.get("titulo_es", ""))
    if _perfil().experiencia(id_) is not None:
        errores = [f"Ya existe una experiencia con el identificador «{id_}»."]
        return render_template("experiencia_form.html", experiencia=None, errores=errores, nueva=True)

    experiencia = _experiencia_desde_formulario(id_)
    errores = validacion.validar_experiencia(experiencia)
    if errores:
        return render_template("experiencia_form.html", experiencia=experiencia, errores=errores, nueva=True)

    almacen.guardar_experiencia(_raiz(), experiencia)
    flash(f"Experiencia «{experiencia.titulo['es']}» guardada.")
    return redirect(url_for("cv_adaptativo.ver_perfil"))


@bp.route("/perfil/experiencias/<id_>/editar", methods=["GET", "POST"])
def editar_experiencia(id_: str):
    existente = _perfil().experiencia(id_)
    if existente is None:
        flash(f"No existe la experiencia «{id_}».")
        return redirect(url_for("cv_adaptativo.ver_perfil"))

    if request.method == "GET":
        return render_template("experiencia_form.html", experiencia=existente, errores=[], nueva=False)

    experiencia = _experiencia_desde_formulario(id_)
    errores = validacion.validar_experiencia(experiencia)
    if errores:
        return render_template("experiencia_form.html", experiencia=experiencia, errores=errores, nueva=False)

    almacen.guardar_experiencia(_raiz(), experiencia)
    flash(f"Experiencia «{experiencia.titulo['es']}» actualizada.")
    return redirect(url_for("cv_adaptativo.ver_perfil"))


@bp.route("/perfil/experiencias/<id_>/borrar", methods=["POST"])
def borrar_experiencia(id_: str):
    almacen.borrar_experiencia(_raiz(), id_)
    flash("Experiencia borrada.")
    return redirect(url_for("cv_adaptativo.ver_perfil"))


def _skill_desde_formulario(id_: str) -> Skill:
    f = request.form
    return Skill(
        id=id_,
        nombre=Bilingue(es=f.get("nombre_es", "").strip(), en=f.get("nombre_en", "").strip()),
        categoria=f.get("categoria", "").strip(),
        keywords=csv_a_lista(f.get("keywords", "")),
    )


@bp.route("/perfil/skills/nueva", methods=["GET", "POST"])
def nueva_skill():
    if request.method == "GET":
        return render_template("skill_form.html", skill=None, errores=[], nueva=True)

    id_ = slugificar(request.form.get("id") or request.form.get("nombre_es", ""))
    if _perfil().skill(id_) is not None:
        errores = [f"Ya existe una skill con el identificador «{id_}»."]
        return render_template("skill_form.html", skill=None, errores=errores, nueva=True)

    skill = _skill_desde_formulario(id_)
    errores = validacion.validar_skill(skill)
    if errores:
        return render_template("skill_form.html", skill=skill, errores=errores, nueva=True)

    almacen.guardar_skill(_raiz(), skill)
    flash(f"Skill «{skill.nombre['es']}» guardada.")
    return redirect(url_for("cv_adaptativo.ver_perfil"))


@bp.route("/perfil/skills/<id_>/editar", methods=["GET", "POST"])
def editar_skill(id_: str):
    existente = _perfil().skill(id_)
    if existente is None:
        flash(f"No existe la skill «{id_}».")
        return redirect(url_for("cv_adaptativo.ver_perfil"))

    if request.method == "GET":
        return render_template("skill_form.html", skill=existente, errores=[], nueva=False)

    skill = _skill_desde_formulario(id_)
    errores = validacion.validar_skill(skill)
    if errores:
        return render_template("skill_form.html", skill=skill, errores=errores, nueva=False)

    almacen.guardar_skill(_raiz(), skill)
    flash(f"Skill «{skill.nombre['es']}» actualizada.")
    return redirect(url_for("cv_adaptativo.ver_perfil"))


@bp.route("/perfil/skills/<id_>/borrar", methods=["POST"])
def borrar_skill(id_: str):
    almacen.borrar_skill(_raiz(), id_)
    flash("Skill borrada.")
    return redirect(url_for("cv_adaptativo.ver_perfil"))


@bp.route("/perfil/sobre-mi", methods=["GET", "POST"])
def editar_sobre_mi():
    perfil = _perfil()
    if request.method == "GET":
        return render_template("sobre_mi_form.html", sobre_mi=perfil.sobre_mi, errores=[])

    f = request.form
    sobre_mi = SobreMi(plantilla=Bilingue(es=f.get("plantilla_es", ""), en=f.get("plantilla_en", "")))
    errores = validacion.validar_sobre_mi(sobre_mi)
    if errores:
        return render_template("sobre_mi_form.html", sobre_mi=sobre_mi, errores=errores)

    almacen.guardar_sobre_mi(_raiz(), sobre_mi)
    flash("Plantilla de «Sobre mí» guardada.")
    return redirect(url_for("cv_adaptativo.ver_perfil"))


# --------------------------------------------------------------------------
# Adaptar
# --------------------------------------------------------------------------


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

    perfil = _perfil()
    if perfil.esta_vacio() or perfil.sobre_mi is None:
        flash("Tu perfil todavía no tiene experiencia, skills o «Sobre mí». Complétalo antes de adaptar un CV.")
        return redirect(url_for("cv_adaptativo.ver_perfil"))

    datos_vacante = analisis.extraer_datos(vacante_texto)

    if not forzar and datos_vacante.empresa:
        previos = archivo.buscar_por_empresa(_raiz(), datos_vacante.empresa)
        if previos:
            return render_template(
                "adaptar.html",
                vacante=vacante_texto,
                idioma=idioma,
                previos=previos,
                empresa=datos_vacante.empresa,
            )

    ajustes = modulo_ajustes.cargar_ajustes(_ruta_ajustes())
    if not ajustes.configurado():
        flash("Configura tu clave de API en Ajustes antes de generar una propuesta.")
        return redirect(url_for("cv_adaptativo.ver_ajustes"))

    try:
        cliente = crear_cliente(ajustes.proveedor, ajustes.clave_api)
        propuesta = motor.adaptar(perfil, vacante_texto, idioma, cliente, N_EXPERIENCIAS, N_SKILLS)
    except ErrorIA as error:
        flash(str(error))
        return render_template("adaptar.html", vacante=vacante_texto, idioma=idioma)
    except ValueError as error:
        flash(str(error))
        return render_template("adaptar.html", vacante=vacante_texto, idioma=idioma)

    modulo_borrador.guardar_borrador(
        _raiz(),
        modulo_borrador.Borrador(
            vacante=vacante_texto,
            empresa=datos_vacante.empresa,
            puesto=datos_vacante.puesto,
            propuesta=propuesta,
        ),
    )
    return redirect(url_for("cv_adaptativo.ver_propuesta"))


# --------------------------------------------------------------------------
# Propuesta
# --------------------------------------------------------------------------


@bp.route("/propuesta")
def ver_propuesta():
    borrador = modulo_borrador.cargar_borrador(_raiz())
    if borrador is None:
        flash("Todavía no has generado ninguna propuesta. Empieza por pegar una vacante.")
        return redirect(url_for("cv_adaptativo.adaptar"))

    perfil = _perfil()
    propuesta = borrador.propuesta
    experiencias = [
        (sel, experiencia, texto_experiencia(experiencia, propuesta.idioma) if experiencia else None)
        for sel, experiencia in (
            (sel, perfil.experiencia(sel.id)) for sel in propuesta.experiencias
        )
    ]
    skills = [(id_, perfil.skill(id_)) for id_ in propuesta.skills]
    texto_skills = " · ".join(skill.nombre[propuesta.idioma] for _, skill in skills if skill)

    return render_template(
        "propuesta.html",
        borrador=borrador,
        propuesta=propuesta,
        perfil=perfil,
        experiencias=experiencias,
        skills=skills,
        texto_skills=texto_skills,
        texto_plano=a_texto(propuesta, perfil),
        texto_markdown=a_markdown(propuesta, perfil),
        hoy=date.today().isoformat(),
    )


def _con_borrador_o_redirigir():
    borrador = modulo_borrador.cargar_borrador(_raiz())
    if borrador is None:
        flash("Esa propuesta ya no está disponible: genera una nueva.")
        return None
    return borrador


@bp.route("/propuesta/ajustar-sobre-mi", methods=["POST"])
def ajustar_sobre_mi():
    borrador = _con_borrador_o_redirigir()
    if borrador is None:
        return redirect(url_for("cv_adaptativo.adaptar"))

    perfil = _perfil()
    if perfil.sobre_mi is None:
        flash("Tu perfil ya no tiene plantilla de «Sobre mí».")
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
    modulo_borrador.guardar_borrador(_raiz(), borrador)
    flash("«Sobre mí» actualizado.")
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
        modulo_borrador.guardar_borrador(_raiz(), borrador)
        flash("Skill actualizada.")
    return redirect(url_for("cv_adaptativo.ver_propuesta"))


@bp.route("/propuesta/ajustar-motivo-skills", methods=["POST"])
def ajustar_motivo_skills():
    borrador = _con_borrador_o_redirigir()
    if borrador is None:
        return redirect(url_for("cv_adaptativo.adaptar"))

    borrador.propuesta = replace(borrador.propuesta, motivo_skills=request.form.get("motivo", "").strip())
    modulo_borrador.guardar_borrador(_raiz(), borrador)
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
        modulo_borrador.guardar_borrador(_raiz(), borrador)
        flash("Experiencia actualizada.")
    return redirect(url_for("cv_adaptativo.ver_propuesta"))


@bp.route("/propuesta/regenerar/<seccion>", methods=["POST"])
def regenerar_seccion(seccion: str):
    borrador = _con_borrador_o_redirigir()
    if borrador is None:
        return redirect(url_for("cv_adaptativo.adaptar"))

    if seccion not in ("sobre-mi", "skills", "experiencias"):
        flash("Sección desconocida.")
        return redirect(url_for("cv_adaptativo.ver_propuesta"))

    ajustes = modulo_ajustes.cargar_ajustes(_ruta_ajustes())
    if not ajustes.configurado():
        flash("Configura tu clave de API en Ajustes antes de regenerar.")
        return redirect(url_for("cv_adaptativo.ver_ajustes"))

    try:
        cliente = crear_cliente(ajustes.proveedor, ajustes.clave_api)
        nueva_propuesta = motor.adaptar(
            _perfil(), borrador.vacante, borrador.propuesta.idioma, cliente, N_EXPERIENCIAS, N_SKILLS
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
    modulo_borrador.guardar_borrador(_raiz(), borrador)
    flash("Sección regenerada.")
    return redirect(url_for("cv_adaptativo.ver_propuesta"))


@bp.route("/propuesta/descartar", methods=["POST"])
def descartar_propuesta():
    modulo_borrador.borrar_borrador(_raiz())
    flash("Propuesta descartada.")
    return redirect(url_for("cv_adaptativo.adaptar"))


@bp.route("/propuesta/guardar", methods=["POST"])
def guardar_propuesta():
    borrador = _con_borrador_o_redirigir()
    if borrador is None:
        return redirect(url_for("cv_adaptativo.adaptar"))

    empresa = request.form.get("empresa", "").strip() or borrador.empresa or "Empresa"
    puesto = request.form.get("puesto", "").strip() or borrador.puesto
    notas = request.form.get("notas", "").strip()
    hoy = date.today()
    id_ = f"{hoy.isoformat()}_{slugificar(empresa)}_{slugificar(puesto)}"

    cv = CVGuardado(
        id=id_,
        fecha=hoy,
        empresa=empresa,
        puesto=puesto,
        vacante=borrador.vacante,
        propuesta=borrador.propuesta,
        estado=EstadoCV.BORRADOR,
        notas=notas,
    )
    archivo.guardar(_raiz(), cv)
    modulo_borrador.borrar_borrador(_raiz())
    flash(f"CV guardado en el archivo para {empresa}.")
    return redirect(url_for("cv_adaptativo.ver_cv", id_=id_))


# --------------------------------------------------------------------------
# Mis CVs
# --------------------------------------------------------------------------


@bp.route("/cvs")
def listar_cvs():
    cvs = archivo.listar(_raiz())
    return render_template("cvs.html", cvs=cvs)


@bp.route("/cvs/<id_>")
def ver_cv(id_: str):
    cv = next((c for c in archivo.listar(_raiz()) if c.id == id_), None)
    if cv is None:
        flash(f"No se encuentra el CV «{id_}» en el archivo.")
        return redirect(url_for("cv_adaptativo.listar_cvs"))

    perfil = _perfil()
    return render_template(
        "cv_detalle.html",
        cv=cv,
        perfil=perfil,
        texto_plano=a_texto(cv.propuesta, perfil),
        texto_markdown=a_markdown(cv.propuesta, perfil),
        estados=list(EstadoCV),
    )


@bp.route("/cvs/<id_>/estado", methods=["POST"])
def cambiar_estado_cv(id_: str):
    estado = request.form.get("estado", "")
    try:
        archivo.cambiar_estado(_raiz(), id_, EstadoCV(estado))
        flash("Estado actualizado.")
    except ValueError:
        flash("Estado no reconocido.")
    return redirect(url_for("cv_adaptativo.ver_cv", id_=id_))


@bp.route("/cvs/<id_>/adjuntar", methods=["POST"])
def adjuntar_cv(id_: str):
    archivo_subido = request.files.get("adjunto")
    if archivo_subido is None or not archivo_subido.filename:
        flash("Elige un archivo antes de adjuntarlo.")
        return redirect(url_for("cv_adaptativo.ver_cv", id_=id_))

    nombre_seguro = secure_filename(archivo_subido.filename)
    destino_temporal = _raiz() / "cvs" / "adjuntos" / f"_subida_{id_}_{nombre_seguro}"
    destino_temporal.parent.mkdir(parents=True, exist_ok=True)
    archivo_subido.save(destino_temporal)
    archivo.adjuntar(_raiz(), id_, destino_temporal)
    destino_temporal.unlink(missing_ok=True)
    flash("Archivo adjuntado.")
    return redirect(url_for("cv_adaptativo.ver_cv", id_=id_))


# --------------------------------------------------------------------------
# Ajustes
# --------------------------------------------------------------------------


@bp.route("/ajustes", methods=["GET", "POST"])
def ver_ajustes():
    if request.method == "GET":
        return render_template("ajustes.html", ajustes=modulo_ajustes.cargar_ajustes(_ruta_ajustes()))

    nuevos = modulo_ajustes.Ajustes(
        proveedor=request.form.get("proveedor", modulo_ajustes.PROVEEDOR_POR_DEFECTO),
        clave_api=request.form.get("clave_api", "").strip(),
    )
    modulo_ajustes.guardar_ajustes(nuevos, _ruta_ajustes())
    flash("Ajustes guardados.")
    return redirect(url_for("cv_adaptativo.ver_ajustes"))
