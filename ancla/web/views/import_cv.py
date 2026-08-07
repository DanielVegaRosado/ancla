"""Import screen: upload your CV (PDF/Word) or paste the text, the AI
proposes experiences and skills, and you confirm what to save before it
touches the profile.

Two steps with ephemeral state in between (`web/importacion.py`), same
pattern as Adapt → Proposal with the draft: nothing is saved to the profile
until the second step's explicit confirmation.
"""
from __future__ import annotations

from dataclasses import replace

from flask import flash, redirect, render_template, request, url_for
from flask_babel import gettext as _

from ancla.ai.client import AIError
from ancla.profile import store, importer, validation
from ancla.profile.extraction import ExtractionError, extract_text
from ancla.profile.model import Bilingual, Experience, Skill, SpokenLanguage
from ancla.web import context
from ancla.web import import_batch as modulo_importacion
from ancla.web.blueprint import bp
from ancla.web.providers import create_client
from ancla.web.util import lines_to_list


@bp.route("/perfil/importar", methods=["GET", "POST"])
def import_cv():
    if request.method == "GET":
        return render_template("import.html")

    fichero = request.files.get("fichero")
    texto_pegado = request.form.get("texto", "").strip()

    try:
        texto_cv = _input_text(fichero, texto_pegado)
    except ExtractionError as error:
        flash(str(error))
        return render_template("import.html")

    ajustes = context.current_settings()
    try:
        cliente = create_client(ajustes.proveedor, ajustes.clave_api, ajustes.url_base, ajustes.modelo)
    except AIError as error:
        flash(str(error))
        return render_template("import.html")
    if not cliente.available():
        flash(_("Configura tu clave de API en Ajustes antes de importar un CV."))
        return redirect(url_for("ancla.view_settings"))

    resultado = importer.analyze_cv(cliente, texto_cv, context.current_profile())
    if not any(
        (
            resultado.experiencias,
            resultado.skills,
            resultado.skills_personales,
            resultado.idiomas,
        )
    ):
        for aviso in resultado.avisos:
            flash(aviso)
        return render_template("import.html")

    modulo_importacion.save_import(
        context.root(),
        modulo_importacion.ImportBatch(
            experiencias=resultado.experiencias,
            skills=resultado.skills,
            skills_personales=resultado.skills_personales,
            idiomas=resultado.idiomas,
            avisos=resultado.avisos,
        ),
    )
    return redirect(url_for("ancla.review_import"))


def _input_text(fichero, texto_pegado: str) -> str:
    if fichero is not None and fichero.filename:
        return extract_text(fichero.filename, fichero.read())
    if texto_pegado:
        return texto_pegado
    raise ExtractionError(_("Sube un fichero o pega el texto de tu CV antes de continuar."))


@bp.route("/perfil/importar/revisar")
def review_import():
    importacion = modulo_importacion.load_import(context.root())
    if importacion is None:
        flash(_("No hay ninguna importación pendiente de revisar."))
        return redirect(url_for("ancla.import_cv"))
    return render_template("import_review.html", importacion=importacion)


@bp.route("/perfil/importar/guardar", methods=["POST"])
def save_import():
    importacion = modulo_importacion.load_import(context.root())
    if importacion is None:
        flash(_("Esa importación ya no está disponible, vuelve a subir el CV."))
        return redirect(url_for("ancla.import_cv"))

    guardadas = 0
    con_error = 0
    for indice, experiencia in enumerate(importacion.experiencias):
        if request.form.get(f"exp-{indice}") != "1":
            continue
        editada = _edited_experience(request.form, indice, experiencia)
        errors = validation.validate_experience(editada)
        if errors:
            con_error += 1
            continue
        store.save_experience(context.root(), editada)
        guardadas += 1

    for indice, skill in enumerate(importacion.skills):
        if request.form.get(f"skill-{indice}") != "1":
            continue
        editada = _edited_skill(request.form, "skill", indice, skill)
        errors = validation.validate_skill(editada)
        if errors:
            con_error += 1
            continue
        store.save_skill(context.root(), editada)
        guardadas += 1

    for indice, skill in enumerate(importacion.skills_personales):
        if request.form.get(f"skillpersonal-{indice}") != "1":
            continue
        editada = _edited_skill(request.form, "skillpersonal", indice, skill)
        errors = validation.validate_personal_skill(editada)
        if errors:
            con_error += 1
            continue
        store.save_personal_skill(context.root(), editada)
        guardadas += 1

    for indice, idioma in enumerate(importacion.idiomas):
        if request.form.get(f"idioma-{indice}") != "1":
            continue
        editado = _edited_language(request.form, indice, idioma)
        errors = validation.validate_language(editado)
        if errors:
            con_error += 1
            continue
        store.save_language(context.root(), editado)
        guardadas += 1

    modulo_importacion.delete_import(context.root())

    if guardadas:
        flash(_("%(cantidad)s elemento(s) añadidos al perfil.", cantidad=guardadas))
    if con_error:
        flash(
            _(
                "%(cantidad)s elemento(s) no se pudieron guardar por falta de datos "
                "(faltaba el nombre en algún idioma, o palabras clave). Añádelos a mano "
                "en «Mi perfil».",
                cantidad=con_error,
            )
        )
    return redirect(url_for("ancla.view_profile"))


def _edited_experience(form, indice: int, original: Experience) -> Experience:
    prefijo = f"exp-{indice}"
    return replace(
        original,
        title=Bilingual(
            es=form.get(f"{prefijo}-titulo_es", original.title["es"]).strip(),
            en=form.get(f"{prefijo}-titulo_en", original.title["en"]).strip(),
        ),
        period=Bilingual(
            es=form.get(f"{prefijo}-periodo_es", original.period["es"]).strip(),
            en=form.get(f"{prefijo}-periodo_en", original.period["en"]).strip(),
        ),
        bullets=Bilingual(
            es=lines_to_list(form.get(f"{prefijo}-bullets_es", "")),
            en=lines_to_list(form.get(f"{prefijo}-bullets_en", "")),
        ),
        stack=Bilingual(
            es=form.get(f"{prefijo}-stack_es", original.stack["es"]).strip(),
            en=form.get(f"{prefijo}-stack_en", original.stack["en"]).strip(),
        ),
    )


def _edited_skill(form, tipo: str, indice: int, original: Skill) -> Skill:
    """Used for both technical and personal skills: same fields, the only
    difference is the form prefix (`skill-N` / `skillpersonal-N`). A
    personal skill has no category field in the template — `form.get`
    simply falls back to the original value (an empty string), same as in
    the manual "New personal skill" form."""
    prefijo = f"{tipo}-{indice}"
    return replace(
        original,
        name=Bilingual(
            es=form.get(f"{prefijo}-nombre_es", original.name["es"]).strip(),
            en=form.get(f"{prefijo}-nombre_en", original.name["en"]).strip(),
        ),
        category=form.get(f"{prefijo}-categoria", original.category).strip(),
    )


def _edited_language(form, indice: int, original: SpokenLanguage) -> SpokenLanguage:
    prefijo = f"idioma-{indice}"
    return replace(
        original,
        name=Bilingual(
            es=form.get(f"{prefijo}-nombre_es", original.name["es"]).strip(),
            en=form.get(f"{prefijo}-nombre_en", original.name["en"]).strip(),
        ),
        level=Bilingual(
            es=form.get(f"{prefijo}-nivel_es", original.level["es"]).strip(),
            en=form.get(f"{prefijo}-nivel_en", original.level["en"]).strip(),
        ),
    )


@bp.route("/perfil/importar/descartar", methods=["POST"])
def discard_import():
    modulo_importacion.delete_import(context.root())
    flash(_("Importación descartada. No se ha guardado nada."))
    return redirect(url_for("ancla.import_cv"))
