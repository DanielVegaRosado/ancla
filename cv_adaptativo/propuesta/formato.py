"""Render de la propuesta a texto que el usuario copia y pega.

La app no genera el PDF: el diseño sigue siendo del usuario (Canva u otra
herramienta). Aquí solo se produce texto limpio, en el mismo orden en que
aparece en el CV, listo para pegar bloque a bloque.

CONTRATO — implementa el agente C.
"""
from __future__ import annotations

from cv_adaptativo.perfil.modelo import Experiencia, Idioma, Perfil, Propuesta

_ENCABEZADOS = {
    "es": {
        "sobre_mi": "SOBRE MÍ",
        "skills": "SKILLS TÉCNICAS",
        "experiencia": "EXPERIENCIA RELEVANTE",
    },
    "en": {
        "sobre_mi": "ABOUT ME",
        "skills": "TECHNICAL SKILLS",
        "experiencia": "RELEVANT EXPERIENCE",
    },
}

_MOTIVOS_MD = {
    "es": {
        "sobre_mi": "## Sobre mí",
        "skills": "## Skills técnicas",
        "experiencia": "## Experiencia relevante",
        "huecos": "## Huecos detectados",
        "huecos_vacio": "Ninguno: el perfil cubre todo lo que pide la vacante.",
        "motivo": "Motivo",
        "no_existe": "*(ya no existe en el perfil)*",
    },
    "en": {
        "sobre_mi": "## About me",
        "skills": "## Technical skills",
        "experiencia": "## Relevant experience",
        "huecos": "## Gaps detected",
        "huecos_vacio": "None: the profile covers everything the posting asks for.",
        "motivo": "Reason",
        "no_existe": "*(no longer in the profile)*",
    },
}


def _bloque_experiencia(experiencia: Experiencia, idioma: Idioma) -> list[str]:
    lineas = [f"{experiencia.titulo[idioma]} — {experiencia.periodo[idioma]}"]
    lineas.extend(f"- {bullet}" for bullet in experiencia.bullets[idioma])
    if experiencia.stack[idioma]:
        lineas.append(experiencia.stack[idioma])
    return lineas


def texto_experiencia(experiencia: Experiencia, idioma: Idioma) -> str:
    """Una experiencia sola, lista para copiar. La usa también la web para el
    botón de copiar de cada bloque en la pantalla de Propuesta."""
    return "\n".join(_bloque_experiencia(experiencia, idioma))


def _nombres_skills(propuesta: Propuesta, perfil: Perfil) -> list[str]:
    """`Propuesta.skills` son ids de `Skill`, no texto ya escrito: se resuelven
    contra el perfil para que corregir el nombre de una skill se propague a
    todo el archivo histórico. Si una skill ya no existe se omite."""
    nombres = (perfil.skill(id_) for id_ in propuesta.skills)
    return [skill.nombre[propuesta.idioma] for skill in nombres if skill is not None]


def a_texto(propuesta: Propuesta, perfil: Perfil) -> str:
    """Texto plano, para pegar en Canva. Sin motivos: solo el contenido del CV."""
    idioma = propuesta.idioma
    encabezados = _ENCABEZADOS[idioma]
    bloques: list[str] = []

    bloques.append(f"{encabezados['sobre_mi']}\n\n{propuesta.sobre_mi.texto}")

    nombres_skills = _nombres_skills(propuesta, perfil)
    if nombres_skills:
        bloques.append(f"{encabezados['skills']}\n\n" + " · ".join(nombres_skills))

    experiencias = [
        perfil.experiencia(seleccionada.id) for seleccionada in propuesta.experiencias
    ]
    experiencias_texto = "\n\n".join(
        texto_experiencia(experiencia, idioma)
        for experiencia in experiencias
        if experiencia is not None
    )
    if experiencias_texto:
        bloques.append(f"{encabezados['experiencia']}\n\n{experiencias_texto}")

    return "\n\n".join(bloques) + "\n"


def a_markdown(propuesta: Propuesta, perfil: Perfil) -> str:
    """Markdown con los motivos y los huecos detectados, para guardar o revisar."""
    idioma = propuesta.idioma
    textos = _MOTIVOS_MD[idioma]
    partes: list[str] = []

    partes.append(f"{textos['sobre_mi']}\n\n{propuesta.sobre_mi.texto}")
    if propuesta.sobre_mi.motivo:
        partes.append(f"> {textos['motivo']}: {propuesta.sobre_mi.motivo}")

    nombres_skills = _nombres_skills(propuesta, perfil)
    if nombres_skills:
        lista_skills = "\n".join(f"{n}. {skill}" for n, skill in enumerate(nombres_skills, start=1))
        partes.append(f"{textos['skills']}\n\n{lista_skills}")
        if propuesta.motivo_skills:
            partes.append(f"> {textos['motivo']}: {propuesta.motivo_skills}")

    if propuesta.experiencias:
        bloques_experiencia = []
        for seleccionada in propuesta.experiencias:
            experiencia = perfil.experiencia(seleccionada.id)
            if experiencia is None:
                bloque = f"**{seleccionada.id}** {textos['no_existe']}"
            else:
                bloque = texto_experiencia(experiencia, idioma)
            if seleccionada.motivo:
                bloque += f"\n> {textos['motivo']}: {seleccionada.motivo}"
            bloques_experiencia.append(bloque)
        partes.append(f"{textos['experiencia']}\n\n" + "\n\n".join(bloques_experiencia))

    huecos = (
        "\n".join(f"- {hueco}" for hueco in propuesta.huecos)
        if propuesta.huecos
        else textos["huecos_vacio"]
    )
    partes.append(f"{textos['huecos']}\n\n{huecos}")

    return "\n\n".join(partes) + "\n"
