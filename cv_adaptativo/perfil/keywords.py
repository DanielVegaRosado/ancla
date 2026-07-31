"""Sugerencia de keywords con IA.

Las keywords son lo que empareja una skill o una experiencia con los requisitos
de una vacante. Pedírselas al usuario es pedirle que piense como el algoritmo:
sabe perfectamente que domina Python, pero no tiene por qué saber que hay que
escribir también «scripting», «backend» o «automatización» para que su skill
salga cuando una oferta use esas palabras. Una skill sin keywords casi nunca se
elige, y el usuario no tiene forma de adivinar por qué.

**Esto no rompe la regla de no inventar.** Las keywords no aparecen jamás en el
CV: son metadatos internos de emparejamiento. Lo que se muestra sigue saliendo
palabra por palabra de lo que escribió el usuario. Aun así se sugieren y no se
imponen — el usuario las revisa, las amplía y las recorta, porque una keyword
demasiado generosa (poner «Kubernetes» en una skill de Docker) haría que su
perfil se ofreciera para algo que no cubre, y eso sí erosionaría la promesa.

Nunca lanza excepción: si no hay clave, si el proveedor falla o si responde
cualquier cosa, se devuelve un `Sugerencia` con la lista vacía y un motivo.
Sugerir keywords es una ayuda, y una ayuda que rompe el formulario donde
estabas escribiendo no es una ayuda — pero una ayuda que falla en silencio,
sin decir por qué, tampoco lo es: el motivo es lo que le permite al usuario
saber si tiene que revisar su clave en Ajustes o simplemente reintentar.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from flask_babel import gettext as _

from cv_adaptativo.ia.cliente import ClienteIA, ErrorIA
from cv_adaptativo.texto import normalizar


@dataclass(frozen=True)
class Sugerencia:
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


def sugerir_para_skill(
    cliente: ClienteIA, nombre_es: str, nombre_en: str, categoria: str = ""
) -> Sugerencia:
    nombres = " / ".join(sorted({n.strip() for n in (nombre_es, nombre_en) if n.strip()}))
    if not nombres:
        return Sugerencia()
    peticion = f"Skill: {nombres}"
    if categoria.strip():
        peticion += f"\nCategoría: {categoria.strip()}"
    return _pedir(cliente, peticion)


def sugerir_para_experiencia(
    cliente: ClienteIA, titulo: str, bullets: list[str], stack: str = ""
) -> Sugerencia:
    if not titulo.strip() and not bullets:
        return Sugerencia()
    partes = [f"Experiencia: {titulo.strip()}"]
    if stack.strip():
        partes.append(f"Stack: {stack.strip()}")
    if bullets:
        partes.append("Qué hizo:\n" + "\n".join(f"- {b}" for b in bullets if b.strip()))
    return _pedir(cliente, "\n".join(partes))


# --------------------------------------------------------------------------


def _pedir(cliente: ClienteIA, peticion: str) -> Sugerencia:
    if not cliente.disponible():
        return Sugerencia(motivo=_("No hay ninguna clave de API configurada. Ve a Ajustes."))
    try:
        bruto = cliente.completar(SISTEMA, peticion)
    except ErrorIA as exc:
        # El mensaje de ErrorIA ya está pensado para enseñarse tal cual (lo
        # construye cada cliente, p. ej. «tu clave de Groq no es válida»): es
        # justo lo que el usuario necesita para saber qué revisar en Ajustes.
        return Sugerencia(motivo=str(exc))
    except Exception:
        return Sugerencia(motivo=_("No se pudo contactar con el proveedor de IA."))

    sugeridas = _limpiar(_extraer(bruto))
    if not sugeridas:
        return Sugerencia(motivo=_("El modelo no ha devuelto ninguna keyword aprovechable."))
    return Sugerencia(keywords=sugeridas)


def _extraer(bruto: str) -> list[str]:
    inicio, fin = bruto.find("["), bruto.rfind("]")
    if inicio == -1 or fin == -1:
        return []
    try:
        datos = json.loads(bruto[inicio : fin + 1])
    except json.JSONDecodeError:
        return []
    return datos if isinstance(datos, list) else []


def _limpiar(bruto: list) -> list[str]:
    """Sin duplicados (comparando sin acentos), sin ruido y con tope."""
    limpias: list[str] = []
    vistas: set[str] = set()
    for elemento in bruto:
        if not isinstance(elemento, str):
            continue
        palabra = re.sub(r"\s+", " ", elemento).strip(" .,;:-").lower()
        clave = normalizar(palabra)
        if not clave or clave in vistas or len(palabra) > 40:
            continue
        vistas.add(clave)
        limpias.append(palabra)
        if len(limpias) >= MAX_SUGERENCIAS:
            break
    return limpias
