"""Profile validation.

The files used to be maintained by hand by a single person who knew the
format. As soon as anyone can write the profile from the app — or edit the
YAML by hand — issues need to be reported in the user's own language, not
blow up with a stack trace.

Two criteria explain why the list says what it says:

- **An issue is something that makes the CV worse**, not just something that
  prevents generating it. A skill with no keywords does not break anything:
  it simply will almost never be chosen, and the user has no way to guess
  that just by looking at the screen.
- **Every message says what is missing and where**, starting with the item
  ("Skill «python»: …"), because `validar_perfil` returns the issues for the
  whole profile together, and it has to be possible to go to the right file.

What is deliberately not validated: that both bullet versions have the same
number of lines. The English and Spanish CV do not have to say the same
thing, and it is the user who writes both.

CONTRACT — implemented by agent A.
"""
from __future__ import annotations

import re

from flask_babel import gettext as _

from ancla.profile.model import (
    LANGUAGES,
    AboutMe,
    Education,
    Experience,
    Language,
    Profile,
    Skill,
    SpokenLanguage,
)


def _language_name(idioma: Language) -> str:
    # A function, not a module-level dict: `_()` has to be evaluated on every
    # call (the current request's language), not once at import time.
    return {"es": _("español"), "en": _("inglés")}[idioma]


# Any {THING} written in the "About me" template.
_HUECO = re.compile(r"\{[^{}]*\}")


def validate_experience(experiencia: Experience) -> list[str]:
    """Issues found, aimed at the user. Empty = valid."""
    etiqueta = (
        _('Experiencia «%(id)s»', id=experiencia.id) if experiencia.id else _("Una experiencia")
    )
    problemas: list[str] = []

    if not experiencia.id.strip():
        problemas.append(
            _(
                "Hay una experiencia sin identificador. El identificador es el nombre "
                "del fichero, por ejemplo «data-analyst-movilidad.yaml»."
            )
        )

    for idioma in LANGUAGES:
        nombre = _language_name(idioma)
        if not experiencia.title[idioma].strip():
            problemas.append(_("%(etiqueta)s: falta el título en %(nombre)s.", etiqueta=etiqueta, nombre=nombre))
        if not experiencia.period[idioma].strip():
            problemas.append(
                _(
                    "%(etiqueta)s: falta el periodo en %(nombre)s (por ejemplo «2025 - ACTUALIDAD»).",
                    etiqueta=etiqueta, nombre=nombre,
                )
            )
        if not experiencia.stack[idioma].strip():
            problemas.append(
                _(
                    "%(etiqueta)s: falta el stack en %(nombre)s (las tecnologías que usaste).",
                    etiqueta=etiqueta, nombre=nombre,
                )
            )
        problemas += _bullet_problems(experiencia.bullets[idioma], etiqueta, nombre)

    if not experiencia.keywords:
        problemas.append(
            _(
                "%(etiqueta)s: no tiene palabras clave, así que casi nunca se elegirá "
                "para un CV. Añade los términos con los que la buscaría una empresa.",
                etiqueta=etiqueta,
            )
        )
    return problemas


def _bullet_problems(bullets: list[str], etiqueta: str, nombre: str) -> list[str]:
    if not bullets:
        problemas = [_("%(etiqueta)s: no tiene ningún punto en %(nombre)s.", etiqueta=etiqueta, nombre=nombre)]
    elif any(not bullet.strip() for bullet in bullets):
        problemas = [
            _(
                "%(etiqueta)s: hay algún punto vacío en %(nombre)s; escríbelo o quítalo.",
                etiqueta=etiqueta, nombre=nombre,
            )
        ]
    else:
        problemas = []
    return problemas


def validate_skill(skill: Skill) -> list[str]:
    etiqueta = _('Skill «%(id)s»', id=skill.id) if skill.id else _("Una skill")
    problemas: list[str] = []

    if not skill.id.strip():
        problemas.append(
            _(
                "Hay una skill sin identificador. El identificador es el nombre del "
                "fichero, por ejemplo «python.yaml»."
            )
        )
    for idioma in LANGUAGES:
        if not skill.name[idioma].strip():
            problemas.append(
                _("%(etiqueta)s: falta el nombre en %(nombre)s.", etiqueta=etiqueta, nombre=_language_name(idioma))
            )
    if not skill.category.strip():
        problemas.append(
            _(
                "%(etiqueta)s: no tiene categoría. Se usa para agrupar las skills del "
                "CV y para repartirlas en el «Sobre mí».",
                etiqueta=etiqueta,
            )
        )
    if not skill.keywords:
        problemas.append(
            _(
                "%(etiqueta)s: no tiene palabras clave, así que casi nunca se elegirá "
                "para un CV. Añade cómo la nombran las ofertas.",
                etiqueta=etiqueta,
            )
        )
    return problemas


def validate_personal_skill(skill: Skill) -> list[str]:
    """Like `validar_skill`, but without requiring a category: there is no
    category grouping for personal skills, so asking for one would be an
    unused field."""
    etiqueta = _('Skill personal «%(id)s»', id=skill.id) if skill.id else _("Una skill personal")
    problemas: list[str] = []

    if not skill.id.strip():
        problemas.append(
            _(
                "Hay una skill personal sin identificador. El identificador es el "
                "nombre del fichero, por ejemplo «trabajo-en-equipo.yaml»."
            )
        )
    for idioma in LANGUAGES:
        if not skill.name[idioma].strip():
            problemas.append(
                _("%(etiqueta)s: falta el nombre en %(nombre)s.", etiqueta=etiqueta, nombre=_language_name(idioma))
            )
    if not skill.keywords:
        problemas.append(
            _(
                "%(etiqueta)s: no tiene palabras clave, así que puede que una vacante "
                "la siga marcando como hueco aunque ya la tengas. Añade cómo se "
                "nombra en las ofertas.",
                etiqueta=etiqueta,
            )
        )
    return problemas


def validate_language(idioma: SpokenLanguage) -> list[str]:
    """As strict as `validar_skill`: without a level, a language says nothing
    on a CV, and without keywords it will almost never clear a false gap
    from the job posting."""
    etiqueta = _('Idioma «%(id)s»', id=idioma.id) if idioma.id else _("Un idioma")
    problemas: list[str] = []

    if not idioma.id.strip():
        problemas.append(
            _(
                "Hay un idioma sin identificador. El identificador es el nombre del "
                "fichero, por ejemplo «ingles.yaml»."
            )
        )
    for cod in LANGUAGES:
        nombre_cod = _language_name(cod)
        if not idioma.name[cod].strip():
            problemas.append(_("%(etiqueta)s: falta el nombre en %(nombre)s.", etiqueta=etiqueta, nombre=nombre_cod))
        if not idioma.level[cod].strip():
            problemas.append(
                _(
                    "%(etiqueta)s: falta el nivel en %(nombre)s (por ejemplo «C1 — Avanzado»).",
                    etiqueta=etiqueta, nombre=nombre_cod,
                )
            )
    if not idioma.keywords:
        problemas.append(
            _(
                "%(etiqueta)s: no tiene palabras clave, así que puede que una vacante "
                "lo siga marcando como hueco aunque ya lo tengas. Añade cómo se "
                "nombra en las ofertas (p. ej. «advanced english», «fluido»).",
                etiqueta=etiqueta,
            )
        )
    return problemas


def validate_education(educacion: Education) -> list[str]:
    """Like `validar_idioma` minus the keywords/level requirement: education
    never feeds a gap check, it is just shown in full."""
    etiqueta = (
        _('Educación «%(id)s»', id=educacion.id) if educacion.id else _("Una educación")
    )
    problemas: list[str] = []

    if not educacion.id.strip():
        problemas.append(
            _(
                "Hay una educación sin identificador. El identificador es el nombre "
                "del fichero, por ejemplo «grado-ingenieria.yaml»."
            )
        )
    for idioma in LANGUAGES:
        nombre = _language_name(idioma)
        if not educacion.title[idioma].strip():
            problemas.append(_("%(etiqueta)s: falta la titulación en %(nombre)s.", etiqueta=etiqueta, nombre=nombre))
        if not educacion.institution[idioma].strip():
            problemas.append(_("%(etiqueta)s: falta el centro en %(nombre)s.", etiqueta=etiqueta, nombre=nombre))
        if not educacion.period[idioma].strip():
            problemas.append(
                _(
                    "%(etiqueta)s: falta el periodo en %(nombre)s (por ejemplo «2023 - 2027»).",
                    etiqueta=etiqueta, nombre=nombre,
                )
            )
    return problemas


def validate_about_me(sobre_mi: AboutMe) -> list[str]:
    """Checks that the template has all 6 gaps, in both ES and EN."""
    problemas: list[str] = []
    huecos = set(sobre_mi.gaps())

    for idioma in LANGUAGES:
        nombre = _language_name(idioma)
        texto = sobre_mi.template[idioma]
        if not texto.strip():
            problemas.append(_("El «Sobre mí» está vacío en %(nombre)s.", nombre=nombre))
            continue

        faltan = [hueco for hueco in sobre_mi.gaps() if hueco not in texto]
        if faltan:
            problemas.append(
                _(
                    "Al «Sobre mí» en %(nombre)s le faltan estos huecos: %(huecos)s. "
                    "Escríbelos tal cual donde quieras que entren las skills elegidas.",
                    nombre=nombre, huecos=", ".join(faltan),
                )
            )
        # A {GROUP_A_4} or a {GROUP_C_1} would be left in the final CV as
        # written, and the user would only ever see that by reading the output.
        desconocidos = sorted(set(_HUECO.findall(texto)) - huecos)
        if desconocidos:
            problemas.append(
                _(
                    "El «Sobre mí» en %(nombre)s tiene huecos que el sistema no sabe "
                    "rellenar: %(desconocidos)s. Los válidos son: %(validos)s.",
                    nombre=nombre,
                    desconocidos=", ".join(desconocidos),
                    validos=", ".join(sobre_mi.gaps()),
                )
            )
    return problemas


def validate_profile(perfil: Profile) -> list[str]:
    """Validates the whole thing: duplicate ids, empty profile, missing "About me"."""
    problemas: list[str] = []

    if perfil.is_empty():
        problemas.append(
            _(
                "El perfil está vacío. Añade al menos una experiencia y una skill "
                "antes de generar un CV: la app solo puede elegir entre lo que tú "
                "hayas escrito."
            )
        )
    else:
        if not perfil.experiences:
            problemas.append(
                _("No hay ninguna experiencia, así que el CV saldría sin proyectos.")
            )
        if not perfil.skills:
            problemas.append(
                _(
                    "No hay ninguna skill, así que el CV saldría sin la sección "
                    "técnica y el «Sobre mí» no se podría componer."
                )
            )

    problemas += _duplicates(
        [experiencia.id for experiencia in perfil.experiences], _("experiencias")
    )
    problemas += _duplicates([skill.id for skill in perfil.skills], _("skills"))
    problemas += _duplicates(
        [skill.id for skill in perfil.personal_skills], _("skills personales")
    )
    problemas += _duplicates([idioma.id for idioma in perfil.languages], _("idiomas"))
    problemas += _duplicates([educacion.id for educacion in perfil.education], _("educación"))

    if perfil.about_me is None:
        problemas.append(
            _(
                "Falta el «Sobre mí». Escríbelo en «Mi perfil»: es el bloque que abre "
                "el CV y el único que la app compone."
            )
        )
    else:
        problemas += validate_about_me(perfil.about_me)

    for experiencia in perfil.experiences:
        problemas += validate_experience(experiencia)
    for skill in perfil.skills:
        problemas += validate_skill(skill)
    # Personal skills and languages are optional (unlike technical skills and
    # experience): passing none is not a problem with the profile, it just
    # means those two blocks come out empty in the Proposal.
    for skill in perfil.personal_skills:
        problemas += validate_personal_skill(skill)
    for idioma in perfil.languages:
        problemas += validate_language(idioma)
    for educacion in perfil.education:
        problemas += validate_education(educacion)
    return problemas


def _duplicates(ids: list[str], que: str) -> list[str]:
    """Normally the id is the file name and cannot repeat, but it can if
    `python.yaml` and `python.yml` coexist."""
    vistos: set[str] = set()
    repetidos: list[str] = []
    for id_ in ids:
        if id_ in vistos and id_ not in repetidos:
            repetidos.append(id_)
        vistos.add(id_)
    if not repetidos:
        return []
    return [
        _(
            "Hay %(que)s con el mismo identificador (%(repetidos)s). Cada una "
            "tiene que tener el suyo: es como el CV guardado sabe a cuál se refiere.",
            que=que, repetidos=", ".join(repetidos),
        )
    ]
