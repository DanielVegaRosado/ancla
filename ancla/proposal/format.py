"""Renders the proposal to text: the per-section copy buttons on the
Proposal screen (`experience_text`, `skill_names`, ...) and the saved-CV
Markdown record (`to_markdown`) shown on a CV's detail page.

The app does not generate the PDF: the layout is the browser's own print
(`ancla/export/html_layout.py`), not something this module produces.

Personal skills and languages are **always shown in full**, read live from
the profile — they never go through `Proposal`, because there is no AI
selection to store: unlike experience or technical skills, a real CV does
not trim these two sections per job posting.
"""
from __future__ import annotations

from ancla.profile.model import Experience, Language, Profile, Proposal, period_text

_MOTIVOS_MD = {
    "es": {
        "sobre_mi": "## Sobre mí",
        "skills": "## Skills técnicas",
        "experiencia": "## Experiencia relevante",
        "skills_personales": "## Skills personales",
        "idiomas": "## Idiomas",
        "huecos": "## Huecos detectados",
        "huecos_vacio": "Ninguno: el perfil cubre todo lo que pide la vacante.",
        "motivo": "Motivo",
        "no_existe": "*(ya no existe en el perfil)*",
    },
    "en": {
        "sobre_mi": "## About me",
        "skills": "## Technical skills",
        "experiencia": "## Relevant experience",
        "skills_personales": "## Personal skills",
        "idiomas": "## Languages",
        "huecos": "## Gaps detected",
        "huecos_vacio": "None: the profile covers everything the posting asks for.",
        "motivo": "Reason",
        "no_existe": "*(no longer in the profile)*",
    },
}


def _experience_block(experiencia: Experience, idioma: Language) -> list[str]:
    lineas = [f"{experiencia.title[idioma]} — {period_text(experiencia.period_start, experiencia.period_end, idioma)}"]
    lineas.extend(f"- {bullet}" for bullet in experiencia.bullets[idioma])
    if experiencia.stack:
        lineas.append(experiencia.stack)
    return lineas


def experience_text(experiencia: Experience, idioma: Language) -> str:
    """A single experience, ready to copy. Also used by the web layer for
    each block's copy button on the Proposal screen."""
    return "\n".join(_experience_block(experiencia, idioma))


def skill_names(propuesta: Proposal, perfil: Profile) -> list[str]:
    """`Proposal.skills` are `Skill` ids, not already-written text: resolved
    against the profile so that correcting a skill's name propagates across
    the whole archive. A skill that no longer exists is omitted."""
    nombres = (perfil.skill(id_) for id_ in propuesta.skills)
    return [skill.name[propuesta.language] for skill in nombres if skill is not None]


def personal_skill_names(perfil: Profile, idioma: Language) -> list[str]:
    return [skill.name[idioma] for skill in perfil.personal_skills]


def language_lines(perfil: Profile, idioma: Language) -> list[str]:
    return [f"{item.name[idioma]} — {item.level[idioma]}" for item in perfil.languages]


def to_markdown(propuesta: Proposal, perfil: Profile) -> str:
    """Markdown with the reasons and detected gaps, for saving or reviewing."""
    idioma = propuesta.language
    textos = _MOTIVOS_MD[idioma]
    partes: list[str] = []

    partes.append(f"{textos['sobre_mi']}\n\n{propuesta.about_me.text}")
    if propuesta.about_me.reason:
        partes.append(f"> {textos['motivo']}: {propuesta.about_me.reason}")

    nombres_skills = skill_names(propuesta, perfil)
    if nombres_skills:
        lista_skills = "\n".join(f"{n}. {skill}" for n, skill in enumerate(nombres_skills, start=1))
        partes.append(f"{textos['skills']}\n\n{lista_skills}")
        if propuesta.skills_reason:
            partes.append(f"> {textos['motivo']}: {propuesta.skills_reason}")

    if propuesta.experiences:
        bloques_experiencia = []
        for seleccionada in propuesta.experiences:
            experiencia = perfil.experience(seleccionada.id)
            if experiencia is None:
                bloque = f"**{seleccionada.id}** {textos['no_existe']}"
            else:
                bloque = experience_text(experiencia, idioma)
            if seleccionada.reason:
                bloque += f"\n> {textos['motivo']}: {seleccionada.reason}"
            bloques_experiencia.append(bloque)
        partes.append(f"{textos['experiencia']}\n\n" + "\n\n".join(bloques_experiencia))

    nombres_personales = personal_skill_names(perfil, idioma)
    if nombres_personales:
        lista_personales = "\n".join(f"- {nombre}" for nombre in nombres_personales)
        partes.append(f"{textos['skills_personales']}\n\n{lista_personales}")

    idiomas_texto = language_lines(perfil, idioma)
    if idiomas_texto:
        lista_idiomas = "\n".join(f"- {linea}" for linea in idiomas_texto)
        partes.append(f"{textos['idiomas']}\n\n{lista_idiomas}")

    huecos = (
        "\n".join(f"- {hueco}" for hueco in propuesta.gaps)
        if propuesta.gaps
        else textos["huecos_vacio"]
    )
    partes.append(f"{textos['huecos']}\n\n{huecos}")

    return "\n\n".join(partes) + "\n"
