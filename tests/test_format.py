"""Tests for rendering proposals to text and markdown."""
from __future__ import annotations

from ancla.profile.model import (
    Bilingual,
    Experience,
    Profile,
    Proposal,
    SelectedAboutMe,
    SelectedExperience,
    Skill,
    SpokenLanguage,
)
from ancla.proposal.format import to_markdown, to_text


def _perfil() -> Profile:
    experiencia = Experience(
        id="proyecto-x",
        title=Bilingual(es="Ingeniero de Datos", en="Data Engineer"),
        period=Bilingual(es="2023 — 2024", en="2023 — 2024"),
        bullets=Bilingual(
            es=["Diseñé el pipeline de ingesta", "Reduje el coste un 30%"],
            en=["Designed the ingestion pipeline", "Cut cost by 30%"],
        ),
        stack=Bilingual(es="Python, Airflow, GCP", en="Python, Airflow, GCP"),
    )
    skills = [
        Skill(id="python", name=Bilingual(es="Python", en="Python")),
        Skill(id="sql", name=Bilingual(es="SQL", en="SQL")),
        Skill(id="gcp", name=Bilingual(es="GCP", en="GCP")),
    ]
    return Profile(experiences=[experiencia], skills=skills)


def _propuesta(idioma: str = "es", huecos: list[str] | None = None) -> Proposal:
    return Proposal(
        language=idioma,
        about_me=SelectedAboutMe(
            group_a=["datos", "backend", "cloud"],
            group_b=["Python", "SQL", "GCP"],
            text="Ingeniero con foco en datos, backend y cloud.",
            reason="Encaja con los requisitos principales de la vacante.",
        ),
        skills=["python", "sql", "gcp"],
        experiences=[SelectedExperience(id="proyecto-x", reason="Coincide con el stack pedido.")],
        skills_reason="Son las skills más citadas en la oferta.",
        gaps=huecos or [],
    )


def test_a_texto_no_incluye_motivos():
    texto = to_text(_propuesta(), _perfil())
    assert "Motivo" not in texto
    assert "Encaja con" not in texto


def test_a_texto_incluye_el_contenido_en_orden():
    texto = to_text(_propuesta(), _perfil())
    pos_sobre_mi = texto.index("SOBRE MÍ")
    pos_skills = texto.index("SKILLS TÉCNICAS")
    pos_experiencia = texto.index("EXPERIENCIA RELEVANTE")
    assert pos_sobre_mi < pos_skills < pos_experiencia
    assert "Ingeniero con foco en datos, backend y cloud." in texto
    assert "Python · SQL · GCP" in texto
    assert "Ingeniero de Datos — 2023 — 2024" in texto
    assert "- Diseñé el pipeline de ingesta" in texto
    assert "Python, Airflow, GCP" in texto


def test_a_texto_respeta_el_idioma():
    texto = to_text(_propuesta(idioma="en"), _perfil())
    assert "ABOUT ME" in texto
    assert "TECHNICAL SKILLS" in texto
    assert "RELEVANT EXPERIENCE" in texto
    assert "Data Engineer — 2023 — 2024" in texto
    assert "- Designed the ingestion pipeline" in texto


def test_a_texto_omite_experiencias_que_ya_no_existen_en_el_perfil():
    propuesta = Proposal(
        language="es",
        about_me=_propuesta().about_me,
        skills=[],
        experiences=[SelectedExperience(id="no-existe", reason="x")],
    )
    texto = to_text(propuesta, _perfil())
    assert "EXPERIENCIA RELEVANTE" not in texto


def test_a_markdown_incluye_motivos():
    markdown = to_markdown(_propuesta(), _perfil())
    assert "Motivo: Encaja con los requisitos principales de la vacante." in markdown
    assert "Motivo: Son las skills más citadas en la oferta." in markdown
    assert "Motivo: Coincide con el stack pedido." in markdown


def test_a_markdown_sin_huecos_dice_que_no_hay():
    markdown = to_markdown(_propuesta(huecos=[]), _perfil())
    assert "Ninguno: el perfil cubre todo lo que pide la vacante." in markdown


def test_a_markdown_lista_los_huecos_detectados():
    markdown = to_markdown(_propuesta(huecos=["Kubernetes", "Terraform"]), _perfil())
    assert "- Kubernetes" in markdown
    assert "- Terraform" in markdown


def test_a_texto_omite_skills_que_ya_no_existen_en_el_perfil():
    propuesta = Proposal(
        language="es",
        about_me=_propuesta().about_me,
        skills=["python", "id-borrado", "sql"],
        experiences=[],
    )
    texto = to_text(propuesta, _perfil())
    assert "Python · SQL" in texto


def test_a_markdown_marca_experiencias_desaparecidas_del_perfil():
    propuesta = Proposal(
        language="es",
        about_me=_propuesta().about_me,
        skills=[],
        experiences=[SelectedExperience(id="fantasma", reason="x")],
    )
    markdown = to_markdown(propuesta, _perfil())
    assert "ya no existe en el perfil" in markdown


# --------------------------------------------------------------------------
# Personal skills and languages: always shown in full, never through Proposal
# --------------------------------------------------------------------------


def _perfil_con_personales_e_idiomas() -> Profile:
    base = _perfil()
    return Profile(
        experiences=base.experiences,
        skills=base.skills,
        personal_skills=[
            Skill(id="equipo", name=Bilingual(es="Trabajo en equipo", en="Teamwork")),
            Skill(id="comunicacion", name=Bilingual(es="Comunicación", en="Communication")),
        ],
        languages=[
            SpokenLanguage(
                id="ingles",
                name=Bilingual(es="Inglés", en="English"),
                level=Bilingual(es="C1 — Avanzado", en="C1 — Advanced"),
            ),
        ],
        about_me=base.about_me,
    )


def test_a_texto_incluye_skills_personales_e_idiomas_completos():
    texto = to_text(_propuesta(), _perfil_con_personales_e_idiomas())
    assert "SKILLS PERSONALES" in texto
    assert "Trabajo en equipo · Comunicación" in texto
    assert "IDIOMAS" in texto
    assert "Inglés — C1 — Avanzado" in texto


def test_a_texto_en_ingles_traduce_encabezados_y_nombres():
    perfil = _perfil_con_personales_e_idiomas()
    texto = to_text(_propuesta(idioma="en"), perfil)
    assert "PERSONAL SKILLS" in texto
    assert "Teamwork · Communication" in texto
    assert "LANGUAGES" in texto
    assert "English — C1 — Advanced" in texto


def test_a_markdown_lista_skills_personales_e_idiomas():
    markdown = to_markdown(_propuesta(), _perfil_con_personales_e_idiomas())
    assert "## Skills personales" in markdown
    assert "- Trabajo en equipo" in markdown
    assert "## Idiomas" in markdown
    assert "- Inglés — C1 — Avanzado" in markdown


def test_sin_skills_personales_ni_idiomas_no_aparecen_los_bloques():
    """They are optional: if the user has not filled them in, an empty
    section is not shown."""
    texto = to_text(_propuesta(), _perfil())
    assert "SKILLS PERSONALES" not in texto
    assert "IDIOMAS" not in texto


def test_skills_personales_e_idiomas_se_leen_del_perfil_no_de_la_propuesta():
    """There is no AI selection for these two blocks: changing the profile
    is enough, no need to regenerate the proposal."""
    propuesta = _propuesta()
    perfil_ampliado = _perfil_con_personales_e_idiomas()
    assert "Inglés" in to_text(propuesta, perfil_ampliado)
    assert "Inglés" not in to_text(propuesta, _perfil())
