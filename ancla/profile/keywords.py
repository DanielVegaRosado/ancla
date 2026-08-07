"""AI-powered keyword suggestions.

Keywords are what matches a skill or an experience to a job posting's
requirements. Asking the user for them is asking them to think like the
algorithm: they know perfectly well they are proficient in Python, but they
have no particular reason to know they also need to write "scripting",
"backend", or "automation" for their skill to surface when a posting uses
those words. A skill with no keywords is almost never chosen, and the user
has no way to guess why.

**This does not break the never-invent rule.** Keywords never appear on the
CV: they are internal matching metadata. What gets shown is still, word for
word, whatever the user wrote. Even so, they are suggested, never imposed —
the user reviews them, expands them, and trims them, because an
over-generous keyword (putting "Kubernetes" on a Docker skill) would offer
their profile for something it does not actually cover, and that would
erode the promise.

Never raises an exception: if there is no key, if the provider fails, or if
it responds with anything unexpected, a `Sugerencia` comes back with an
empty list and a reason. Suggesting keywords is meant to help, and a helper
that breaks the form you were filling in is not help — but a helper that
fails silently, without saying why, is not much help either: the reason is
what lets the user know whether to check their key in Settings or simply
try again.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from flask_babel import gettext as _

from ancla.ai.client import AIClient, AIError
from ancla.text import normalize


@dataclass(frozen=True)
class Suggestion:
    keywords: list[str] = field(default_factory=list)
    motivo: str = ""

MAX_SUGERENCIAS = 10

SISTEMA = """\
Generas keywords de emparejamiento para el perfil profesional de una persona. \
Son metadatos internos: NO se muestran nunca en su CV. Sirven para que, cuando \
una oferta de empleo use un término, se reconozca que esta skill o experiencia \
lo cubre.

Reglas:
- Incluye cómo se nombra eso realmente en las ofertas, en español y en inglés.
- Incluye sinónimos y variantes de escritura habituales.
- NO inventes tecnologías relacionadas que la persona no haya mencionado. Para \
una skill de Docker no pongas «Kubernetes»: haría que se ofreciera para algo \
que no cubre.
- Todo en minúsculas, sin repetir.

Responde ÚNICAMENTE con un array JSON de cadenas, sin texto alrededor."""


def suggest_for_skill(
    cliente: AIClient, nombre_es: str, nombre_en: str, categoria: str = ""
) -> Suggestion:
    nombres = " / ".join(sorted({n.strip() for n in (nombre_es, nombre_en) if n.strip()}))
    if not nombres:
        return Suggestion()
    peticion = f"Skill: {nombres}"
    if categoria.strip():
        peticion += f"\nCategoría: {categoria.strip()}"
    return _request(cliente, peticion)


def suggest_for_experience(
    cliente: AIClient, titulo: str, bullets: list[str], stack: str = ""
) -> Suggestion:
    if not titulo.strip() and not bullets:
        return Suggestion()
    partes = [f"Experiencia: {titulo.strip()}"]
    if stack.strip():
        partes.append(f"Stack: {stack.strip()}")
    if bullets:
        partes.append("Qué hizo:\n" + "\n".join(f"- {b}" for b in bullets if b.strip()))
    return _request(cliente, "\n".join(partes))


# --------------------------------------------------------------------------


def _request(cliente: AIClient, peticion: str) -> Suggestion:
    if not cliente.available():
        return Suggestion(motivo=_("No hay ninguna clave de API configurada. Ve a Ajustes."))
    try:
        bruto = cliente.complete(SISTEMA, peticion)
    except AIError as exc:
        # ErrorIA's message is already meant to be shown as-is (each client
        # builds it, e.g. "your Groq key is invalid"): it is exactly what the
        # user needs to know what to check in Settings.
        return Suggestion(motivo=str(exc))
    except Exception:
        return Suggestion(motivo=_("No se pudo contactar con el proveedor de IA."))

    sugeridas = _clean(_extract(bruto))
    if not sugeridas:
        return Suggestion(motivo=_("El modelo no ha devuelto ninguna keyword aprovechable."))
    return Suggestion(keywords=sugeridas)


def _extract(bruto: str) -> list[str]:
    inicio, fin = bruto.find("["), bruto.rfind("]")
    if inicio == -1 or fin == -1:
        return []
    try:
        datos = json.loads(bruto[inicio : fin + 1])
    except json.JSONDecodeError:
        return []
    return datos if isinstance(datos, list) else []


def _clean(bruto: list) -> list[str]:
    """No duplicates (comparing without accents), no noise, and a cap on how many."""
    limpias: list[str] = []
    vistas: set[str] = set()
    for elemento in bruto:
        if not isinstance(elemento, str):
            continue
        palabra = re.sub(r"\s+", " ", elemento).strip(" .,;:-").lower()
        clave = normalize(palabra)
        if not clave or clave in vistas or len(palabra) > 40:
            continue
        vistas.add(clave)
        limpias.append(palabra)
        if len(limpias) >= MAX_SUGERENCIAS:
            break
    return limpias
