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
- **Being unfinished is not the same as being wrong.** An entry written in
  only one language is complete for the CV in that language, so it is a
  warning and not an error: a CV imported in Spanish has to be savable
  before anyone has spent a translation call on it.

What is deliberately not validated: that both bullet versions have the same
number of lines. The English and Spanish CV do not have to say the same
thing, and it is the user who writes both.

CONTRACT — implemented by agent A.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from flask_babel import gettext as _

from ancla.profile.model import (
    LANGUAGES,
    AboutMe,
    Bilingual,
    Education,
    Experience,
    Language,
    Profile,
    Skill,
    SpokenLanguage,
)


def language_name(idioma: Language) -> str:
    # A function, not a module-level dict: `_()` has to be evaluated on every
    # call (the current request's language), not once at import time.
    return {"es": _("español"), "en": _("inglés")}[idioma]


# Any {THING} written in the "About me" template.
_HUECO = re.compile(r"\{[^{}]*\}")




@dataclass(frozen=True)
class Issues:
    """What is wrong with an entry, split by whether it stops it being saved.

    `errors` are things the user has to fix before the entry is worth
    keeping: without them it would reach a CV broken, or would never be
    chosen at all. `warnings` are things that are merely unfinished — in
    practice, a translation nobody has paid for yet.

    They used to be a single list, and every caller treated all of it as
    blocking, which is what made a CV imported in one language impossible to
    save: being written in Spanish only is not a defect of the entry, it is
    a job the user may never want to do.
    """

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def messages(self) -> list[str]:
        """Everything found, for a report that only lists and never blocks."""
        return [*self.errors, *self.warnings]

    def __add__(self, otros: "Issues") -> "Issues":
        return Issues(self.errors + otros.errors, self.warnings + otros.warnings)


def written_languages(texto: Bilingual[str]) -> tuple[Language, ...]:
    """The languages an entry is actually written in, decided by the one
    field that identifies it (its title or its name).

    Everything else is then only required in those languages. An entry with
    no title in any language is broken; one with a title in a single
    language is simply half done, and that difference is what the rest of
    this module turns into an error or a warning.
    """
    return tuple(idioma for idioma in LANGUAGES if texto[idioma].strip())


def missing_languages(texto: Bilingual[str]) -> tuple[Language, ...]:
    """The other side of `written_languages`, empty when nothing is missing."""
    escritos = written_languages(texto)
    if not escritos:
        return ()
    return tuple(idioma for idioma in LANGUAGES if idioma not in escritos)


def _untranslated(etiqueta: str, faltan: tuple[Language, ...]) -> list[str]:
    return [
        _(
            "%(etiqueta)s: todavía no está en %(nombre)s. Puedes traducirla desde "
            "«Mi perfil» cuando quieras.",
            etiqueta=etiqueta, nombre=language_name(idioma),
        )
        for idioma in faltan
    ]


def _period_coherence_errors(etiqueta: str, inicio: str, fin: str) -> list[str]:
    """A start year after the end year, shared by experience and education.

    `fin` skips the check whenever it is not itself a year — an `ongoing` /
    `finished` marker or an empty value both mean "no end to compare
    against", and a value carried over from free text that could not be
    split is not a year either. Only two years are ever comparable, so
    anything else is left alone rather than guessed at.
    """
    if not (inicio.isdigit() and fin.isdigit()):
        return []
    if int(inicio) > int(fin):
        return [
            _(
                "%(etiqueta)s: el periodo no es coherente, empieza en %(inicio)s y "
                "acaba en %(fin)s.",
                etiqueta=etiqueta, inicio=inicio, fin=fin,
            )
        ]
    return []


def validate_experience(experiencia: Experience) -> Issues:
    """Issues found, aimed at the user. No errors = can be saved."""
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

    if not experiencia.period_start.strip():
        problemas.append(
            _(
                "%(etiqueta)s: falta el periodo (por ejemplo «2025 - ACTUALIDAD»).",
                etiqueta=etiqueta,
            )
        )
    problemas += _period_coherence_errors(
        etiqueta, experiencia.period_start, experiencia.period_end
    )
    if not experiencia.stack.strip():
        problemas.append(
            _(
                "%(etiqueta)s: falta el stack (las tecnologías que usaste).",
                etiqueta=etiqueta,
            )
        )

    escritos = written_languages(experiencia.title)
    if not escritos:
        problemas.append(_("%(etiqueta)s: falta el título.", etiqueta=etiqueta))
    for idioma in escritos:
        problemas += _bullet_problems(
            experiencia.bullets[idioma], etiqueta, language_name(idioma)
        )

    avisos = _untranslated(etiqueta, missing_languages(experiencia.title))
    if not experiencia.keywords:
        avisos.append(
            _(
                "%(etiqueta)s: no tiene palabras clave, así que casi nunca se elegirá "
                "para un CV. Añade los términos con los que la buscaría una empresa.",
                etiqueta=etiqueta,
            )
        )
    return Issues(problemas, avisos)


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


def validate_skill(skill: Skill) -> Issues:
    etiqueta = _('Skill «%(id)s»', id=skill.id) if skill.id else _("Una skill")
    problemas: list[str] = []

    if not skill.id.strip():
        problemas.append(
            _(
                "Hay una skill sin identificador. El identificador es el nombre del "
                "fichero, por ejemplo «python.yaml»."
            )
        )
    if not written_languages(skill.name):
        problemas.append(_("%(etiqueta)s: falta el nombre.", etiqueta=etiqueta))
    if not skill.category.strip():
        problemas.append(
            _(
                "%(etiqueta)s: no tiene categoría. Se usa para agrupar las skills del "
                "CV y para repartirlas en el «Sobre mí».",
                etiqueta=etiqueta,
            )
        )
    avisos = _untranslated(etiqueta, missing_languages(skill.name))
    if not skill.keywords:
        avisos.append(
            _(
                "%(etiqueta)s: no tiene palabras clave, así que casi nunca se elegirá "
                "para un CV. Añade cómo la nombran las ofertas.",
                etiqueta=etiqueta,
            )
        )
    return Issues(problemas, avisos)


def validate_personal_skill(skill: Skill) -> Issues:
    """Like `validate_skill`, but without requiring a category: there is no
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
    if not written_languages(skill.name):
        problemas.append(_("%(etiqueta)s: falta el nombre.", etiqueta=etiqueta))
    avisos = _untranslated(etiqueta, missing_languages(skill.name))
    if not skill.keywords:
        avisos.append(
            _(
                "%(etiqueta)s: no tiene palabras clave, así que puede que una vacante "
                "la siga marcando como hueco aunque ya la tengas. Añade cómo se "
                "nombra en las ofertas.",
                etiqueta=etiqueta,
            )
        )
    return Issues(problemas, avisos)


def validate_language(idioma: SpokenLanguage) -> Issues:
    """As strict as `validate_skill`: without a level, a language says nothing
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
    escritos = written_languages(idioma.name)
    if not escritos:
        problemas.append(_("%(etiqueta)s: falta el nombre.", etiqueta=etiqueta))
    for cod in escritos:
        if not idioma.level[cod].strip():
            problemas.append(
                _(
                    "%(etiqueta)s: falta el nivel en %(nombre)s (por ejemplo «C1 — Avanzado»).",
                    etiqueta=etiqueta, nombre=language_name(cod),
                )
            )
    avisos = _untranslated(etiqueta, missing_languages(idioma.name))
    if not idioma.keywords:
        avisos.append(
            _(
                "%(etiqueta)s: no tiene palabras clave, así que puede que una vacante "
                "lo siga marcando como hueco aunque ya lo tengas. Añade cómo se "
                "nombra en las ofertas (p. ej. «advanced english», «fluido»).",
                etiqueta=etiqueta,
            )
        )
    return Issues(problemas, avisos)


def validate_education(educacion: Education) -> Issues:
    """Like `validate_language` minus the keywords/level requirement: education
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
    if not educacion.institution.strip():
        problemas.append(_("%(etiqueta)s: falta el centro.", etiqueta=etiqueta))
    if not educacion.period_start.strip():
        problemas.append(
            _(
                "%(etiqueta)s: falta el periodo (por ejemplo «2023 - 2027»).",
                etiqueta=etiqueta,
            )
        )
    problemas += _period_coherence_errors(
        etiqueta, educacion.period_start, educacion.period_end
    )
    if not written_languages(educacion.title):
        problemas.append(_("%(etiqueta)s: falta la titulación.", etiqueta=etiqueta))
    return Issues(problemas, _untranslated(etiqueta, missing_languages(educacion.title)))


def validate_about_me(sobre_mi: AboutMe) -> Issues:
    """Checks that the template has all 6 gaps in each language it is written in."""
    problemas: list[str] = []
    huecos = set(sobre_mi.gaps())
    escritos = written_languages(sobre_mi.template)

    if not escritos:
        return Issues([_("El «Sobre mí» está vacío.")])

    for idioma in escritos:
        nombre = language_name(idioma)
        texto = sobre_mi.template[idioma]

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

    avisos = [
        _(
            "El «Sobre mí» todavía no está en %(nombre)s. Escríbelo cuando vayas a "
            "generar un CV en ese idioma.",
            nombre=language_name(idioma),
        )
        for idioma in missing_languages(sobre_mi.template)
    ]
    return Issues(problemas, avisos)


def validate_profile(perfil: Profile) -> Issues:
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

    total = Issues(problemas)

    if perfil.about_me is None:
        total += Issues([
            _(
                "Falta el «Sobre mí». Escríbelo en «Mi perfil»: es el bloque que abre "
                "el CV y el único que la app compone."
            )
        ])
    else:
        total += validate_about_me(perfil.about_me)

    for experiencia in perfil.experiences:
        total += validate_experience(experiencia)
    for skill in perfil.skills:
        total += validate_skill(skill)
    # Personal skills and languages are optional (unlike technical skills and
    # experience): passing none is not a problem with the profile, it just
    # means those two blocks come out empty in the Proposal.
    for skill in perfil.personal_skills:
        total += validate_personal_skill(skill)
    for idioma in perfil.languages:
        total += validate_language(idioma)
    for educacion in perfil.education:
        total += validate_education(educacion)
    return total


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
