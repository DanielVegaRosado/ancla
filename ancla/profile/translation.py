"""Translates profile entries that only exist in one language.

Separate from `importer.py` on purpose, and it is a quota decision before it
is a design one. The importer used to ask the model for every entry twice,
in Spanish and in English, and the response is what fills the per-minute
budget: roughly one output token per character of CV, so asking for both
languages halved how much of a CV fitted in a single call. Importing in one
language and translating later splits that in two calls, and the second one
falls into a different minute on its own, because the user spends that
minute reading the review screen.

It also matches what people want: someone applying only in Spanish has no
reason to spend a call on an English CV they will never send.

**This works on structured entries, never on the raw CV.** By the time
anything reaches here the user has already reviewed and accepted the fields,
so a translation can be checked field by field against what it came from —
unlike a second pass over the whole document, where a changed sentence would
be invisible.

Three guarantees, and they are enforced here rather than asked of the model:

- **The source language is never written to.** Only the target slot of each
  `Bilingual` is replaced; the side the user wrote is copied through
  untouched, so a model that answers with a "better" version of the original
  cannot reach the profile.
- **An empty field stays empty.** Nothing is invented to fill a gap the
  original does not have.
- **Translating is not rewriting.** The prompt asks for a literal, faithful
  translation, and anything the model returns for a field that was empty, or
  for an entry that was not sent, is dropped.

Never raises: a missing key, a provider failure, or an unreadable answer
come back as the entries exactly as they went in, plus a warning. Writing
the other language by hand works with no provider at all.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace

from flask_babel import gettext as _

from ancla.ai.client import AIClient
from ancla.profile.model import (
    AboutMe,
    Bilingual,
    Education,
    Experience,
    Language,
    Profile,
    Skill,
    SpokenLanguage,
)
from ancla.profile.validation import language_name
from ancla.text import json_block, to_text, to_texts

# The bilingual fields of each entry type, by attribute name. Nothing else
# travels: `stack`, `institution` and the periods are single texts on
# purpose (technology and institution names are proper nouns), and
# `keywords` are how a job posting names a skill, not prose to translate.
TRANSLATABLE_FIELDS: dict[type, tuple[str, ...]] = {
    AboutMe: ("template",),
    Experience: ("title", "bullets"),
    Skill: ("name", "category"),
    SpokenLanguage: ("name", "level"),
    Education: ("title",),
    # The headline under the name ("Data Engineer", "Ingeniero
    # Informático...) — the whole profile, since it is the one bilingual
    # field on it, not a list entry with its own id like the rest here.
    Profile: ("headline",),
}

# Groq's free tier allows 8000 tokens per minute in total (checked against
# the real API). A batch bigger than this would not fit in one call anyway,
# and cutting it here is preferable to a truncated JSON, which loses the
# whole answer instead of the tail of it.
MAX_ENTRIES = 40

SISTEMA = """\
Traduces campos sueltos de un CV que una persona ya ha escrito y revisado. No los \
reescribes: los pasas al otro idioma.

Reglas:
1. Traducción literal y fiel. No mejores el estilo, no resumas, no amplíes, no cambies \
el orden de las ideas ni el tono. Si el original dice tres cosas, la traducción dice \
esas tres cosas.
2. No inventes nada que no esté en el texto original. Un campo vacío se queda vacío.
3. Los nombres propios, las tecnologías y las siglas se dejan como están (Python, \
Docker, PostgreSQL, UEMC, AWS...). No los traduzcas ni los expandas.
4. Una lista de bullets se traduce bullet a bullet y devuelve el MISMO número de \
elementos, en el mismo orden. No fusiones ni dividas bullets.
5. Los huecos entre llaves ({GROUP_A_1}, {GROUP_B_2}...) se copian tal cual, en el mismo \
punto de la frase. Ni los traduzcas ni los quites ni añadas otros.
6. Devuelve exactamente los mismos identificadores y los mismos campos que te paso, sin \
añadir ni quitar ninguno.

Responde ÚNICAMENTE con un JSON, sin texto alrededor ni bloques de código, con esta \
forma: un objeto cuyas claves son los identificadores que te paso, y cuyo valor es un \
objeto con los mismos campos que ese identificador traía, ya traducidos.
Ejemplo: {"0": {"title": "Data Engineer", "bullets": ["Built the pipeline"]}}"""


@dataclass(frozen=True)
class Translation:
    """The entries with the target language filled in where it could be.

    `entries` is always usable and always in the order it came in: on any
    failure it is the list that went in, untouched.
    """

    entries: list = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


def translate(cliente: AIClient, entradas: list, idioma: Language) -> Translation:
    """One call for the whole batch, whatever mix of entry types it holds.

    Batching is the point: translating twelve entries one at a time is
    twelve calls and twelve waits on the per-minute quota, which is what
    makes the "translate everything missing" button worth having. The same
    function serves a single entry — a batch of one.
    """
    pendientes = {
        indice: entrada
        for indice, entrada in enumerate(entradas)
        if _fields_to_translate(entrada, idioma)
    }
    if not pendientes:
        return Translation(list(entradas))
    if not cliente.available():
        return Translation(
            list(entradas), [_("No hay ninguna clave de API configurada. Ve a Ajustes.")]
        )
    if len(pendientes) > MAX_ENTRIES:
        return Translation(
            list(entradas),
            [
                _(
                    "Hay %(cantidad)s entradas sin traducir, demasiadas para una sola "
                    "petición. Tradúcelas por partes con el botón de cada entrada.",
                    cantidad=len(pendientes),
                )
            ],
        )

    try:
        bruto = cliente.complete(SISTEMA, _request(pendientes, idioma))
    except Exception as exc:
        return Translation(
            list(entradas),
            [_("No se ha podido traducir: %(error)s", error=exc)],
        )

    traducciones = _parse(bruto)
    if traducciones is None:
        return Translation(
            list(entradas),
            [_("El modelo no ha devuelto una respuesta interpretable. Vuelve a intentarlo.")],
        )

    resultado = list(entradas)
    sin_traducir = 0
    for indice, entrada in pendientes.items():
        campos = traducciones.get(str(indice), {})
        traducida = _apply(entrada, campos, idioma)
        if traducida is entrada:
            sin_traducir += 1
        resultado[indice] = traducida

    avisos = []
    if sin_traducir:
        avisos.append(
            _(
                "%(cantidad)s entrada(s) se han quedado sin traducir. Vuelve a "
                "intentarlo o escríbelas a mano.",
                cantidad=sin_traducir,
            )
        )
    return Translation(resultado, avisos)


def pending(entradas: list, idioma: Language) -> list:
    """The entries that would come out empty in a CV in `idioma`.

    Used to mark them on screen and to warn before adapting, so nobody
    discovers it by reading a CV with half its sections blank.
    """
    return [entrada for entrada in entradas if _fields_to_translate(entrada, idioma)]


def entry_name(entrada, idioma: Language | None = None) -> str:
    """How to name an entry to the user: its title or name, in whichever
    language it is written in."""
    if isinstance(entrada, AboutMe):
        return _("Sobre mí")
    if isinstance(entrada, Profile):
        # `Profile.name` is a plain string (a person's name reads the same
        # in any language), not the bilingual field being translated here —
        # naming the entry after it would misname what is actually changing.
        return _("Titular")
    etiqueta = getattr(entrada, "title", None) or getattr(entrada, "name", None)
    if etiqueta is None:
        return getattr(entrada, "id", "")
    if idioma is not None and etiqueta[idioma].strip():
        return etiqueta[idioma].strip()
    return etiqueta["es"].strip() or etiqueta["en"].strip() or getattr(entrada, "id", "")


# --------------------------------------------------------------------------


def _fields_to_translate(entrada, idioma: Language) -> tuple[str, ...]:
    """Fields with something written in the other language and nothing in
    `idioma`. An empty original is not one of them: nothing to translate is
    not the same as a translation that is missing."""
    campos = TRANSLATABLE_FIELDS.get(type(entrada), ())
    origen = _other(idioma)
    return tuple(
        campo
        for campo in campos
        if _has_content(getattr(entrada, campo)[origen])
        and not _has_content(getattr(entrada, campo)[idioma])
    )


def _other(idioma: Language) -> Language:
    return "en" if idioma == "es" else "es"


def _has_content(valor: object) -> bool:
    if isinstance(valor, list):
        return any(elemento.strip() for elemento in valor)
    return bool(str(valor).strip())


def _request(pendientes: dict[int, object], idioma: Language) -> str:
    origen = _other(idioma)
    entradas = {
        str(indice): {
            campo: getattr(entrada, campo)[origen]
            for campo in _fields_to_translate(entrada, idioma)
        }
        for indice, entrada in pendientes.items()
    }
    return (
        f"Traduce al {language_name(idioma)} estos campos, "
        f"escritos en {language_name(origen)}:\n"
        + json.dumps(entradas, ensure_ascii=False, indent=2)
    )


def _parse(bruto: str) -> dict[str, dict] | None:
    bloque = json_block(bruto)
    if bloque is None:
        return None
    try:
        datos = json.loads(bloque)
    except json.JSONDecodeError:
        return None
    if not isinstance(datos, dict):
        return None
    return {clave: valor for clave, valor in datos.items() if isinstance(valor, dict)}


def _apply(entrada, campos: dict, idioma: Language):
    """A copy with only the target slot of each field written.

    Returns the entry itself when nothing usable came back, so the caller
    can tell apart "translated" from "left as it was" without comparing
    field by field.
    """
    cambios = {}
    for campo in _fields_to_translate(entrada, idioma):
        original = getattr(entrada, campo)
        traducido = _same_shape(campos.get(campo), original[_other(idioma)])
        if not _has_content(traducido) or not _keeps_gaps(original[_other(idioma)], traducido):
            continue
        cambios[campo] = _with_language(original, idioma, traducido)
    return replace(entrada, **cambios) if cambios else entrada


def _keeps_gaps(original, traducido) -> bool:
    """Whether the translation carries the same `{GROUP_A_1}`-style gaps as
    the original. A lost or invented gap would leave the "About me" of that
    language rendering wrong, which nothing downstream can detect."""
    return _gaps(original) == _gaps(traducido)


def _gaps(valor) -> set[str]:
    texto = " ".join(valor) if isinstance(valor, list) else str(valor)
    return set(re.findall(r"\{[A-Z_0-9]+\}", texto))


def _same_shape(valor: object, original):
    """The model's value read as whatever the original field is — a text or
    a list of texts — so a bullet list that comes back as a single string,
    or a title that comes back as a list, is dropped instead of corrupting
    the entry's shape."""
    if isinstance(original, list):
        return to_texts(valor)
    return to_text(valor)


def _with_language(original: Bilingual, idioma: Language, valor):
    """Only `idioma` changes; the language the user wrote is copied through."""
    if idioma == "es":
        return Bilingual(es=valor, en=original["en"])
    return Bilingual(es=original["es"], en=valor)
