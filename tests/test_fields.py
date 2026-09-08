"""Tests for `ancla/export/fields.py`: building the field catalog a CV
template renders from a proposal — shared by every printable HTML template,
recovered from the old `.docx`-only `test_export.py` when the `.docx`
export path was removed (the field catalog itself was never docx-specific)."""
from __future__ import annotations

import dataclasses

from ancla.export import fields
from ancla.profile.model import (
    Bilingual,
    Education,
    Experience,
    Profile,
    Proposal,
    SelectedAboutMe,
    SelectedExperience,
    Skill,
    SpokenLanguage,
)


def _perfil() -> Profile:
    experiencias = [
        Experience(
            id="proyecto-a",
            title=Bilingual(es="Ingeniero de Datos · ACME", en="Data Engineer · ACME"),
            period_start="2023", period_end="2024",
            bullets=Bilingual(es=["Bullet A1", "Bullet A2"], en=["Bullet A1 EN", "Bullet A2 EN"]),
            stack="Python",
        ),
        Experience(
            id="proyecto-b",
            title=Bilingual(es="Backend Developer · Nubelia", en="Backend Developer · Nubelia"),
            period_start="2021", period_end="2023",
            bullets=Bilingual(es=["Bullet B1"], en=["Bullet B1 EN"]),
            stack="Go",
        ),
    ]
    skills = [Skill(id="python", name=Bilingual(es="Python", en="Python"))]
    personales = [Skill(id="equipo", name=Bilingual(es="Trabajo en equipo", en="Teamwork"))]
    idiomas = [SpokenLanguage(id="en", name=Bilingual(es="Inglés", en="English"), level=Bilingual(es="C1", en="C1"))]
    educacion = [
        Education(
            id="grado",
            title=Bilingual(es="Grado en Ingeniería Informática", en="BSc in Computer Engineering"),
            institution="UEMC",
            period_start="2023", period_end="2027",
        )
    ]
    return Profile(
        experiences=experiencias,
        skills=skills,
        personal_skills=personales,
        languages=idiomas,
        education=educacion,
        contact=["+34 000 000 000", "tu-email@ejemplo.com"],
        headline=Bilingual(es="Ingeniero Informático", en="Computer Engineer"),
    )


def _propuesta() -> Proposal:
    return Proposal(
        language="es",
        about_me=SelectedAboutMe(group_a=[], group_b=[], text="Sobre mí de prueba.", reason=""),
        skills=["python"],
        experiences=[
            SelectedExperience(id="proyecto-a", reason="Encaja con la vacante."),
            SelectedExperience(id="proyecto-b", reason="Completa la sección."),
        ],
    )


def test_resolved_selection_descarta_experiencias_que_ya_no_existen():
    perfil = _perfil()
    propuesta = _propuesta()
    propuesta.experiences.append(SelectedExperience(id="no-existe", reason=""))
    seleccion = fields.resolved_selection(propuesta, perfil)
    assert [s.id for s, _ in seleccion] == ["proyecto-a", "proyecto-b"]


def test_build_context_expone_el_catalogo_de_campos():
    perfil = _perfil()
    propuesta = _propuesta()
    experiencias = fields.resolved_experiences(propuesta, perfil)
    contexto = fields.build_context(propuesta, perfil, experiencias, "Daniel Vega")

    assert contexto["nombre"] == "Daniel Vega"
    assert contexto["sobre_mi"] == "Sobre mí de prueba."
    assert contexto["skills"] == ["Python"]
    assert contexto["idiomas"] == ["Inglés — C1"]
    assert contexto["skills_personales"] == ["Trabajo en equipo"]
    assert len(contexto["experiencias"]) == 2
    primera = contexto["experiencias"][0]
    assert primera["puesto"] == "Ingeniero de Datos · ACME"
    assert primera["empresa"] == ""
    assert primera["fechas"] == "2023 · 2024"
    assert primera["bullets"] == ["Bullet A1", "Bullet A2"]
    assert primera["stack"] == "Python"
    assert contexto["contacto"] == ["+34 000 000 000", "tu-email@ejemplo.com"]
    assert contexto["titular"] == "Ingeniero Informático"
    assert contexto["educacion"] == [
        {"titulo": "Grado en Ingeniería Informática", "centro": "UEMC", "fechas": "2023 · 2027"}
    ]
    assert contexto["foto"] == ""


def test_nunca_reescribe_los_bullets_del_usuario():
    """Product rule 2: bullets are shown verbatim, letter for letter — the
    context doesn't touch them, only copies them from the experience."""
    perfil = _perfil()
    propuesta = _propuesta()
    experiencias = fields.resolved_experiences(propuesta, perfil)
    contexto = fields.build_context(propuesta, perfil, experiencias, "")
    assert contexto["experiencias"][0]["bullets"] == perfil.experience("proyecto-a").bullets["es"]


def test_sustituye_el_guion_no_separable_por_uno_normal():
    """Narrow, documented exception to rule 2: some fonts don't ship the
    U+2011 glyph, so it visually breaks. Typographic-compatibility fix, not
    a content rewrite — visually identical, and the saved profile is never
    touched (it only happens in `build_context`, on the way to the CV)."""
    guion_no_separable = "H‑Z‑H"
    perfil = dataclasses.replace(
        _perfil(), headline=Bilingual(es=f"Rol {guion_no_separable}", en=f"Role {guion_no_separable}")
    )
    perfil.experience("proyecto-a").bullets["es"][0] = f"Secuencia {guion_no_separable}"
    propuesta = _propuesta()
    experiencias = fields.resolved_experiences(propuesta, perfil)
    contexto = fields.build_context(propuesta, perfil, experiencias, "")

    assert contexto["experiencias"][0]["bullets"][0] == "Secuencia H-Z-H"
    assert contexto["titular"] == "Rol H-Z-H"
    assert "‑" not in contexto["experiencias"][0]["bullets"][0]
