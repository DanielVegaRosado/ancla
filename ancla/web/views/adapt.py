"""Adapt screen: paste a job posting, choose a language, generate the proposal."""
from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for
from flask_babel import gettext as _

from ancla.archive import repository as archivo
from ancla.ai.client import AIError
from ancla.profile import translation
from ancla.profile.model import LANGUAGES, N_EXPERIENCES, N_SKILLS
from ancla.selection import engine
from ancla.posting import analysis
from ancla.web import draft as modulo_borrador
from ancla.web import context
from ancla.web.blueprint import bp
from ancla.web.providers import create_client


@bp.route("/adaptar", methods=["GET", "POST"])
def adapt():
    if request.method == "GET":
        return render_template("adapt.html", vacante="", idioma="es")

    vacante_texto = request.form.get("vacante", "").strip()
    idioma = request.form.get("idioma", "es")
    if idioma not in LANGUAGES:
        idioma = "es"
    forzar = request.form.get("forzar") == "1"
    forzar_idioma = request.form.get("forzar_idioma") == "1"

    if not vacante_texto:
        flash(_("Pega el texto de la vacante antes de generar la propuesta."))
        return render_template("adapt.html", vacante=vacante_texto, idioma=idioma)

    perfil = context.current_profile()
    if perfil.is_empty() or perfil.about_me is None:
        flash(
            _(
                "Tu perfil todavía no tiene experiencia, skills o «Sobre mí». "
                "Complétalo antes de adaptar un CV."
            )
        )
        return redirect(url_for("ancla.view_profile"))

    # Said before the call, never fixed by it: translating here would spend
    # a call nobody asked for, right before the big one. The user decides,
    # but knowing which entries would come out blank.
    if not forzar_idioma:
        sin_traducir = _untranslated_names(perfil, idioma)
        if sin_traducir:
            return render_template(
                "adapt.html", vacante=vacante_texto, idioma=idioma,
                sin_traducir=sin_traducir, forzar=forzar,
            )

    datos_vacante = analysis.extract_data(vacante_texto)

    if not forzar and datos_vacante.company:
        previos = archivo.find_by_company(context.root(), datos_vacante.company)
        if previos:
            return render_template(
                "adapt.html",
                vacante=vacante_texto,
                idioma=idioma,
                previos=previos,
                empresa=datos_vacante.company,
                forzar_idioma=True,
            )

    ajustes = context.current_settings()
    try:
        cliente = create_client(ajustes.proveedor, ajustes.clave_api, ajustes.url_base, ajustes.modelo)
    except AIError as error:
        flash(str(error))
        return render_template("adapt.html", vacante=vacante_texto, idioma=idioma)
    if not cliente.available():
        flash(_("Configura tu clave de API en Ajustes antes de generar una propuesta."))
        return redirect(url_for("ancla.view_settings"))

    try:
        propuesta = engine.adapt(perfil, vacante_texto, idioma, cliente, N_EXPERIENCES, N_SKILLS)
    except (AIError, ValueError) as error:
        flash(str(error))
        return render_template("adapt.html", vacante=vacante_texto, idioma=idioma)

    modulo_borrador.save_draft(
        context.root(),
        modulo_borrador.Draft(
            vacante=vacante_texto,
            empresa=datos_vacante.company,
            puesto=datos_vacante.position,
            propuesta=propuesta,
        ),
    )
    return redirect(url_for("ancla.view_proposal"))


def _untranslated_names(perfil, idioma: str) -> list[str]:
    """The profile entries that would reach the CV empty in `idioma`.

    Names, not counts: "you are missing four things" leaves the user with
    nothing to act on, and the point of warning at all is that they can
    decide whether those four matter for this posting.
    """
    catalogos = (
        [perfil.about_me], perfil.experiences, perfil.skills, perfil.personal_skills,
        perfil.languages, perfil.education,
    )
    return [
        translation.entry_name(entrada)
        for catalogo in catalogos
        for entrada in translation.pending(catalogo, idioma)
    ]
