"""My profile screen: editing experiences, skills, and the About me template."""
from __future__ import annotations

from flask import abort, flash, jsonify, redirect, render_template, request, send_file, url_for
from flask_babel import gettext as _

from ancla.profile import store, keywords, validation
from ancla.profile.model import AboutMe, Bilingual, Education, Experience, Skill, SpokenLanguage
from ancla.web import settings as modulo_ajustes
from ancla.web import context
from ancla.web.blueprint import bp
from ancla.web.providers import create_client
from ancla.web.util import csv_to_list, lines_to_list, slugify


@bp.route("/")
def home():
    return redirect(url_for("ancla.view_profile"))


@bp.route("/perfil")
def view_profile():
    ajustes = context.current_settings()
    return render_template("profile.html", perfil=context.current_profile(), orden_perfil=ajustes.orden_perfil)


@bp.route("/perfil/orden", methods=["POST"])
def save_profile_order():
    """The user drags the My profile panels into whatever order they like;
    this just persists it. Always returns 200 as long as the request is
    readable: an invalid order is not a user mistake that needs explaining,
    it is resolved on its own by falling back to the default order
    (`orden_perfil_valido`)."""
    datos = request.get_json(silent=True) or {}
    ajustes = context.current_settings()
    ajustes.orden_perfil = modulo_ajustes.valid_profile_order(datos.get("orden"))
    context.save_current_settings(ajustes)
    return jsonify({"ok": True})


def _experience_from_form(id_: str) -> Experience:
    f = request.form
    return Experience(
        id=id_,
        title=Bilingual(es=f.get("titulo_es", "").strip(), en=f.get("titulo_en", "").strip()),
        period=Bilingual(es=f.get("periodo_es", "").strip(), en=f.get("periodo_en", "").strip()),
        bullets=Bilingual(
            es=lines_to_list(f.get("bullets_es", "")),
            en=lines_to_list(f.get("bullets_en", "")),
        ),
        stack=Bilingual(es=f.get("stack_es", "").strip(), en=f.get("stack_en", "").strip()),
        keywords=csv_to_list(f.get("keywords", "")),
        status=f.get("estado", "").strip(),
    )


@bp.route("/perfil/experiencias/nueva", methods=["GET", "POST"])
def new_experience():
    if request.method == "GET":
        return render_template("experience_form.html", experiencia=None, errors=[], nueva=True)

    id_ = slugify(request.form.get("id") or request.form.get("titulo_es", ""))
    if context.current_profile().experience(id_) is not None:
        errors = [_("Ya existe una experiencia con el identificador «%(id)s».", id=id_)]
        return render_template("experience_form.html", experiencia=None, errors=errors, nueva=True)

    experiencia = _experience_from_form(id_)
    errors = validation.validate_experience(experiencia)
    if errors:
        return render_template("experience_form.html", experiencia=experiencia, errors=errors, nueva=True)

    store.save_experience(context.root(), experiencia)
    flash(_("Experiencia «%(titulo)s» guardada.", titulo=experiencia.title["es"]))
    return redirect(url_for("ancla.view_profile"))


@bp.route("/perfil/experiencias/<id_>/editar", methods=["GET", "POST"])
def edit_experience(id_: str):
    existente = context.current_profile().experience(id_)
    if existente is None:
        flash(_("No existe la experiencia «%(id)s».", id=id_))
        return redirect(url_for("ancla.view_profile"))

    if request.method == "GET":
        return render_template("experience_form.html", experiencia=existente, errors=[], nueva=False)

    experiencia = _experience_from_form(id_)
    errors = validation.validate_experience(experiencia)
    if errors:
        return render_template("experience_form.html", experiencia=experiencia, errors=errors, nueva=False)

    store.save_experience(context.root(), experiencia)
    flash(_("Experiencia «%(titulo)s» actualizada.", titulo=experiencia.title["es"]))
    return redirect(url_for("ancla.view_profile"))


@bp.route("/perfil/experiencias/<id_>/borrar", methods=["POST"])
def delete_experience(id_: str):
    store.delete_experience(context.root(), id_)
    flash(_("Experiencia borrada."))
    return redirect(url_for("ancla.view_profile"))


@bp.route("/perfil/experiencias/borrar-todas", methods=["POST"])
def delete_all_experiences():
    n = len(context.current_profile().experiences)
    store.delete_all_experiences(context.root())
    flash(_("%(cantidad)s experiencia(s) borradas.", cantidad=n) if n else _("No había ninguna experiencia que borrar."))
    return redirect(url_for("ancla.view_profile"))


@bp.route("/perfil/keywords", methods=["POST"])
def suggest_keywords():
    """Suggests keywords for the skill or experience currently being written.

    Always returns 200 with a list (empty if it could not get one): this is
    a form helper, and a failure here must not interrupt whoever is
    writing. The user reviews and expands whatever is proposed — it is
    never saved on its own.
    """
    datos = request.get_json(silent=True) or {}
    ajustes = context.current_settings()
    if not ajustes.configured():
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
        cliente = create_client(ajustes.proveedor, ajustes.clave_api, ajustes.url_base, ajustes.modelo)
    except Exception:
        return jsonify({"keywords": [], "aviso": _("No se pudo contactar con el proveedor.")})

    if datos.get("tipo") == "experiencia":
        sugerencia = keywords.suggest_for_experience(
            cliente,
            titulo=datos.get("titulo", ""),
            bullets=lines_to_list(datos.get("bullets", "")),
            stack=datos.get("stack", ""),
        )
    else:
        sugerencia = keywords.suggest_for_skill(
            cliente,
            nombre_es=datos.get("nombre_es", ""),
            nombre_en=datos.get("nombre_en", ""),
            categoria=datos.get("categoria", ""),
        )

    return jsonify({"keywords": sugerencia.keywords, "aviso": sugerencia.motivo})


def _skill_from_form(id_: str) -> Skill:
    f = request.form
    return Skill(
        id=id_,
        name=Bilingual(es=f.get("nombre_es", "").strip(), en=f.get("nombre_en", "").strip()),
        category=f.get("categoria", "").strip(),
        keywords=csv_to_list(f.get("keywords", "")),
    )


@bp.route("/perfil/skills/nueva", methods=["GET", "POST"])
def new_skill():
    if request.method == "GET":
        return render_template("skill_form.html", skill=None, errors=[], nueva=True)

    id_ = slugify(request.form.get("id") or request.form.get("nombre_es", ""))
    if context.current_profile().skill(id_) is not None:
        errors = [_("Ya existe una skill con el identificador «%(id)s».", id=id_)]
        return render_template("skill_form.html", skill=None, errors=errors, nueva=True)

    skill = _skill_from_form(id_)
    errors = validation.validate_skill(skill)
    if errors:
        return render_template("skill_form.html", skill=skill, errors=errors, nueva=True)

    store.save_skill(context.root(), skill)
    flash(_("Skill «%(nombre)s» guardada.", nombre=skill.name["es"]))
    return redirect(url_for("ancla.view_profile"))


@bp.route("/perfil/skills/<id_>/editar", methods=["GET", "POST"])
def edit_skill(id_: str):
    existente = context.current_profile().skill(id_)
    if existente is None:
        flash(_("No existe la skill «%(id)s».", id=id_))
        return redirect(url_for("ancla.view_profile"))

    if request.method == "GET":
        return render_template("skill_form.html", skill=existente, errors=[], nueva=False)

    skill = _skill_from_form(id_)
    errors = validation.validate_skill(skill)
    if errors:
        return render_template("skill_form.html", skill=skill, errors=errors, nueva=False)

    store.save_skill(context.root(), skill)
    flash(_("Skill «%(nombre)s» actualizada.", nombre=skill.name["es"]))
    return redirect(url_for("ancla.view_profile"))


@bp.route("/perfil/skills/<id_>/borrar", methods=["POST"])
def delete_skill(id_: str):
    store.delete_skill(context.root(), id_)
    flash(_("Skill borrada."))
    return redirect(url_for("ancla.view_profile"))


@bp.route("/perfil/skills/borrar-todas", methods=["POST"])
def delete_all_skills():
    n = len(context.current_profile().skills)
    store.delete_all_skills(context.root())
    flash(_("%(cantidad)s skill(s) borradas.", cantidad=n) if n else _("No había ninguna skill que borrar."))
    return redirect(url_for("ancla.view_profile"))


# --------------------------------------------------------------------------
# Personal skills: same `Skill` type, separate folder and validation. Never
# go through the selection engine — always shown in full on the Proposal,
# never chosen by the AI. See `Profile` in modelo.py.
# --------------------------------------------------------------------------


@bp.route("/perfil/skills-personales/nueva", methods=["GET", "POST"])
def new_personal_skill():
    if request.method == "GET":
        return render_template("personal_skill_form.html", skill=None, errors=[], nueva=True)

    id_ = slugify(request.form.get("id") or request.form.get("nombre_es", ""))
    if context.current_profile().personal_skill(id_) is not None:
        errors = [_("Ya existe una skill personal con el identificador «%(id)s».", id=id_)]
        return render_template("personal_skill_form.html", skill=None, errors=errors, nueva=True)

    skill = _skill_from_form(id_)
    errors = validation.validate_personal_skill(skill)
    if errors:
        return render_template("personal_skill_form.html", skill=skill, errors=errors, nueva=True)

    store.save_personal_skill(context.root(), skill)
    flash(_("Skill personal «%(nombre)s» guardada.", nombre=skill.name["es"]))
    return redirect(url_for("ancla.view_profile"))


@bp.route("/perfil/skills-personales/<id_>/editar", methods=["GET", "POST"])
def edit_personal_skill(id_: str):
    existente = context.current_profile().personal_skill(id_)
    if existente is None:
        flash(_("No existe la skill personal «%(id)s».", id=id_))
        return redirect(url_for("ancla.view_profile"))

    if request.method == "GET":
        return render_template("personal_skill_form.html", skill=existente, errors=[], nueva=False)

    skill = _skill_from_form(id_)
    errors = validation.validate_personal_skill(skill)
    if errors:
        return render_template("personal_skill_form.html", skill=skill, errors=errors, nueva=False)

    store.save_personal_skill(context.root(), skill)
    flash(_("Skill personal «%(nombre)s» actualizada.", nombre=skill.name["es"]))
    return redirect(url_for("ancla.view_profile"))


@bp.route("/perfil/skills-personales/<id_>/borrar", methods=["POST"])
def delete_personal_skill(id_: str):
    store.delete_personal_skill(context.root(), id_)
    flash(_("Skill personal borrada."))
    return redirect(url_for("ancla.view_profile"))


@bp.route("/perfil/skills-personales/borrar-todas", methods=["POST"])
def delete_all_personal_skills():
    n = len(context.current_profile().personal_skills)
    store.delete_all_personal_skills(context.root())
    flash(
        _("%(cantidad)s skill(s) personal(es) borradas.", cantidad=n)
        if n
        else _("No había ninguna skill personal que borrar.")
    )
    return redirect(url_for("ancla.view_profile"))


# --------------------------------------------------------------------------
# Languages: same approach as personal skills (separate catalog, always
# shown in full on the Proposal), plus an extra level field.
# --------------------------------------------------------------------------


def _language_from_form(id_: str) -> SpokenLanguage:
    f = request.form
    return SpokenLanguage(
        id=id_,
        name=Bilingual(es=f.get("nombre_es", "").strip(), en=f.get("nombre_en", "").strip()),
        level=Bilingual(es=f.get("nivel_es", "").strip(), en=f.get("nivel_en", "").strip()),
        keywords=csv_to_list(f.get("keywords", "")),
    )


@bp.route("/perfil/idiomas/nuevo", methods=["GET", "POST"])
def new_language():
    if request.method == "GET":
        return render_template("language_form.html", idioma=None, errors=[], nuevo=True)

    id_ = slugify(request.form.get("id") or request.form.get("nombre_es", ""))
    if context.current_profile().language(id_) is not None:
        errors = [_("Ya existe un idioma con el identificador «%(id)s».", id=id_)]
        return render_template("language_form.html", idioma=None, errors=errors, nuevo=True)

    idioma = _language_from_form(id_)
    errors = validation.validate_language(idioma)
    if errors:
        return render_template("language_form.html", idioma=idioma, errors=errors, nuevo=True)

    store.save_language(context.root(), idioma)
    flash(_("Idioma «%(nombre)s» guardado.", nombre=idioma.name["es"]))
    return redirect(url_for("ancla.view_profile"))


@bp.route("/perfil/idiomas/<id_>/editar", methods=["GET", "POST"])
def edit_language(id_: str):
    existente = context.current_profile().language(id_)
    if existente is None:
        flash(_("No existe el idioma «%(id)s».", id=id_))
        return redirect(url_for("ancla.view_profile"))

    if request.method == "GET":
        return render_template("language_form.html", idioma=existente, errors=[], nuevo=False)

    idioma = _language_from_form(id_)
    errors = validation.validate_language(idioma)
    if errors:
        return render_template("language_form.html", idioma=idioma, errors=errors, nuevo=False)

    store.save_language(context.root(), idioma)
    flash(_("Idioma «%(nombre)s» actualizado.", nombre=idioma.name["es"]))
    return redirect(url_for("ancla.view_profile"))


@bp.route("/perfil/idiomas/<id_>/borrar", methods=["POST"])
def delete_language(id_: str):
    store.delete_language(context.root(), id_)
    flash(_("Idioma borrado."))
    return redirect(url_for("ancla.view_profile"))


@bp.route("/perfil/idiomas/borrar-todos", methods=["POST"])
def delete_all_languages():
    n = len(context.current_profile().languages)
    store.delete_all_languages(context.root())
    flash(_("%(cantidad)s idioma(s) borrados.", cantidad=n) if n else _("No había ningún idioma que borrar."))
    return redirect(url_for("ancla.view_profile"))


# --------------------------------------------------------------------------
# Education: same approach as languages (separate catalog, always shown in
# full, never chosen by the AI). No keywords: nothing checks education
# against a job posting's gaps.
# --------------------------------------------------------------------------


def _education_from_form(id_: str) -> Education:
    f = request.form
    return Education(
        id=id_,
        title=Bilingual(es=f.get("titulo_es", "").strip(), en=f.get("titulo_en", "").strip()),
        institution=Bilingual(es=f.get("centro_es", "").strip(), en=f.get("centro_en", "").strip()),
        period=Bilingual(es=f.get("periodo_es", "").strip(), en=f.get("periodo_en", "").strip()),
    )


@bp.route("/perfil/educacion/nueva", methods=["GET", "POST"])
def new_education():
    if request.method == "GET":
        return render_template("education_form.html", educacion=None, errors=[], nueva=True)

    id_ = slugify(request.form.get("id") or request.form.get("titulo_es", ""))
    if context.current_profile().education_entry(id_) is not None:
        errors = [_("Ya existe una educación con el identificador «%(id)s».", id=id_)]
        return render_template("education_form.html", educacion=None, errors=errors, nueva=True)

    educacion = _education_from_form(id_)
    errors = validation.validate_education(educacion)
    if errors:
        return render_template("education_form.html", educacion=educacion, errors=errors, nueva=True)

    store.save_education(context.root(), educacion)
    flash(_("Educación «%(titulo)s» guardada.", titulo=educacion.title["es"]))
    return redirect(url_for("ancla.view_profile"))


@bp.route("/perfil/educacion/<id_>/editar", methods=["GET", "POST"])
def edit_education(id_: str):
    existente = context.current_profile().education_entry(id_)
    if existente is None:
        flash(_("No existe la educación «%(id)s».", id=id_))
        return redirect(url_for("ancla.view_profile"))

    if request.method == "GET":
        return render_template("education_form.html", educacion=existente, errors=[], nueva=False)

    educacion = _education_from_form(id_)
    errors = validation.validate_education(educacion)
    if errors:
        return render_template("education_form.html", educacion=educacion, errors=errors, nueva=False)

    store.save_education(context.root(), educacion)
    flash(_("Educación «%(titulo)s» actualizada.", titulo=educacion.title["es"]))
    return redirect(url_for("ancla.view_profile"))


@bp.route("/perfil/educacion/<id_>/borrar", methods=["POST"])
def delete_education(id_: str):
    store.delete_education(context.root(), id_)
    flash(_("Educación borrada."))
    return redirect(url_for("ancla.view_profile"))


@bp.route("/perfil/educacion/borrar-todas", methods=["POST"])
def delete_all_education():
    n = len(context.current_profile().education)
    store.delete_all_education(context.root())
    flash(_("%(cantidad)s educación(es) borradas.", cantidad=n) if n else _("No había ninguna educación que borrar."))
    return redirect(url_for("ancla.view_profile"))


# --------------------------------------------------------------------------
# Contact: free-form lines (phone, email, city, LinkedIn...), not bilingual
# — a phone number or a URL reads the same in any language. Same "always
# shown in full" rule as everything else in this section.
# --------------------------------------------------------------------------


@bp.route("/perfil/contacto", methods=["GET", "POST"])
def edit_contact():
    if request.method == "GET":
        perfil = context.current_profile()
        return render_template(
            "contact_form.html", nombre=perfil.name, titular=perfil.headline, contacto=perfil.contact
        )

    nombre = request.form.get("nombre", "").strip()
    titular = Bilingual(
        es=request.form.get("titular_es", "").strip(),
        en=request.form.get("titular_en", "").strip(),
    )
    lineas = lines_to_list(request.form.get("lineas", ""))
    store.save_contact(context.root(), nombre, titular, lineas)
    flash(_("Contacto guardado."))
    return redirect(url_for("ancla.view_profile"))


# --------------------------------------------------------------------------
# Photo: a single file, replaced whole on every upload (see
# `profile/store.py::save_photo`).
# --------------------------------------------------------------------------


@bp.route("/perfil/foto", methods=["POST"])
def upload_photo():
    fichero = request.files.get("foto")
    if fichero is None or not fichero.filename:
        flash(_("No se ha seleccionado ninguna foto."))
        return redirect(url_for("ancla.view_profile"))

    store.save_photo(context.root(), fichero.filename, fichero.read())
    flash(_("Foto de perfil guardada."))
    return redirect(url_for("ancla.view_profile"))


@bp.route("/perfil/foto/borrar", methods=["POST"])
def delete_photo():
    store.delete_photo(context.root())
    flash(_("Foto de perfil borrada."))
    return redirect(url_for("ancla.view_profile"))


@bp.route("/perfil/foto/archivo")
def photo_file():
    ruta = store.photo_path(context.root())
    if ruta is None:
        abort(404)
    return send_file(ruta)


@bp.route("/perfil/sobre-mi", methods=["GET", "POST"])
def edit_about_me():
    perfil = context.current_profile()
    if request.method == "GET":
        return render_template("about_me_form.html", sobre_mi=perfil.about_me, errors=[])

    f = request.form
    sobre_mi = AboutMe(template=Bilingual(es=f.get("plantilla_es", ""), en=f.get("plantilla_en", "")))
    errors = validation.validate_about_me(sobre_mi)
    if errors:
        return render_template("about_me_form.html", sobre_mi=sobre_mi, errors=errors)

    store.save_about_me(context.root(), sobre_mi)
    flash(_("Plantilla de «Sobre mí» guardada."))
    return redirect(url_for("ancla.view_profile"))
