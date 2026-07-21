"""Tests del render de propuestas a texto y markdown."""
from __future__ import annotations

from cv_adaptativo.perfil.modelo import (
    Bilingue,
    Experiencia,
    ExperienciaSeleccionada,
    Perfil,
    Propuesta,
    SeleccionSobreMi,
    Skill,
)
from cv_adaptativo.propuesta.formato import a_markdown, a_texto


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
