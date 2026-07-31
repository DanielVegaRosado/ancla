"""Pantalla Mi perfil: editar experiencias, skills y la plantilla del Sobre mí."""
from __future__ import annotations

from flask import flash, jsonify, redirect, render_template, request, url_for
from flask_babel import gettext as _

from cv_adaptativo.perfil import almacen, keywords, validacion
from cv_adaptativo.perfil.modelo import Bilingue, Experiencia, IdiomaHablado, Skill, SobreMi
from cv_adaptativo.web import ajustes as modulo_ajustes
from cv_adaptativo.web import contexto
from cv_adaptativo.web.blueprint import bp
from cv_adaptativo.web.proveedores import crear_cliente
from cv_adaptativo.web.util import csv_a_lista, lineas_a_lista, slugificar


@bp.route("/")
def portada():
    return redirect(url_for("cv_adaptativo.ver_perfil"))


@bp.route("/perfil")
def ver_perfil():
    ajustes = modulo_ajustes.cargar_ajustes(contexto.ruta_ajustes())
    return render_template("perfil.html", perfil=contexto.perfil_actual(), orden_perfil=ajustes.orden_perfil)


@bp.route("/perfil/orden", methods=["POST"])
def guardar_orden_perfil():
    """El usuario arrastra los paneles de Mi perfil a su gusto; esto solo
    persiste ese orden. Devuelve 200 siempre que la petición sea legible: un
    orden inválido no es un fallo del usuario que haya que explicarle, se
    resuelve solo cayendo al orden por defecto (`orden_perfil_valido`)."""
    datos = request.get_json(silent=True) or {}
    ajustes = modulo_ajustes.cargar_ajustes(contexto.ruta_ajustes())
    ajustes.orden_perfil = modulo_ajustes.orden_perfil_valido(datos.get("orden"))
    modulo_ajustes.guardar_ajustes(ajustes, contexto.ruta_ajustes())
    return jsonify({"ok": True})


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
    if contexto.perfil_actual().experiencia(id_) is not None:
        errores = [_("Ya existe una experiencia con el identificador «%(id)s».", id=id_)]
        return render_template("experiencia_form.html", experiencia=None, errores=errores, nueva=True)

    experiencia = _experiencia_desde_formulario(id_)
    errores = validacion.validar_experiencia(experiencia)
    if errores:
        return render_template("experiencia_form.html", experiencia=experiencia, errores=errores, nueva=True)

    almacen.guardar_experiencia(contexto.raiz(), experiencia)
    flash(_("Experiencia «%(titulo)s» guardada.", titulo=experiencia.titulo["es"]))
    return redirect(url_for("cv_adaptativo.ver_perfil"))


@bp.route("/perfil/experiencias/<id_>/editar", methods=["GET", "POST"])
def editar_experiencia(id_: str):
    existente = contexto.perfil_actual().experiencia(id_)
    if existente is None:
        flash(_("No existe la experiencia «%(id)s».", id=id_))
        return redirect(url_for("cv_adaptativo.ver_perfil"))

    if request.method == "GET":
        return render_template("experiencia_form.html", experiencia=existente, errores=[], nueva=False)

    experiencia = _experiencia_desde_formulario(id_)
    errores = validacion.validar_experiencia(experiencia)
    if errores:
        return render_template("experiencia_form.html", experiencia=experiencia, errores=errores, nueva=False)

    almacen.guardar_experiencia(contexto.raiz(), experiencia)
    flash(_("Experiencia «%(titulo)s» actualizada.", titulo=experiencia.titulo["es"]))
    return redirect(url_for("cv_adaptativo.ver_perfil"))


@bp.route("/perfil/experiencias/<id_>/borrar", methods=["POST"])
def borrar_experiencia(id_: str):
    almacen.borrar_experiencia(contexto.raiz(), id_)
    flash(_("Experiencia borrada."))
    return redirect(url_for("cv_adaptativo.ver_perfil"))


@bp.route("/perfil/experiencias/borrar-todas", methods=["POST"])
def borrar_todas_experiencias():
    n = len(contexto.perfil_actual().experiencias)
    almacen.borrar_todas_experiencias(contexto.raiz())
    flash(_("%(cantidad)s experiencia(s) borradas.", cantidad=n) if n else _("No había ninguna experiencia que borrar."))
    return redirect(url_for("cv_adaptativo.ver_perfil"))


@bp.route("/perfil/keywords", methods=["POST"])
def sugerir_keywords():
    """Propone keywords para la skill o experiencia que se está escribiendo.

    Devuelve siempre 200 con una lista (vacía si no se pudo): es una ayuda del
    formulario, y un error aquí no debe interrumpir a quien está escribiendo.
    El usuario revisa y amplía lo que se le propone — nunca se guarda solo.
    """
    datos = request.get_json(silent=True) or {}
    ajustes = modulo_ajustes.cargar_ajustes(contexto.ruta_ajustes())
    if not ajustes.configurado():
        return jsonify(
            {
                "keywords": [],
                "aviso": _(
                    "Configura tu clave de API en Ajustes para que la IA "
                    "te proponga keywords. Mientras tanto, escríbelas a mano."
                ),
            }
        )

    try:
        cliente = crear_cliente(ajustes.proveedor, ajustes.clave_api)
    except Exception:
        return jsonify({"keywords": [], "aviso": _("No se pudo contactar con el proveedor.")})

    if datos.get("tipo") == "experiencia":
        sugerencia = keywords.sugerir_para_experiencia(
            cliente,
            titulo=datos.get("titulo", ""),
            bullets=lineas_a_lista(datos.get("bullets", "")),
            stack=datos.get("stack", ""),
        )
    else:
        sugerencia = keywords.sugerir_para_skill(
            cliente,
            nombre_es=datos.get("nombre_es", ""),
            nombre_en=datos.get("nombre_en", ""),
            categoria=datos.get("categoria", ""),
        )

    return jsonify({"keywords": sugerencia.keywords, "aviso": sugerencia.motivo})


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
    if contexto.perfil_actual().skill(id_) is not None:
        errores = [_("Ya existe una skill con el identificador «%(id)s».", id=id_)]
        return render_template("skill_form.html", skill=None, errores=errores, nueva=True)

    skill = _skill_desde_formulario(id_)
    errores = validacion.validar_skill(skill)
    if errores:
        return render_template("skill_form.html", skill=skill, errores=errores, nueva=True)

    almacen.guardar_skill(contexto.raiz(), skill)
    flash(_("Skill «%(nombre)s» guardada.", nombre=skill.nombre["es"]))
    return redirect(url_for("cv_adaptativo.ver_perfil"))


@bp.route("/perfil/skills/<id_>/editar", methods=["GET", "POST"])
def editar_skill(id_: str):
    existente = contexto.perfil_actual().skill(id_)
    if existente is None:
        flash(_("No existe la skill «%(id)s».", id=id_))
        return redirect(url_for("cv_adaptativo.ver_perfil"))

    if request.method == "GET":
        return render_template("skill_form.html", skill=existente, errores=[], nueva=False)

    skill = _skill_desde_formulario(id_)
    errores = validacion.validar_skill(skill)
    if errores:
        return render_template("skill_form.html", skill=skill, errores=errores, nueva=False)

    almacen.guardar_skill(contexto.raiz(), skill)
    flash(_("Skill «%(nombre)s» actualizada.", nombre=skill.nombre["es"]))
    return redirect(url_for("cv_adaptativo.ver_perfil"))


@bp.route("/perfil/skills/<id_>/borrar", methods=["POST"])
def borrar_skill(id_: str):
    almacen.borrar_skill(contexto.raiz(), id_)
    flash(_("Skill borrada."))
    return redirect(url_for("cv_adaptativo.ver_perfil"))


@bp.route("/perfil/skills/borrar-todas", methods=["POST"])
def borrar_todas_skills():
    n = len(contexto.perfil_actual().skills)
    almacen.borrar_todas_skills(contexto.raiz())
    flash(_("%(cantidad)s skill(s) borradas.", cantidad=n) if n else _("No había ninguna skill que borrar."))
    return redirect(url_for("cv_adaptativo.ver_perfil"))


# --------------------------------------------------------------------------
# Skills personales: mismo tipo `Skill`, carpeta y validación aparte. Nunca
# entran al motor de selección — se muestran siempre completas en la
# Propuesta, no las elige la IA. Ver `Perfil` en modelo.py.
# --------------------------------------------------------------------------


@bp.route("/perfil/skills-personales/nueva", methods=["GET", "POST"])
def nueva_skill_personal():
    if request.method == "GET":
        return render_template("skill_personal_form.html", skill=None, errores=[], nueva=True)

    id_ = slugificar(request.form.get("id") or request.form.get("nombre_es", ""))
    if contexto.perfil_actual().skill_personal(id_) is not None:
        errores = [_("Ya existe una skill personal con el identificador «%(id)s».", id=id_)]
        return render_template("skill_personal_form.html", skill=None, errores=errores, nueva=True)

    skill = _skill_desde_formulario(id_)
    errores = validacion.validar_skill_personal(skill)
    if errores:
        return render_template("skill_personal_form.html", skill=skill, errores=errores, nueva=True)

    almacen.guardar_skill_personal(contexto.raiz(), skill)
    flash(_("Skill personal «%(nombre)s» guardada.", nombre=skill.nombre["es"]))
    return redirect(url_for("cv_adaptativo.ver_perfil"))


@bp.route("/perfil/skills-personales/<id_>/editar", methods=["GET", "POST"])
def editar_skill_personal(id_: str):
    existente = contexto.perfil_actual().skill_personal(id_)
    if existente is None:
        flash(_("No existe la skill personal «%(id)s».", id=id_))
        return redirect(url_for("cv_adaptativo.ver_perfil"))

    if request.method == "GET":
        return render_template("skill_personal_form.html", skill=existente, errores=[], nueva=False)

    skill = _skill_desde_formulario(id_)
    errores = validacion.validar_skill_personal(skill)
    if errores:
        return render_template("skill_personal_form.html", skill=skill, errores=errores, nueva=False)

    almacen.guardar_skill_personal(contexto.raiz(), skill)
    flash(_("Skill personal «%(nombre)s» actualizada.", nombre=skill.nombre["es"]))
    return redirect(url_for("cv_adaptativo.ver_perfil"))


@bp.route("/perfil/skills-personales/<id_>/borrar", methods=["POST"])
def borrar_skill_personal(id_: str):
    almacen.borrar_skill_personal(contexto.raiz(), id_)
    flash(_("Skill personal borrada."))
    return redirect(url_for("cv_adaptativo.ver_perfil"))


@bp.route("/perfil/skills-personales/borrar-todas", methods=["POST"])
def borrar_todas_skills_personales():
    n = len(contexto.perfil_actual().skills_personales)
    almacen.borrar_todas_skills_personales(contexto.raiz())
    flash(
        _("%(cantidad)s skill(s) personal(es) borradas.", cantidad=n)
        if n
        else _("No había ninguna skill personal que borrar.")
    )
    return redirect(url_for("cv_adaptativo.ver_perfil"))


# --------------------------------------------------------------------------
# Idiomas: mismo criterio que skills personales (catálogo aparte, siempre
# completo en la Propuesta), con un campo extra de nivel.
# --------------------------------------------------------------------------


def _idioma_desde_formulario(id_: str) -> IdiomaHablado:
    f = request.form
    return IdiomaHablado(
        id=id_,
        nombre=Bilingue(es=f.get("nombre_es", "").strip(), en=f.get("nombre_en", "").strip()),
        nivel=Bilingue(es=f.get("nivel_es", "").strip(), en=f.get("nivel_en", "").strip()),
        keywords=csv_a_lista(f.get("keywords", "")),
    )


@bp.route("/perfil/idiomas/nuevo", methods=["GET", "POST"])
def nuevo_idioma():
    if request.method == "GET":
        return render_template("idioma_form.html", idioma=None, errores=[], nuevo=True)

    id_ = slugificar(request.form.get("id") or request.form.get("nombre_es", ""))
    if contexto.perfil_actual().idioma(id_) is not None:
        errores = [_("Ya existe un idioma con el identificador «%(id)s».", id=id_)]
        return render_template("idioma_form.html", idioma=None, errores=errores, nuevo=True)

    idioma = _idioma_desde_formulario(id_)
    errores = validacion.validar_idioma(idioma)
    if errores:
        return render_template("idioma_form.html", idioma=idioma, errores=errores, nuevo=True)

    almacen.guardar_idioma(contexto.raiz(), idioma)
    flash(_("Idioma «%(nombre)s» guardado.", nombre=idioma.nombre["es"]))
    return redirect(url_for("cv_adaptativo.ver_perfil"))


@bp.route("/perfil/idiomas/<id_>/editar", methods=["GET", "POST"])
def editar_idioma(id_: str):
    existente = contexto.perfil_actual().idioma(id_)
    if existente is None:
        flash(_("No existe el idioma «%(id)s».", id=id_))
        return redirect(url_for("cv_adaptativo.ver_perfil"))

    if request.method == "GET":
        return render_template("idioma_form.html", idioma=existente, errores=[], nuevo=False)

    idioma = _idioma_desde_formulario(id_)
    errores = validacion.validar_idioma(idioma)
    if errores:
        return render_template("idioma_form.html", idioma=idioma, errores=errores, nuevo=False)

    almacen.guardar_idioma(contexto.raiz(), idioma)
    flash(_("Idioma «%(nombre)s» actualizado.", nombre=idioma.nombre["es"]))
    return redirect(url_for("cv_adaptativo.ver_perfil"))


@bp.route("/perfil/idiomas/<id_>/borrar", methods=["POST"])
def borrar_idioma(id_: str):
    almacen.borrar_idioma(contexto.raiz(), id_)
    flash(_("Idioma borrado."))
    return redirect(url_for("cv_adaptativo.ver_perfil"))


@bp.route("/perfil/idiomas/borrar-todos", methods=["POST"])
def borrar_todos_idiomas():
    n = len(contexto.perfil_actual().idiomas)
    almacen.borrar_todos_idiomas(contexto.raiz())
    flash(_("%(cantidad)s idioma(s) borrados.", cantidad=n) if n else _("No había ningún idioma que borrar."))
    return redirect(url_for("cv_adaptativo.ver_perfil"))


@bp.route("/perfil/sobre-mi", methods=["GET", "POST"])
def editar_sobre_mi():
    perfil = contexto.perfil_actual()
    if request.method == "GET":
        return render_template("sobre_mi_form.html", sobre_mi=perfil.sobre_mi, errores=[])

    f = request.form
    sobre_mi = SobreMi(plantilla=Bilingue(es=f.get("plantilla_es", ""), en=f.get("plantilla_en", "")))
    errores = validacion.validar_sobre_mi(sobre_mi)
    if errores:
        return render_template("sobre_mi_form.html", sobre_mi=sobre_mi, errores=errores)

    almacen.guardar_sobre_mi(contexto.raiz(), sobre_mi)
    flash(_("Plantilla de «Sobre mí» guardada."))
    return redirect(url_for("cv_adaptativo.ver_perfil"))
