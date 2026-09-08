"""Builds the field catalog a CV template renders from a proposal.

What is left of the old `fill.py` after the `.docx` export path was
removed: the part that was never docx-specific to begin with — it built
the same Jinja context `html_layout.py` still fills an HTML template with,
long before an HTML path existed. `docx-templates/README.md`'s field
catalog described this same context; the printable HTML templates
(`html-templates/*.html`) are what still use it.

`Experience` has no separate company field (see `ancla/profile/model.py`):
`title` already bundles "role · company" together, the same way it is
shown everywhere else in the app (Proposal screen, `proposal/format.py`).
`empresa` is kept in the context because the field catalog names it, but is
always empty — a template that wants role and company on separate lines has
nothing to split them from and has to fold both into `puesto`.

Each experience also carries `stack` (the tech-stack line, e.g. "Python,
FastAPI, PostgreSQL"): not in the original field catalog, added because a
real template shows it under every experience and the data was already
sitting unused on `Experience.stack`. Optional — a template that ignores
the field simply doesn't show it.

`contacto`, `titular`, `educacion` and `foto` mirror the "always complete,
never selected" rule that already governs `skills_personales`/`idiomas`:
none of the four go through `selection/engine.py`, so they are read live
from the profile, not from `Proposal`.
"""
from __future__ import annotations

from ancla.profile.model import Experience, Language, Profile, Proposal, SelectedExperience, period_text
from ancla.proposal.format import language_lines, personal_skill_names, skill_names

# Section headers are plain text baked into each template (not tags a
# template author fills in), so they used to be permanently Spanish even
# when the proposal itself was generated in English. `propuesta.language`
# already tells us which; this is the ES/EN pair for each header a real
# template uses. Kept as separate keys so each template's own wording
# survives, rather than forcing every template to share one generic label.
_ETIQUETAS: dict[str, dict[Language, str]] = {
    "contacto": {"es": "CONTACTO", "en": "CONTACT"},
    "educacion": {"es": "EDUCACIÓN", "en": "EDUCATION"},
    "skills_tecnicas": {"es": "SKILLS TÉCNICAS", "en": "TECHNICAL SKILLS"},
    "skills": {"es": "SKILLS", "en": "SKILLS"},
    "skills_personales": {"es": "SKILLS PERSONALES", "en": "PERSONAL SKILLS"},
    # Standalone subtitles ("TECHNICAL", "PERSONAL"), without repeating
    # "SKILLS" — for a template that groups one "SKILLS" header with both
    # of these underneath, instead of two independent headers.
    "tecnicas": {"es": "TÉCNICAS", "en": "TECHNICAL"},
    "personales": {"es": "PERSONALES", "en": "PERSONAL"},
    "idiomas": {"es": "IDIOMAS", "en": "LANGUAGES"},
    "sobre_mi": {"es": "SOBRE MÍ", "en": "ABOUT ME"},
    "experiencia_relevante": {"es": "EXPERIENCIA RELEVANTE", "en": "RELEVANT EXPERIENCE"},
    "experiencia": {"es": "EXPERIENCIA", "en": "EXPERIENCE"},
}


def _etiquetas(idioma: Language) -> dict[str, str]:
    return {f"etiqueta_{clave}": valores[idioma] for clave, valores in _ETIQUETAS.items()}


def resolved_selection(propuesta: Proposal, perfil: Profile) -> list[tuple[SelectedExperience, Experience]]:
    """The proposal's chosen experiences, in the same relevance order,
    paired with the profile data they point to. One that no longer exists
    there is dropped rather than shown as a blank block — same rule
    `proposal/format.py` follows for the copy-paste text."""
    parejas = ((seleccionada, perfil.experience(seleccionada.id)) for seleccionada in propuesta.experiences)
    return [(seleccionada, experiencia) for seleccionada, experiencia in parejas if experiencia is not None]


def resolved_experiences(propuesta: Proposal, perfil: Profile) -> list[Experience]:
    return [experiencia for _, experiencia in resolved_selection(propuesta, perfil)]


#: Non-breaking hyphen (U+2011), sometimes present in pasted text (e.g. a
#: "H‑Z‑H" bullet). Swapped for a plain hyphen (U+002D, visually identical)
#: only in the rendered CV; the profile itself is never touched, so this
#: doesn't cross rule 2 ("never rewrite the user").
_GUION_NO_SEPARABLE = "‑"


def _sin_guion_no_separable(texto: str) -> str:
    return texto.replace(_GUION_NO_SEPARABLE, "-")


def build_context(
    propuesta: Proposal,
    perfil: Profile,
    experiencias: list[Experience],
    nombre: str,
    foto: str = "",
) -> dict:
    idioma = propuesta.language
    nombre_primero, _, nombre_resto = nombre.partition(" ")
    return {
        **_etiquetas(idioma),
        "nombre": nombre,
        # Some templates set the first name and the rest in different styles
        # ("**DANIEL** VEGA"), which a single tag cannot express: formatting
        # lives on the run, not on the text. Split on the first space; a
        # template that doesn't need it keeps using `nombre` whole.
        "nombre_primero": nombre_primero,
        "nombre_resto": nombre_resto,
        "sobre_mi": _sin_guion_no_separable(propuesta.about_me.text),
        "experiencias": [
            {
                "puesto": _sin_guion_no_separable(experiencia.title[idioma]),
                "empresa": "",
                "fechas": period_text(experiencia.period_start, experiencia.period_end, idioma),
                "bullets": [_sin_guion_no_separable(b) for b in experiencia.bullets[idioma]],
                "stack": _sin_guion_no_separable(experiencia.stack),
            }
            for experiencia in experiencias
        ],
        "skills": skill_names(propuesta, perfil),
        "idiomas": language_lines(perfil, idioma),
        "skills_personales": personal_skill_names(perfil, idioma),
        "contacto": [_sin_guion_no_separable(linea) for linea in perfil.contact],
        "titular": _sin_guion_no_separable(perfil.headline[idioma]),
        "educacion": [
            {
                "titulo": _sin_guion_no_separable(entrada.title[idioma]),
                "centro": _sin_guion_no_separable(entrada.institution),
                "fechas": period_text(entrada.period_start, entrada.period_end, idioma),
            }
            for entrada in perfil.education
        ],
        "foto": foto,
    }
