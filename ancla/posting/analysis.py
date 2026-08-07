"""Extracts data from the job posting the user pasted in.

Only the deterministic, cheap part: company and position, to name the CV in
the archive and to be able to warn that one for that company already
exists before spending a call on the model. The real requirements analysis
is done by the engine, within that single call.

Looked up in three passes, from most to least reliable, stopping at the
first hit: an explicit label ("Company:"), a set phrase ("Join X", "X is
hiring"), and finally the header job boards tend to paste (first line the
position, second line the company). As soon as confidence drops below that,
an empty string is returned: a made-up value in the archive's file name is
worse than an empty field the user fills in in two seconds.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ancla.text import normalize

# Headers are up top; further down the description starts and anything
# found there is noise.
LINEAS_CABECERA = 40
MAX_CARACTERES_CAMPO = 80

_ETIQUETAS_EMPRESA = (
    r"empresa|compa[ñn][ií]a|organizaci[oó]n|entidad|company|employer|hiring company"
)
_ETIQUETAS_PUESTO = (
    r"puesto|cargo|posici[oó]n|vacante|oferta|t[ií]tulo del puesto"
    r"|position|role|job title|job"
)

# Words that give away a job title. Not a taxonomy: it is what actually
# shows up in the postings people paste in.
_PALABRAS_DE_PUESTO = (
    "desarrollador", "desarrolladora", "programador", "programadora", "ingenier",
    "analista", "cientific", "arquitect", "tecnic", "consultor", "becari",
    "practicas", "especialista", "responsable", "jefe", "director", "gestor",
    "administrador", "investigador", "disenador",
    "developer", "engineer", "scientist", "analyst", "architect", "intern",
    "internship", "manager", "designer", "specialist", "consultant", "lead",
    "trainee", "researcher", "devops", "sre", "backend", "frontend", "fullstack",
    "full stack", "data", "qa", "tester",
)

# A header is a title, not a sentence. If the line says someone is looking
# for someone, it is prose, not the job's name.
_MARCAS_DE_FRASE = (
    "busca", "buscamos", "estamos", "ofrecemos", "requisitos",
    "we are", "is hiring", "hiring for", "join us",
)

# Work mode, schedule, and other job-board trimmings: never the company.
_RUIDO = (
    "remoto", "remote", "hibrido", "hybrid", "presencial", "on-site", "onsite",
    "jornada", "full-time", "part-time", "tiempo completo", "media jornada",
    "salario", "salary", "contrato", "publicado", "solicitar", "apply",
    "hace ", " ago", "candidatos", "applicants",
)

_SUFIJOS_EMPRESA = r"s\.?l\.?u?\.?|s\.?a\.?|inc|ltd|llc|gmbh|b\.?v\.?|corp|group|ag|plc"

# A company name: up to four capitalised words. The patterns below take
# capitalisation seriously, so no global IGNORECASE (it would defeat the
# [A-Z] classes): each trigger word carries its own `(?i:...)`.
_NOMBRE = r"(?P<nombre>[A-ZÁÉÍÓÚÑ][\w&.\-]*(?:\s+[A-ZÁÉÍÓÚÑ0-9][\w&.\-]*){0,3})"

_FRASES_EMPRESA = (
    rf"(?i:[uú]nete a|join)\s+{_NOMBRE}",
    rf"^\s*{_NOMBRE}\s+(?i:busca|est[aá] buscando|selecciona|ampl[ií]a)\b",
    rf"(?i:\ben)\s+{_NOMBRE}\s+(?i:buscamos|estamos buscando)\b",
    rf"^\s*(?i:sobre|acerca de|about(?: us at)?)\s+{_NOMBRE}\s*$",
)


@dataclass(frozen=True)
class JobPostingData:
    company: str = ""
    position: str = ""


def extract_data(vacante: str) -> JobPostingData:
    """Tries to guess the company and position from the pasted text.

    A heuristic: returns empty strings when unsure, and the web layer
    always lets the user correct them. Never blocks the flow.
    """
    texto = vacante or ""
    lineas = [_strip_markdown(linea) for linea in texto.splitlines()]
    lineas = [linea for linea in lineas if linea][:LINEAS_CABECERA]

    empresa = _by_label(lineas, _ETIQUETAS_EMPRESA) or _by_stock_phrase(lineas)
    puesto = _by_label(lineas, _ETIQUETAS_PUESTO)

    if not puesto and lineas and _looks_like_position(lineas[0]):
        puesto = _clean(lineas[0])
        # Typical job-board header: the position, then the company right below it.
        if not empresa and len(lineas) > 1:
            empresa = _company_from_header(lineas[1])

    return JobPostingData(company=empresa, position=puesto)


def _by_label(lineas: list[str], etiquetas: str) -> str:
    patron = re.compile(rf"^\s*(?:{etiquetas})\s*[:：\-–—]\s*(.+)$", re.IGNORECASE)
    for linea in lineas:
        encontrado = patron.match(linea)
        if not encontrado:
            continue
        valor = _clean(encontrado.group(1))
        if valor:
            return valor
    return ""


def _by_stock_phrase(lineas: list[str]) -> str:
    cabecera = "\n".join(lineas)
    for patron in _FRASES_EMPRESA:
        encontrado = re.search(patron, cabecera, re.MULTILINE)
        if not encontrado:
            continue
        nombre = _clean(encontrado.group("nombre"))
        if nombre and _looks_like_proper_noun(nombre):
            return nombre
    return ""


def _company_from_header(linea: str) -> str:
    """The header's second line, if it genuinely looks like a company."""
    candidato = _clean(linea)
    if not candidato or _looks_like_position(candidato) or not _looks_like_proper_noun(candidato):
        return ""
    return candidato


def _looks_like_position(linea: str) -> bool:
    bruto = _strip_markdown(linea)
    if bruto.endswith((".", "!", "?", ":", ";")):
        return False
    if any(marca in normalize(bruto) for marca in _MARCAS_DE_FRASE):
        return False
    candidato = _clean(linea)
    if not candidato or len(candidato.split()) > 12:
        return False
    normalizado = normalize(candidato)
    return any(palabra in normalizado for palabra in _PALABRAS_DE_PUESTO)


def _looks_like_proper_noun(valor: str) -> bool:
    """Rules out sentences, locations, and job-board trimmings."""
    if not valor[0].isupper() or len(valor.split()) > 5:
        return False
    if "," in valor:
        # "Acme, S.L." is fine; "Madrid, Spain" is not.
        cola = valor.rsplit(",", 1)[1].strip()
        if not re.fullmatch(_SUFIJOS_EMPRESA, normalize(cola)):
            return False
    return True


def _clean(valor: str) -> str:
    """Leaves the field ready to display, or empty if it is not worth showing."""
    texto = _strip_markdown(valor)
    # Job boards chain fields with · or |: the first one is the one that matters.
    texto = re.split(r"[·|•]", texto)[0]
    texto = re.sub(
        r"\((?:[mfhxdwv]\s*/[^)]*|remoto|remote|h[íi]brido|hybrid|presencial"
        r"|on-?site|full[\s-]?time|part[\s-]?time)\)",
        "",
        texto,
        flags=re.IGNORECASE,
    )
    texto = re.sub(r"\s+", " ", texto).strip(" \t\"'“”«»-–—…").strip()
    # A trailing period is unwanted, except when it is part of the legal
    # name ("S.L.").
    if not re.search(r"(?:\b\w\.){2,}$", texto):
        texto = texto.rstrip(".,;:").strip()

    if not texto or len(texto) > MAX_CARACTERES_CAMPO:
        return ""
    # The noise filter also applies to the position, not just the company.
    # This is deliberate, and has a known cost: "Remote backend developer"
    # yields an empty position. Accepted because the field is a two-second
    # fix in the web UI, and because that same filter is what stops a CV
    # being archived under "Full-time". If this ever becomes annoying, the
    # fix is to split into two noise lists (one per field), not to loosen
    # this one.
    normalizado = normalize(texto)
    if any(ruido in normalizado for ruido in _RUIDO):
        return ""
    return texto


def _strip_markdown(linea: str) -> str:
    sin_viñeta = re.sub(r"^\s*(?:[-*+•]|\d+[.)])\s+", "", linea)
    return re.sub(r"[*_#`]", "", sin_viñeta).strip()
