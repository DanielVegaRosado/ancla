"""Proposal screen: the result of Adapt, with reasons, gaps, copy buttons,
direct per-item adjustment, and regenerate by section."""
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime

from flask import flash, redirect, render_template, request, url_for
from flask_babel import gettext as _

from ancla.ai.client import AIError
from ancla.export import templates as plantillas_docx
from ancla.profile.model import (
    N_EXPERIENCES,
    N_SKILLS,
    CVStatus,
    SavedCV,
    SelectedAboutMe,
    SelectedExperience,
)
from ancla.proposal.format import (
    to_markdown,
    to_text,
    language_lines,
    personal_skill_names,
    experience_text,
)
from ancla.archive import repository as archivo
from ancla.selection import engine
from ancla.web import draft as modulo_borrador
from ancla.web import context
from ancla.web.blueprint import bp
from ancla.web.providers import create_client

_SECCIONES = ("sobre-mi", "skills", "experiencias")


@bp.route("/propuesta")
def view_proposal():
    borrador = modulo_borrador.load_draft(context.root())
    if borrador is None:
        flash(_("Todavía no has generado ninguna propuesta. Empieza por pegar una vacante."))
        return redirect(url_for("ancla.adapt"))

    perfil = context.current_profile()
    propuesta = borrador.propuesta
    experiencias = [
        (sel, experiencia, experience_text(experiencia, propuesta.language) if experiencia else None)
        for sel, experiencia in (
            (sel, perfil.experience(sel.id)) for sel in propuesta.experiences
        )
    ]
    skills = [(id_, perfil.skill(id_)) for id_ in propuesta.skills]
    texto_skills = " · ".join(skill.name[propuesta.language] for _, skill in skills if skill)

    # Personal skills and languages never go through the Proposal or the
    # draft: they are read live from the profile on every render, because
    # there is no AI selection to store — they are always shown in full.
    texto_skills_personales = " · ".join(personal_skill_names(perfil, propuesta.language))
    texto_idiomas = " · ".join(language_lines(perfil, propuesta.language))

    return render_template(
        "proposal.html",
        borrador=borrador,
        propuesta=propuesta,
        perfil=perfil,
        experiencias=experiencias,
        skills=skills,
        texto_skills=texto_skills,
        texto_skills_personales=texto_skills_personales,
        texto_idiomas=texto_idiomas,
        texto_plano=to_text(propuesta, perfil),
        texto_markdown=to_markdown(propuesta, perfil),
        hoy=date.today().isoformat(),
        plantillas_docx=plantillas_docx.list_templates(context.docx_templates_root()),
    )


def _with_draft_or_redirect():
    borrador = modulo_borrador.load_draft(context.root())
    if borrador is None:
        flash(_("Esa propuesta ya no está disponible, genera una nueva."))
        return None
    return borrador


@bp.route("/propuesta/ajustar-sobre-mi", methods=["POST"])
def adjust_about_me():
    borrador = _with_draft_or_redirect()
    if borrador is None:
        return redirect(url_for("ancla.adapt"))

    perfil = context.current_profile()
    if perfil.about_me is None:
        flash(_("Tu perfil ya no tiene plantilla de «Sobre mí»."))
        return redirect(url_for("ancla.view_proposal"))

    f = request.form
    grupo_a = [f.get(f"grupo_a_{n}", "").strip() for n in (1, 2, 3)]
    grupo_b = [f.get(f"grupo_b_{n}", "").strip() for n in (1, 2, 3)]
    motivo = f.get("motivo", "").strip()

    try:
        texto = perfil.about_me.render(grupo_a, grupo_b, borrador.propuesta.language)
    except ValueError as error:
        flash(str(error))
        return redirect(url_for("ancla.view_proposal"))

    nueva_seleccion = SelectedAboutMe(group_a=grupo_a, group_b=grupo_b, text=texto, reason=motivo)
    borrador.propuesta = replace(borrador.propuesta, about_me=nueva_seleccion)
    modulo_borrador.save_draft(context.root(), borrador)
    flash(_("«Sobre mí» actualizado."))
    return redirect(url_for("ancla.view_proposal"))


@bp.route("/propuesta/ajustar-skill", methods=["POST"])
def adjust_skill():
    borrador = _with_draft_or_redirect()
    if borrador is None:
        return redirect(url_for("ancla.adapt"))

    indice = int(request.form.get("indice", -1))
    new_id = request.form.get("skill_id", "")
    skills = list(borrador.propuesta.skills)
    if 0 <= indice < len(skills) and new_id:
        skills[indice] = new_id
        borrador.propuesta = replace(borrador.propuesta, skills=skills)
        modulo_borrador.save_draft(context.root(), borrador)
        flash(_("Skill actualizada."))
    return redirect(url_for("ancla.view_proposal"))


@bp.route("/propuesta/ajustar-motivo-skills", methods=["POST"])
def adjust_skills_reason():
    borrador = _with_draft_or_redirect()
    if borrador is None:
        return redirect(url_for("ancla.adapt"))

    borrador.propuesta = replace(borrador.propuesta, skills_reason=request.form.get("motivo", "").strip())
    modulo_borrador.save_draft(context.root(), borrador)
    return redirect(url_for("ancla.view_proposal"))


@bp.route("/propuesta/ajustar-experiencia", methods=["POST"])
def adjust_experience():
    borrador = _with_draft_or_redirect()
    if borrador is None:
        return redirect(url_for("ancla.adapt"))

    indice = int(request.form.get("indice", -1))
    new_id = request.form.get("experiencia_id", "")
    motivo = request.form.get("motivo", "").strip()
    experiencias = list(borrador.propuesta.experiences)
    if 0 <= indice < len(experiencias) and new_id:
        experiencias[indice] = SelectedExperience(id=new_id, reason=motivo)
        borrador.propuesta = replace(borrador.propuesta, experiences=experiencias)
        modulo_borrador.save_draft(context.root(), borrador)
        flash(_("Experiencia actualizada."))
    return redirect(url_for("ancla.view_proposal"))


@bp.route("/propuesta/regenerar/<seccion>", methods=["POST"])
def regenerate_section(seccion: str):
    borrador = _with_draft_or_redirect()
    if borrador is None:
        return redirect(url_for("ancla.adapt"))

    if seccion not in _SECCIONES:
        flash(_("Sección desconocida."))
        return redirect(url_for("ancla.view_proposal"))

    ajustes = context.current_settings()
    try:
        cliente = create_client(ajustes.proveedor, ajustes.clave_api, ajustes.url_base, ajustes.modelo)
    except AIError as error:
        flash(str(error))
        return redirect(url_for("ancla.view_proposal"))
    if not cliente.available():
        flash(_("Configura tu clave de API en Ajustes antes de regenerar."))
        return redirect(url_for("ancla.view_settings"))

    try:
        nueva_propuesta = engine.adapt(
            context.current_profile(), borrador.vacante, borrador.propuesta.language, cliente, N_EXPERIENCES, N_SKILLS
        )
    except (AIError, ValueError) as error:
        flash(str(error))
        return redirect(url_for("ancla.view_proposal"))

    if seccion == "sobre-mi":
        borrador.propuesta = replace(borrador.propuesta, about_me=nueva_propuesta.about_me)
    elif seccion == "skills":
        borrador.propuesta = replace(
            borrador.propuesta, skills=nueva_propuesta.skills, skills_reason=nueva_propuesta.skills_reason
        )
    else:
        borrador.propuesta = replace(borrador.propuesta, experiences=nueva_propuesta.experiences)

    borrador.propuesta = replace(borrador.propuesta, gaps=nueva_propuesta.gaps)
    modulo_borrador.save_draft(context.root(), borrador)
    flash(_("Sección regenerada."))
    return redirect(url_for("ancla.view_proposal"))


@bp.route("/propuesta/descartar", methods=["POST"])
def discard_proposal():
    modulo_borrador.delete_draft(context.root())
    flash(_("Propuesta descartada."))
    return redirect(url_for("ancla.adapt"))


@bp.route("/propuesta/guardar", methods=["POST"])
def save_proposal():
    borrador = _with_draft_or_redirect()
    if borrador is None:
        return redirect(url_for("ancla.adapt"))

    empresa = request.form.get("empresa", "").strip() or borrador.empresa or "Empresa"
    puesto = request.form.get("puesto", "").strip() or borrador.puesto
    notas = request.form.get("notas", "").strip()
    # Both come from the same instant so a capture does not cross midnight
    # against the other if they were read separately.
    ahora = datetime.now()
    id_ = archivo.new_id(context.root(), ahora.date(), empresa, puesto)

    cv = SavedCV(
        id=id_,
        date=ahora.date(),
        time=ahora.time(),
        company=empresa,
        position=puesto,
        posting=borrador.vacante,
        proposal=borrador.propuesta,
        status=CVStatus.DRAFT,
        notes=notas,
    )
    archivo.save(context.root(), cv)
    modulo_borrador.delete_draft(context.root())
    flash(_("CV guardado en el archivo para %(empresa)s.", empresa=empresa))
    return redirect(url_for("ancla.view_cv", id_=id_))
