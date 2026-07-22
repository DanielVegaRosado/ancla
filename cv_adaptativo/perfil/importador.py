"""Analiza el texto de un CV y propone experiencias y skills candidatas.

Distinto de `migrador.py`: aquel convierte un formato propio y rígido
(`TITULO_ES:`, `BULLETS_ES:`...) con expresiones regulares, sin IA, porque no
hay ambigüedad que resolver. Un CV cualquiera es prosa libre — cada persona lo
escribe distinto — así que aquí hace falta que un modelo entienda el texto,
no una regex.

El texto que analiza siempre viene de `extraccion.py` (determinista) o de lo
que el usuario pegó a mano: nunca del propio modelo "leyendo" un PDF, que
podría transcribir mal una palabra sin que nadie lo note.

**Nada se guarda aquí.** Este módulo solo propone `Experiencia`/`Skill` con un
id provisional; la web las guarda —o no— después de que el usuario las revise
y confirme una por una, igual que con las keywords sugeridas en `keywords.py`.
Nunca lanza excepción de red o de formato: un fallo aquí se traduce en la
lista de candidatas vacía y un aviso, para no romper la pantalla de subida.

**Traduce cuando falta un idioma** (decisión de producto, 2026-07-22): si el
CV está solo en español, el modelo propone también la versión en inglés, y al
revés. Es la única excepción consciente a "nunca reescribir al usuario" —
aquí no hay nada escrito todavía que reescribir, y el usuario revisa la
traducción antes de que se guarde nada. **Pendiente para v1.1:** una
traducción de mayor calidad apoyada en diccionarios (Oxford/Cambridge) en vez
de dejarla enteramente al criterio del modelo.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from cv_adaptativo.ia.cliente import ClienteIA
from cv_adaptativo.perfil.modelo import Bilingue, Experiencia, Perfil, Skill
from cv_adaptativo.texto import a_texto, a_textos, bloque_json, slugificar

# El nivel gratuito de Groq limita a 8000 tokens por minuto (comprobado con
# la API real). Ese presupuesto tiene que cubrir el prompt del sistema
# (~450 tokens), este texto y la respuesta del modelo a la vez — un CV
# demasiado largo puede dejar tan poco margen para la respuesta que Groq la
# corte o la rechace directamente. 10.000 caracteres son de sobra para
# cualquier CV real (1-2 páginas) y dejan margen para las tres cosas.
MAX_CARACTERES_CV = 10000

SISTEMA = """\
Analizas el texto de un CV para ayudar a una persona a construir su base de datos \
profesional. No escribes su CV: identificas qué experiencias (puestos, proyectos) y \
qué skills técnicas aparecen en el texto, y las estructuras.

Reglas:
1. Extrae SOLO lo que está literalmente en el texto. No añadas responsabilidades, \
logros, cifras o fechas que no aparezcan.
2. Si un dato no está en el texto, deja ese campo vacío. No lo completes con un \
supuesto razonable, por plausible que parezca.
3. El texto puede estar en un solo idioma. Si falta la versión en el otro, TRADUCE \
de forma literal y fiel — no reformules ni mejores el estilo, traduce el contenido \
tal cual está.
4. Ante la duda entre si algo es una experiencia (un puesto o proyecto con contexto \
propio) o solo una skill suelta mencionada de pasada, propón skill. Inventar una \
experiencia alrededor de una mención suelta es peor error que perder una experiencia.
5. Cada puesto o proyecto distinto es una experiencia separada. Nunca fusiones ni \
resumas varias experiencias en una.
6. Para cada skill, propón una categoría breve (lenguaje, cloud, dato, framework...) \
y unas pocas keywords de cómo se nombra en ofertas de empleo. No añadas tecnologías \
relacionadas que no aparezcan en el texto — de una mención a "Docker" no propongas \
"Kubernetes" como skill aparte.

Responde ÚNICAMENTE con este JSON, sin texto alrededor ni bloques de código:
{
  "experiencias": [
    {"titulo": {"es": "", "en": ""}, "periodo": {"es": "", "en": ""},
     "bullets": {"es": [], "en": []}, "stack": {"es": "", "en": ""},
     "keywords": []}
  ],
  "skills": [
    {"nombre": {"es": "", "en": ""}, "categoria": "", "keywords": []}
  ]
}"""


@dataclass(frozen=True)
class ResultadoImportacion:
    experiencias: list[Experiencia] = field(default_factory=list)
    skills: list[Skill] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


def analizar_cv(cliente: ClienteIA, texto_cv: str, perfil: Perfil) -> ResultadoImportacion:
    """Una sola llamada al modelo. `perfil` se usa solo para que los ids
    provisionales de las candidatas no choquen con los que ya existen."""
    texto = texto_cv.strip()
    if not texto:
        return ResultadoImportacion(avisos=["No hay texto que analizar."])
    if not cliente.disponible():
        return ResultadoImportacion(
            avisos=["No hay ninguna clave de API configurada. Ve a Ajustes."]
        )

    if len(texto) > MAX_CARACTERES_CV:
        texto = texto[:MAX_CARACTERES_CV] + "\n[...texto recortado...]"

    try:
        bruto = cliente.completar(SISTEMA, texto)
    except Exception as exc:
        return ResultadoImportacion(avisos=[f"No se ha podido analizar el CV: {exc}"])

    datos = _extraer_json(bruto)
    if datos is None:
        return ResultadoImportacion(
            avisos=["El modelo no ha devuelto una respuesta interpretable. Vuelve a intentarlo."]
        )

    ids_usados: set[str] = {e.id for e in perfil.experiencias} | {
        s.id for s in perfil.skills
    } | {s.id for s in perfil.skills_personales}

    experiencias = [
        exp
        for bruto_exp in _lista(datos.get("experiencias"))
        if (exp := _a_experiencia(_diccionario(bruto_exp), ids_usados)) is not None
    ]
    skills = [
        skill
        for bruto_skill in _lista(datos.get("skills"))
        if (skill := _a_skill(_diccionario(bruto_skill), ids_usados)) is not None
    ]

    avisos = []
    if not experiencias and not skills:
        avisos.append(
            "No se ha encontrado ninguna experiencia ni skill reconocible en el texto."
        )
    return ResultadoImportacion(experiencias=experiencias, skills=skills, avisos=avisos)


# --------------------------------------------------------------------------
# Respuesta del modelo -> candidatas
# --------------------------------------------------------------------------


def _extraer_json(bruto: str) -> dict | None:
    bloque = bloque_json(bruto)
    if bloque is None:
        return None
    try:
        datos = json.loads(bloque)
    except json.JSONDecodeError:
        return None
    return datos if isinstance(datos, dict) else None


def _a_experiencia(datos: dict, ids_usados: set[str]) -> Experiencia | None:
    titulo = _bilingue(datos.get("titulo"))
    # Sin título no hay nada que enseñar en la revisión: se descarta, no se
    # propone una candidata vacía.
    if not titulo["es"].strip() and not titulo["en"].strip():
        return None
    id_ = _id_libre(titulo["es"] or titulo["en"], ids_usados)
    return Experiencia(
        id=id_,
        titulo=titulo,
        periodo=_bilingue(datos.get("periodo")),
        bullets=_bilingue_lista(datos.get("bullets")),
        stack=_bilingue(datos.get("stack")),
        keywords=a_textos(datos.get("keywords")),
    )


def _a_skill(datos: dict, ids_usados: set[str]) -> Skill | None:
    nombre = _bilingue(datos.get("nombre"))
    if not nombre["es"].strip() and not nombre["en"].strip():
        return None
    id_ = _id_libre(nombre["es"] or nombre["en"], ids_usados)
    return Skill(
        id=id_,
        nombre=nombre,
        categoria=a_texto(datos.get("categoria")),
        keywords=a_textos(datos.get("keywords")),
    )


def _bilingue(datos: object) -> Bilingue[str]:
    datos = datos if isinstance(datos, dict) else {}
    return Bilingue(es=a_texto(datos.get("es")), en=a_texto(datos.get("en")))


def _bilingue_lista(datos: object) -> Bilingue[list[str]]:
    datos = datos if isinstance(datos, dict) else {}
    return Bilingue(es=a_textos(datos.get("es")), en=a_textos(datos.get("en")))


def _id_libre(nombre: str, ids_usados: set[str]) -> str:
    """Id provisional a partir del nombre; el usuario lo revisa igual que en
    los formularios manuales. Con sufijo si ya está usado en este lote o en
    el perfil, para que dos candidatas nunca choquen entre sí."""
    base = slugificar(nombre)
    candidato, n = base, 2
    while candidato in ids_usados:
        candidato = f"{base}-{n}"
        n += 1
    ids_usados.add(candidato)
    return candidato


def _lista(valor: object) -> list:
    return valor if isinstance(valor, list) else []


def _diccionario(valor: object) -> dict:
    return valor if isinstance(valor, dict) else {}
