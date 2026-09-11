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
from ancla.profile import store, importer, gaps, translation, validation
from ancla.profile.extraction import ExtractionError, extract_text
from ancla.profile.model import (
    LANGUAGES,
    AboutMe,
    Bilingual,
    Education,
    Experience,
    Language,
    Skill,
    SpokenLanguage,
)
from ancla.text import normalize
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

    idioma = _chosen_language(request.form.get("idioma_cv", ""), texto_cv)
    perfil = context.current_profile()
    resultado = importer.analyze_cv(cliente, texto_cv, perfil, idioma)

    sobre_mi = resultado.sobre_mi
    avisos = list(resultado.avisos)
    if sobre_mi is not None:
        # Same accelerator as the manual "About me" editor
        # (`suggest_about_me_gaps`), called automatically here so the
        # review screen shows the huecos already placed instead of a raw
        # paragraph. Both the profile's existing technical skills and the
        # ones this same CV just proposed are offered: a paragraph copied
        # from the CV can equally reference a skill already saved from a
        # previous import or one this one is proposing for the first time,
        # and `gaps.py` already deduplicates names on its own.
        propuesta = gaps.suggest_gaps(cliente, sobre_mi, resultado.skills + perfil.skills)
        sobre_mi = propuesta.about_me
        avisos += propuesta.avisos

    contacto = resultado.contacto
    lote = modulo_importacion.ImportBatch(
        experiencias=resultado.experiencias,
        skills=resultado.skills,
        skills_personales=resultado.skills_personales,
        idiomas=resultado.idiomas,
        educacion=resultado.educacion,
        contacto_nombre=contacto.name if contacto else "",
        contacto_titular=contacto.headline if contacto else Bilingual(es="", en=""),
        contacto_lineas=contacto.lines if contacto else [],
        sobre_mi=sobre_mi,
        avisos=avisos,
        written=[idioma],
        resto=resultado.restante,
    )
    if not lote.has_content():
        for aviso in avisos:
            flash(aviso)
        return render_template("import.html", ia_configurada=ajustes.configured())

    modulo_importacion.save_import(context.root(), lote)
    return redirect(url_for("ancla.review_import"))


def _chosen_language(elegido: str, texto_cv: str) -> Language:
    """What the user picked, or what the text looks like if they left it on
    automatic. Anything else that arrives in the form is treated as
    automatic rather than rejected: the field is a convenience, and a
    hand-crafted value should not cost the user their upload."""
    if elegido in LANGUAGES:
        return elegido
    return importer.detect_language(texto_cv)


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
    return render_template(
        "import_review.html",
        importacion=importacion,
        idioma_importado=importacion.written[0],
        falta_idioma=_missing_language(importacion),
    )


def _contact_from_form(form, importacion: modulo_importacion.ImportBatch) -> tuple[str, Bilingual[str], list[str]]:
    """Name, headline and lines with whatever the user edited on the review
    screen — falls back to the imported values for a field the form did not
    send, same convention as `_edited_experience` and the rest."""
    nombre = form.get("contacto-nombre", importacion.contacto_nombre).strip()
    titular = Bilingual(
        es=form.get("contacto-titular_es", importacion.contacto_titular["es"]).strip(),
        en=form.get("contacto-titular_en", importacion.contacto_titular["en"]).strip(),
    )
    lineas = lines_to_list(form.get("contacto-lineas", "\n".join(importacion.contacto_lineas)))
    return nombre, titular, lineas


def _about_me_from_form(form, importacion: modulo_importacion.ImportBatch) -> AboutMe | None:
    """`None` when nothing was proposed — there is no card and no fields on
    the review screen to read edits from."""
    if importacion.sobre_mi is None:
        return None
    return AboutMe(
        template=Bilingual(
            es=form.get("sobre-mi-plantilla_es", importacion.sobre_mi.template["es"]),
            en=form.get("sobre-mi-plantilla_en", importacion.sobre_mi.template["en"]),
        )
    )


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

    if request.form.get("contacto") == "1":
        nombre, titular, lineas = _contact_from_form(request.form, importacion)
        store.save_contact(context.root(), nombre, titular, lineas)
        guardadas += 1

    if request.form.get("sobre-mi") == "1":
        sobre_mi = _about_me_from_form(request.form, importacion)
        # `sobre_mi` is only `None` when the checkbox itself could not have
        # been rendered (no card without a proposal), so this never fires
        # in practice — kept as a guard, not a silent skip.
        if sobre_mi is not None:
            if validation.validate_about_me(sobre_mi).errors:
                con_error += 1
            else:
                store.save_about_me(context.root(), sobre_mi)
                guardadas += 1

    modulo_importacion.delete_import(context.root())

    if guardadas:
        flash(_("%(cantidad)s elemento(s) añadidos al perfil.", cantidad=guardadas))
    if con_error:
        flash(
            _(
                "%(cantidad)s elemento(s) no se pudieron guardar por falta de datos "
                "(faltaba el nombre, el periodo o las palabras clave). Añádelos a mano "
                "en «Mi perfil».",
                cantidad=con_error,
            )
        )
    return redirect(url_for("ancla.view_profile"))


def _edited_experience(form, prefijo: str, original: Experience) -> Experience:
    """Experience with form edits applied, preserving original values where not edited.

    Bullets follow a different fallback rule from other fields: they default to
    an empty list if not found in the form, rather than to `original.bullets`.
    This is intentional. Bullets are the critical field of an experience and
    require an explicit user decision — an empty textarea means the user
    consciously removed them, not that they forgot to edit. This matters in
    `_apply_edits` (used for translation), which processes all candidates
    regardless of checkbox state: if a candidate's checkbox is unchecked, its
    HTML fields don't appear in the form, and other fields preserve the original
    while bullets become empty. That's correct: the user chose not to save it,
    and an empty bullets list is the safest choice for an untouched candidate.
    """
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
    simply falls back to the original value (an empty pair), same as in
    the manual "New personal skill" form."""
    return replace(
        original,
        name=Bilingual(
            es=form.get(f"{prefijo}-nombre_es", original.name["es"]).strip(),
            en=form.get(f"{prefijo}-nombre_en", original.name["en"]).strip(),
        ),
        category=Bilingual(
            es=form.get(f"{prefijo}-categoria_es", original.category["es"]).strip(),
            en=form.get(f"{prefijo}-categoria_en", original.category["en"]).strip(),
        ),
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


# The field that carries an entry's name, for the five categories: "title"
# for the two with a title (experiences, education), "name" for the three
# named by a single word (skills, personal skills, languages). Used only to
# de-duplicate a second import's candidates against the batch's own — the
# profile-level duplicate check already keyed on this same distinction lives
# in `importer.py`, and this mirrors it rather than reaching into that
# module's private helpers for what is a one-line lookup.
_ATRIBUTO_NOMBRE = {
    "experiencias": "title", "skills": "name", "skills_personales": "name",
    "idiomas": "name", "educacion": "title",
}


def _candidates(lote: modulo_importacion.ImportBatch, seccion: _ReviewSection) -> list:
    return getattr(lote, seccion.attribute)


def _sin_repetidos_en_lote(nuevas: list, existentes: list, atributo: str) -> list:
    """`nuevas` with whatever `existentes` already names (ES or EN,
    case/accent-insensitive) dropped.

    Importing a second part only asks `analyze_cv` to compare against the
    saved profile, because that is the only catalog it knows about — the
    first part's own candidates are still unsaved, sitting in this same
    batch. Without this, a skill mentioned in both halves of a CV (its
    summary near the top, its stack lower down) would show up twice on the
    review screen.
    """
    ya = {
        normalize(valor)
        for item in existentes
        for valor in (getattr(item, atributo)["es"], getattr(item, atributo)["en"])
        if valor
    }
    return [
        candidata for candidata in nuevas
        if not any(
            normalize(valor) in ya
            for valor in (getattr(candidata, atributo)["es"], getattr(candidata, atributo)["en"])
            if valor
        )
    ]


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
        # Only errors stop a candidate: an entry written in a single
        # language is unfinished, not wrong, and the whole point of
        # importing in one language is being able to save it that way.
        if seccion.validate(editada).errors:
            con_error += 1
            continue
        seccion.save(context.root(), editada)
        guardadas += 1
    return guardadas, con_error


@bp.route("/perfil/importar/traducir", methods=["POST"])
def translate_import():
    """The second, optional call: the whole batch at once, into the language
    it is not written in.

    One call for every category together, and only for what is missing: it
    is the same per-minute budget as the import, and it is being spent a
    minute later only because reviewing the first screen took that long.
    """
    importacion = modulo_importacion.load_import(context.root())
    if importacion is None:
        flash(_("Esa importación ya no está disponible, vuelve a subir el CV."))
        return redirect(url_for("ancla.import_cv"))

    destino = _missing_language(importacion)
    if destino is None:
        flash(_("Esta importación ya está en los dos idiomas."))
        return redirect(url_for("ancla.review_import"))

    ajustes = context.current_settings()
    try:
        cliente = create_client(ajustes.proveedor, ajustes.clave_api, ajustes.url_base, ajustes.modelo)
    except AIError as error:
        flash(str(error))
        return redirect(url_for("ancla.review_import"))

    _apply_edits(request.form, importacion)
    secciones = importacion.sections()
    # Every category in one request, not one per category: five calls would
    # need five minutes of quota to do what fits in a single answer.
    resultado = translation.translate(
        cliente, [candidata for seccion in secciones for candidata in seccion], destino
    )
    desde = 0
    for seccion in secciones:
        seccion[:] = resultado.entries[desde : desde + len(seccion)]
        desde += len(seccion)

    for aviso in resultado.avisos:
        flash(aviso)
    if not resultado.avisos:
        importacion.written = [
            idioma for idioma in LANGUAGES
            if idioma in (*importacion.written, destino)
        ]
    modulo_importacion.save_import(context.root(), importacion)
    return redirect(url_for("ancla.review_import"))


def _apply_edits(form, lote: modulo_importacion.ImportBatch) -> None:
    """Carries whatever the user corrected by hand into the batch.

    The review screen's two buttons submit the same form, so translating
    must not throw away the edits that saving would have kept. Unlike
    saving, this ignores the checkboxes: unticking one means "do not add
    this to my profile", not "forget what I typed in it".
    """
    for seccion in SECTIONS:
        candidatas = _candidates(lote, seccion)
        candidatas[:] = [
            seccion.edited(form, f"{seccion.prefix}-{indice}", candidata)
            for indice, candidata in enumerate(candidatas)
        ]
    lote.contacto_nombre, lote.contacto_titular, lote.contacto_lineas = _contact_from_form(form, lote)
    lote.sobre_mi = _about_me_from_form(form, lote)


def _missing_language(importacion: modulo_importacion.ImportBatch) -> Language | None:
    faltan = [idioma for idioma in LANGUAGES if idioma not in importacion.written]
    return faltan[0] if faltan else None


@bp.route("/perfil/importar/segunda-parte", methods=["POST"])
def import_second_part():
    """Analyses whatever `_recortar` had to leave out of the first call, as a
    second, independent one.

    Same reasoning as `translate_import`: it is another call against the
    same per-minute budget, spent later only because reviewing the first
    part took a minute on its own — and the section boundary it starts on
    was already computed for free when the first part was cut, so there is
    no new text to locate here.

    The results land in the very same batch under review rather than a
    screen of their own: they are appended to each category's list, so the
    next render of `review_import` simply shows more cards. If the leftover
    was itself too long for one call, `importacion.resto` comes back
    non-empty again and the button on the review screen stays available for
    a third part, without this needing to special-case it.
    """
    importacion = modulo_importacion.load_import(context.root())
    if importacion is None:
        flash(_("Esa importación ya no está disponible, vuelve a subir el CV."))
        return redirect(url_for("ancla.import_cv"))
    if not importacion.resto:
        flash(_("No queda ninguna parte pendiente de importar de este CV."))
        return redirect(url_for("ancla.review_import"))

    ajustes = context.current_settings()
    try:
        cliente = create_client(ajustes.proveedor, ajustes.clave_api, ajustes.url_base, ajustes.modelo)
    except AIError as error:
        flash(str(error))
        return redirect(url_for("ancla.review_import"))

    _apply_edits(request.form, importacion)
    resultado = importer.analyze_cv(
        cliente, importacion.resto, context.current_profile(), importacion.written[0]
    )
    for seccion in SECTIONS:
        atributo = seccion.attribute
        nuevas = _sin_repetidos_en_lote(
            getattr(resultado, atributo), getattr(importacion, atributo), _ATRIBUTO_NOMBRE[atributo]
        )
        getattr(importacion, atributo).extend(nuevas)
    importacion.avisos.extend(resultado.avisos)
    importacion.resto = resultado.restante
    modulo_importacion.save_import(context.root(), importacion)
    return redirect(url_for("ancla.review_import"))


@bp.route("/perfil/importar/descartar", methods=["POST"])
def discard_import():
    modulo_importacion.delete_import(context.root())
    flash(_("Importación descartada. No se ha guardado nada."))
    return redirect(url_for("ancla.import_cv"))
