"""Import screen: upload your CV (PDF/Word) or paste the text, the AI
proposes experiences and skills, and you confirm what to save before it
touches the profile.

Two steps with ephemeral state in between (`web/importacion.py`), same
pattern as Adapt → Proposal with the draft: nothing is saved to the profile
until the second step's explicit confirmation.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

from flask import flash, redirect, render_template, request, url_for
from flask_babel import gettext as _

from ancla.ai.client import AIError
from ancla.profile import store, importer, validation
from ancla.profile.extraction import ExtractionError, extract_text
from ancla.profile.model import Bilingual, Education, Experience, Skill, SpokenLanguage
from ancla.web import context
from ancla.web import import_batch as modulo_importacion
from ancla.web.blueprint import bp
from ancla.web.providers import create_client
from ancla.web.util import lines_to_list


@bp.route("/perfil/importar", methods=["GET", "POST"])
def import_cv():
    ajustes = context.current_settings()
    if request.method == "GET":
        return render_template("import.html", ia_configurada=ajustes.configured())

    fichero = request.files.get("fichero")
    texto_pegado = request.form.get("texto", "").strip()

    try:
        texto_cv = _input_text(fichero, texto_pegado)
    except ExtractionError as error:
        flash(str(error))
        return render_template("import.html", ia_configurada=ajustes.configured())

    try:
        cliente = create_client(ajustes.proveedor, ajustes.clave_api, ajustes.url_base, ajustes.modelo)
    except AIError as error:
        flash(str(error))
        return render_template("import.html", ia_configurada=ajustes.configured())
    if not cliente.available():
        flash(_("Configura tu clave de API en Ajustes antes de importar un CV."))
        return redirect(url_for("ancla.view_settings"))

    resultado = importer.analyze_cv(cliente, texto_cv, context.current_profile())
    lote = modulo_importacion.ImportBatch(
        experiencias=resultado.experiencias,
        skills=resultado.skills,
        skills_personales=resultado.skills_personales,
        idiomas=resultado.idiomas,
        educacion=resultado.educacion,
        avisos=resultado.avisos,
    )
    if not any(_candidates(lote, seccion) for seccion in SECTIONS):
        for aviso in resultado.avisos:
            flash(aviso)
        return render_template("import.html", ia_configurada=ajustes.configured())

    modulo_importacion.save_import(context.root(), lote)
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
    for seccion in SECTIONS:
        nuevas, fallidas = _save_section(request.form, importacion, seccion)
        guardadas += nuevas
        con_error += fallidas

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


def _edited_experience(form, prefijo: str, original: Experience) -> Experience:
    return replace(
        original,
        title=Bilingual(
            es=form.get(f"{prefijo}-titulo_es", original.title["es"]).strip(),
            en=form.get(f"{prefijo}-titulo_en", original.title["en"]).strip(),
        ),
        period_start=form.get(f"{prefijo}-periodo_inicio", original.period_start).strip(),
        period_end=form.get(f"{prefijo}-periodo_fin", original.period_end).strip(),
        bullets=Bilingual(
            es=lines_to_list(form.get(f"{prefijo}-bullets_es", "")),
            en=lines_to_list(form.get(f"{prefijo}-bullets_en", "")),
        ),
        stack=form.get(f"{prefijo}-stack", original.stack).strip(),
    )


def _edited_skill(form, prefijo: str, original: Skill) -> Skill:
    """Used for both technical and personal skills: same fields, the only
    difference is the form prefix (`skill-N` / `skillpersonal-N`). A
    personal skill has no category field in the template — `form.get`
    simply falls back to the original value (an empty string), same as in
    the manual "New personal skill" form."""
    return replace(
        original,
        name=Bilingual(
            es=form.get(f"{prefijo}-nombre_es", original.name["es"]).strip(),
            en=form.get(f"{prefijo}-nombre_en", original.name["en"]).strip(),
        ),
        category=form.get(f"{prefijo}-categoria", original.category).strip(),
    )


def _edited_language(form, prefijo: str, original: SpokenLanguage) -> SpokenLanguage:
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


def _edited_education(form, prefijo: str, original: Education) -> Education:
    return replace(
        original,
        title=Bilingual(
            es=form.get(f"{prefijo}-titulo_es", original.title["es"]).strip(),
            en=form.get(f"{prefijo}-titulo_en", original.title["en"]).strip(),
        ),
        institution=form.get(f"{prefijo}-centro", original.institution).strip(),
        period_start=form.get(f"{prefijo}-periodo_inicio", original.period_start).strip(),
        period_end=form.get(f"{prefijo}-periodo_fin", original.period_end).strip(),
    )


@dataclass(frozen=True)
class _ReviewSection:
    """One reviewable category of an import.

    The five categories differ only in where their candidates live in the
    batch, the form prefix their checkboxes and fields use, and which
    editor, validator and store function apply — so they are described once
    here instead of as five near-identical loops. A category missing from
    this table is one the review screen can show but never save.
    """

    attribute: str
    prefix: str
    edited: Callable
    validate: Callable
    save: Callable


SECTIONS = (
    _ReviewSection(
        "experiencias", "exp", _edited_experience,
        validation.validate_experience, store.save_experience,
    ),
    _ReviewSection(
        "skills", "skill", _edited_skill,
        validation.validate_skill, store.save_skill,
    ),
    _ReviewSection(
        "skills_personales", "skillpersonal", _edited_skill,
        validation.validate_personal_skill, store.save_personal_skill,
    ),
    _ReviewSection(
        "idiomas", "idioma", _edited_language,
        validation.validate_language, store.save_language,
    ),
    _ReviewSection(
        "educacion", "edu", _edited_education,
        validation.validate_education, store.save_education,
    ),
)


def _candidates(lote: modulo_importacion.ImportBatch, seccion: _ReviewSection) -> list:
    return getattr(lote, seccion.attribute)


def _save_section(form, lote: modulo_importacion.ImportBatch, seccion: _ReviewSection) -> tuple[int, int]:
    """Saves the candidates the user left checked. Returns
    `(saved, rejected)`: a candidate whose edits no longer validate is
    counted, not saved, so the screen can say how many were dropped."""
    guardadas = 0
    con_error = 0
    for indice, candidata in enumerate(_candidates(lote, seccion)):
        prefijo = f"{seccion.prefix}-{indice}"
        if form.get(prefijo) != "1":
            continue
        editada = seccion.edited(form, prefijo, candidata)
        if seccion.validate(editada):
            con_error += 1
            continue
        seccion.save(context.root(), editada)
        guardadas += 1
    return guardadas, con_error


@bp.route("/perfil/importar/descartar", methods=["POST"])
def discard_import():
    modulo_importacion.delete_import(context.root())
    flash(_("Importación descartada. No se ha guardado nada."))
    return redirect(url_for("ancla.import_cv"))
