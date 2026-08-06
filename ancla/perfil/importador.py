"""Analiza el texto de un CV y propone candidatas para las cuatro secciones del
perfil: experiencias, skills técnicas, skills personales e idiomas.

Distinto de `migrador.py`: aquel convierte un formato propio y rígido
(`TITULO_ES:`, `BULLETS_ES:`...) con expresiones regulares, sin IA, porque no
hay ambigüedad que resolver. Un CV cualquiera es prosa libre — cada persona lo
escribe distinto — así que aquí hace falta que un modelo entienda el texto,
no una regex.

El texto que analiza siempre viene de `extraccion.py` (determinista) o de lo
que el usuario pegó a mano: nunca del propio modelo "leyendo" un PDF, que
podría transcribir mal una palabra sin que nadie lo note.

**Nada se guarda aquí.** Este módulo solo propone `Experiencia`/`Skill`/
`IdiomaHablado` con un id provisional; la web las guarda —o no— después de que
el usuario las revise y confirme una por una, igual que con las keywords
sugeridas en `keywords.py`. Nunca lanza excepción de red o de formato: un
fallo aquí se traduce en la lista de candidatas vacía y un aviso, para no
romper la pantalla de subida.

**Skills personales e idiomas usan un catálogo aparte del de skills técnicas**
(igual que en `Perfil`, ver `modelo.py`): el modelo se lo distingue en el
propio prompt (regla 7 y 8), no un filtro posterior — así "Trabajo en equipo"
nunca puede colarse entre tus skills técnicas por error de clasificación.

**No repite lo que ya está en el perfil** (decisión de producto, 2026-07-23):
importar un segundo CV —p. ej. la versión en inglés de uno ya importado en
español— no debe duplicar cada experiencia y skill que ya se guardó la
primera vez, solo lo nuevo. Esto NO se le pide al modelo por prompt: se
compara cada candidata contra `perfil` después de la respuesta
(`normalizar()`, insensible a mayúsculas/acentos, igual que el resto del
proyecto compara nombres) y se descarta la que ya exista con ese nombre en
español o en inglés. Es la misma filosofía que los ids del motor de
selección — garantía por código, no por instrucción al modelo, porque un
prompt se puede ignorar y un filtro posterior no.

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

from ancla.ia.cliente import ClienteIA
from ancla.perfil.modelo import Bilingue, Experiencia, IdiomaHablado, Perfil, Skill
from ancla.texto import a_texto, a_textos, bloque_json, normalizar, slugificar

# El nivel gratuito de Groq limita a 8000 tokens por minuto (comprobado con
# la API real). Ese presupuesto tiene que cubrir el prompt del sistema
# (~450 tokens), este texto y la respuesta del modelo a la vez — un CV
# demasiado largo puede dejar tan poco margen para la respuesta que Groq la
# corte o la rechace directamente. 10.000 caracteres son de sobra para
# cualquier CV real (1-2 páginas) y dejan margen para las tres cosas.
MAX_CARACTERES_CV = 10000

SISTEMA = """\
Analizas el texto de un CV para ayudar a una persona a construir su base de datos \
profesional. No escribes su CV: identificas qué hay en el texto y lo estructuras en \
CUATRO categorías: experiencias, skills técnicas, skills personales e idiomas.

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
6. Para cada skill TÉCNICA, propón una categoría breve (lenguaje, cloud, dato, \
framework...) y unas pocas keywords de cómo se nombra en ofertas de empleo. No añadas \
tecnologías relacionadas que no aparezcan en el texto — de una mención a "Docker" no \
propongas "Kubernetes" como skill aparte.
7. Distingue skill TÉCNICA de skill PERSONAL: una tecnología, lenguaje o herramienta \
concreta (Python, SQL, Docker...) es técnica; una cualidad o forma de trabajar \
(trabajo en equipo, resolución de problemas, atención al detalle, autonomía...) es \
personal, aunque el CV las liste juntas o bajo el mismo apartado. Nunca mezcles las dos.
8. Para cada idioma HABLADO (español, inglés, alemán...) extrae también su nivel tal \
como aparezca (p. ej. "C1 Avanzado", "Nativo", "B2") y tradúcelo igual que el resto — no \
inventes un nivel que no esté escrito. Un idioma hablado no es una skill técnica.
9. Antes de dar la lista de skills técnicas por definitiva, revísala tú mismo: si dos \
entradas nombran la misma tecnología o competencia con distinta redacción (p. ej. \
"Machine Learning" y "Machine Learning Development", o "Data Analysis" y "Data \
Analytics"), dejas solo una — la forma más corta y reconocible. Tampoco conviertas el \
título o el campo de una experiencia en una skill aparte (de un puesto "Data Engineer" \
no propongas la skill "Data Engineering"; de un proyecto de "Quantum Computing" no \
propongas esa etiqueta como skill): ese campo ya queda representado por la propia \
experiencia. Esto NO afecta a las tecnologías concretas que se mencionen dentro de una \
experiencia (lenguajes, librerías, herramientas del stack) — esas sí son skills \
aparte aunque no estén en una lista de skills separada, y ante la duda de si una \
tecnología concreta cuenta o no, inclúyela: es preferible algo de redundancia a que \
falte una tecnología real que sí se menciona.

Responde ÚNICAMENTE con este JSON, sin texto alrededor ni bloques de código:
{
  "experiencias": [
    {"titulo": {"es": "", "en": ""}, "periodo": {"es": "", "en": ""},
     "bullets": {"es": [], "en": []}, "stack": {"es": "", "en": ""},
     "keywords": []}
  ],
  "skills": [
    {"nombre": {"es": "", "en": ""}, "categoria": "", "keywords": []}
  ],
  "skills_personales": [
    {"nombre": {"es": "", "en": ""}, "keywords": []}
  ],
  "idiomas": [
    {"nombre": {"es": "", "en": ""}, "nivel": {"es": "", "en": ""}, "keywords": []}
  ]
}"""


@dataclass(frozen=True)
class ResultadoImportacion:
    experiencias: list[Experiencia] = field(default_factory=list)
    skills: list[Skill] = field(default_factory=list)
    skills_personales: list[Skill] = field(default_factory=list)
    idiomas: list[IdiomaHablado] = field(default_factory=list)
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

    ids_usados: set[str] = (
        {e.id for e in perfil.experiencias}
        | {s.id for s in perfil.skills}
        | {s.id for s in perfil.skills_personales}
        | {i.id for i in perfil.idiomas}
    )

    experiencias, duplicadas_exp = _candidatas(
        datos.get("experiencias"), _a_experiencia, ids_usados,
        "titulo", _nombres_bilingues(perfil.experiencias, "titulo"),
    )
    skills, duplicadas_skills = _candidatas(
        datos.get("skills"), _a_skill, ids_usados,
        "nombre", _nombres_bilingues(perfil.skills, "nombre"),
    )
    skills_personales, duplicadas_sp = _candidatas(
        datos.get("skills_personales"), _a_skill, ids_usados,
        "nombre", _nombres_bilingues(perfil.skills_personales, "nombre"),
    )
    idiomas, duplicadas_idiomas = _candidatas(
        datos.get("idiomas"), _a_idioma, ids_usados,
        "nombre", _nombres_bilingues(perfil.idiomas, "nombre"),
    )
    duplicadas = duplicadas_exp + duplicadas_skills + duplicadas_sp + duplicadas_idiomas

    avisos = []
    if not any((experiencias, skills, skills_personales, idiomas)):
        if duplicadas:
            avisos.append(
                "No hay nada nuevo que añadir: todo lo que se ha reconocido en este "
                "CV ya está en tu perfil."
            )
        else:
            avisos.append(
                "No se ha encontrado ninguna experiencia ni skill reconocible en el texto."
            )
    elif duplicadas:
        avisos.append(
            f"Se ha omitido {duplicadas} elemento(s) que ya estaban en tu perfil "
            "(mismo nombre en español o en inglés) para no duplicarlos."
        )
    return ResultadoImportacion(
        experiencias=experiencias,
        skills=skills,
        skills_personales=skills_personales,
        idiomas=idiomas,
        avisos=avisos,
    )


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


def _nombres_bilingues(items: list, atributo: str) -> set[str]:
    """Los nombres ES/EN ya presentes en el perfil para esta categoría,
    normalizados para comparar sin depender de mayúsculas, acentos o de en
    qué idioma coincida. `atributo` es "titulo" para experiencias, "nombre"
    para skills e idiomas — el resto del modelo comparte esa forma."""
    normalizados: set[str] = set()
    for item in items:
        bilingue = getattr(item, atributo)
        for valor in (bilingue["es"], bilingue["en"]):
            if valor:
                normalizados.add(normalizar(valor))
    return normalizados


def _candidatas(bruto_lista: object, parser, ids_usados: set[str], atributo: str, existentes: set[str]):
    """Parsea una lista de la respuesta del modelo y descarta lo que ya está
    en el perfil (por nombre, no por id — el modelo no conoce los ids del
    perfil). También descarta duplicados dentro del propio lote: si el
    modelo repite el mismo nombre dos veces en una respuesta, la regla 9 del
    prompt se lo pide pero esto lo garantiza aunque no la siga. Devuelve
    `(candidatas, número_de_duplicadas)`."""
    existentes = set(existentes)  # copia: no tocar el set del perfil del llamante
    candidatas = []
    duplicadas = 0
    for bruto in _lista(bruto_lista):
        candidata = parser(_diccionario(bruto), ids_usados)
        if candidata is None:
            continue
        bilingue = getattr(candidata, atributo)
        es, en = normalizar(bilingue["es"]), normalizar(bilingue["en"])
        if (es and es in existentes) or (en and en in existentes):
            duplicadas += 1
            continue
        candidatas.append(candidata)
        existentes.update(nombre for nombre in (es, en) if nombre)
    return candidatas, duplicadas


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


def _a_idioma(datos: dict, ids_usados: set[str]) -> IdiomaHablado | None:
    nombre = _bilingue(datos.get("nombre"))
    if not nombre["es"].strip() and not nombre["en"].strip():
        return None
    id_ = _id_libre(nombre["es"] or nombre["en"], ids_usados)
    return IdiomaHablado(
        id=id_,
        nombre=nombre,
        nivel=_bilingue(datos.get("nivel")),
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
