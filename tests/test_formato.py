"""Tests del render de propuestas a texto y markdown."""
from __future__ import annotations

from ancla.perfil.modelo import (
    Bilingue,
    Experiencia,
    ExperienciaSeleccionada,
    IdiomaHablado,
    Perfil,
    Propuesta,
    SeleccionSobreMi,
    Skill,
)
from ancla.propuesta.formato import a_markdown, a_texto


def _perfil() -> Perfil:
    experiencia = Experiencia(
        id="proyecto-x",
        titulo=Bilingue(es="Ingeniero de Datos", en="Data Engineer"),
        periodo=Bilingue(es="2023 — 2024", en="2023 — 2024"),
        bullets=Bilingue(
            es=["Diseñé el pipeline de ingesta", "Reduje el coste un 30%"],
            en=["Designed the ingestion pipeline", "Cut cost by 30%"],
        ),
        stack=Bilingue(es="Python, Airflow, GCP", en="Python, Airflow, GCP"),
    )
    skills = [
        Skill(id="python", nombre=Bilingue(es="Python", en="Python")),
        Skill(id="sql", nombre=Bilingue(es="SQL", en="SQL")),
        Skill(id="gcp", nombre=Bilingue(es="GCP", en="GCP")),
    ]
    return Perfil(experiencias=[experiencia], skills=skills)


def _propuesta(idioma: str = "es", huecos: list[str] | None = None) -> Propuesta:
    return Propuesta(
        idioma=idioma,
        sobre_mi=SeleccionSobreMi(
            grupo_a=["datos", "backend", "cloud"],
            grupo_b=["Python", "SQL", "GCP"],
            texto="Ingeniero con foco en datos, backend y cloud.",
            motivo="Encaja con los requisitos principales de la vacante.",
        ),
        skills=["python", "sql", "gcp"],
        experiencias=[ExperienciaSeleccionada(id="proyecto-x", motivo="Coincide con el stack pedido.")],
        motivo_skills="Son las skills más citadas en la oferta.",
        huecos=huecos or [],
    )


def test_a_texto_no_incluye_motivos():
    texto = a_texto(_propuesta(), _perfil())
    assert "Motivo" not in texto
    assert "Encaja con" not in texto


def test_a_texto_incluye_el_contenido_en_orden():
    texto = a_texto(_propuesta(), _perfil())
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
    texto = a_texto(_propuesta(idioma="en"), _perfil())
    assert "ABOUT ME" in texto
    assert "TECHNICAL SKILLS" in texto
    assert "RELEVANT EXPERIENCE" in texto
    assert "Data Engineer — 2023 — 2024" in texto
    assert "- Designed the ingestion pipeline" in texto


def test_a_texto_omite_experiencias_que_ya_no_existen_en_el_perfil():
    propuesta = Propuesta(
        idioma="es",
        sobre_mi=_propuesta().sobre_mi,
        skills=[],
        experiencias=[ExperienciaSeleccionada(id="no-existe", motivo="x")],
    )
    texto = a_texto(propuesta, _perfil())
    assert "EXPERIENCIA RELEVANTE" not in texto


def test_a_markdown_incluye_motivos():
    markdown = a_markdown(_propuesta(), _perfil())
    assert "Motivo: Encaja con los requisitos principales de la vacante." in markdown
    assert "Motivo: Son las skills más citadas en la oferta." in markdown
    assert "Motivo: Coincide con el stack pedido." in markdown


def test_a_markdown_sin_huecos_dice_que_no_hay():
    markdown = a_markdown(_propuesta(huecos=[]), _perfil())
    assert "Ninguno: el perfil cubre todo lo que pide la vacante." in markdown


def test_a_markdown_lista_los_huecos_detectados():
    markdown = a_markdown(_propuesta(huecos=["Kubernetes", "Terraform"]), _perfil())
    assert "- Kubernetes" in markdown
    assert "- Terraform" in markdown


def test_a_texto_omite_skills_que_ya_no_existen_en_el_perfil():
    propuesta = Propuesta(
        idioma="es",
        sobre_mi=_propuesta().sobre_mi,
        skills=["python", "id-borrado", "sql"],
        experiencias=[],
    )
    texto = a_texto(propuesta, _perfil())
    assert "Python · SQL" in texto


def test_a_markdown_marca_experiencias_desaparecidas_del_perfil():
    propuesta = Propuesta(
        idioma="es",
        sobre_mi=_propuesta().sobre_mi,
        skills=[],
        experiencias=[ExperienciaSeleccionada(id="fantasma", motivo="x")],
    )
    markdown = a_markdown(propuesta, _perfil())
    assert "ya no existe en el perfil" in markdown


# --------------------------------------------------------------------------
# Skills personales e idiomas: siempre completos, sin pasar por Propuesta
# --------------------------------------------------------------------------


def _perfil_con_personales_e_idiomas() -> Perfil:
    base = _perfil()
    return Perfil(
        experiencias=base.experiencias,
        skills=base.skills,
        skills_personales=[
            Skill(id="equipo", nombre=Bilingue(es="Trabajo en equipo", en="Teamwork")),
            Skill(id="comunicacion", nombre=Bilingue(es="Comunicación", en="Communication")),
        ],
        idiomas=[
            IdiomaHablado(
                id="ingles",
                nombre=Bilingue(es="Inglés", en="English"),
                nivel=Bilingue(es="C1 — Avanzado", en="C1 — Advanced"),
            ),
        ],
        sobre_mi=base.sobre_mi,
    )


def test_a_texto_incluye_skills_personales_e_idiomas_completos():
    texto = a_texto(_propuesta(), _perfil_con_personales_e_idiomas())
    assert "SKILLS PERSONALES" in texto
    assert "Trabajo en equipo · Comunicación" in texto
    assert "IDIOMAS" in texto
    assert "Inglés — C1 — Avanzado" in texto


def test_a_texto_en_ingles_traduce_encabezados_y_nombres():
    perfil = _perfil_con_personales_e_idiomas()
    texto = a_texto(_propuesta(idioma="en"), perfil)
    assert "PERSONAL SKILLS" in texto
    assert "Teamwork · Communication" in texto
    assert "LANGUAGES" in texto
    assert "English — C1 — Advanced" in texto


def test_a_markdown_lista_skills_personales_e_idiomas():
    markdown = a_markdown(_propuesta(), _perfil_con_personales_e_idiomas())
    assert "## Skills personales" in markdown
    assert "- Trabajo en equipo" in markdown
    assert "## Idiomas" in markdown
    assert "- Inglés — C1 — Avanzado" in markdown


def test_sin_skills_personales_ni_idiomas_no_aparecen_los_bloques():
    """Son opcionales: si el usuario no los ha rellenado, no se enseña un
    apartado vacío."""
    texto = a_texto(_propuesta(), _perfil())
    assert "SKILLS PERSONALES" not in texto
    assert "IDIOMAS" not in texto


def test_skills_personales_e_idiomas_se_leen_del_perfil_no_de_la_propuesta():
    """No hay selección de IA para estos dos bloques: cambiar el perfil basta,
    no hace falta regenerar la propuesta."""
    propuesta = _propuesta()
    perfil_ampliado = _perfil_con_personales_e_idiomas()
    assert "Inglés" in a_texto(propuesta, perfil_ampliado)
    assert "Inglés" not in a_texto(propuesta, _perfil())
