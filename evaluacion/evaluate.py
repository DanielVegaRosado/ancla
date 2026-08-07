"""Test bench for the selection engine (checks + transcript + AI judge).

Ported from MedAI's pattern (`evaluacion/evaluar_bots.py`): runs real cases
against **the exact logic the app uses**, without going through the web
layer, and deliberately produces two separate files.

It exists to answer a question no test suite answers: *is the proposal any
good?* Unit tests check that the engine honours its contract; this checks
whether the selection is actually useful. Without it, tweaking the prompt is
tuning blind.

Three layers, cheapest to most expensive:

1. **Deterministic checks** (`checks.py`, 0 tokens) — what a machine
   can verify on its own. If one fails, that is a defect, not an opinion.
2. **Transcript** — the raw proposals, ungraded, so a person can judge them
   with their own criteria.
3. **AI judge** — a separate call, independent of the one that generated the
   proposal, scoring a rubric.

The order of the two files matters: **the AI judge has biases** (it rewards
length and confident-sounding text), so your own judgement has to form from
reading the transcript before you see any score. Even more so here than in
MedAI: nobody judges whether a CV represents someone better than that person.

Usage (from `app/`):

    python -m evaluacion.evaluate                 # everything
    python -m evaluacion.evaluate --sin-juez      # skip the judge's calls
    python -m evaluacion.evaluate --perfil perfil-ejemplo
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from ancla.ai.client import AIError
from ancla.ai.groq import GroqClient
from ancla.profile import store
from ancla.profile.model import N_EXPERIENCES, N_SKILLS, Profile, Proposal
from ancla.proposal import format
from ancla.selection import engine, prompt
from ancla.web.settings import load_settings
from evaluacion.checks import Check, check

RAIZ = Path(__file__).resolve().parent.parent
CASOS = Path(__file__).resolve().parent / "vacantes.json"
EXPORTACIONES = RAIZ / "exportaciones"

# Groq's free tier throttles per minute: a case could fail on its turn for
# no real reason. Same approach as in MedAI.
REINTENTOS = 3
ESPERA_REINTENTO_S = 12


CRITERIOS = {
    "elige_lo_mas_relevante": (
        "De todo el catálogo disponible, las experiencias elegidas son las que mejor "
        "cubren los requisitos de esta vacante. Si había una claramente más relevante "
        "sin elegir, no lo cumple."
    ),
    "orden_por_relevancia": (
        "Las experiencias y las skills están ordenadas de más a menos relevante para "
        "esta vacante, no en un orden arbitrario."
    ),
    "cubre_requisitos_distintos": (
        "Las experiencias elegidas cubren requisitos distintos entre sí en vez de "
        "repetir el mismo stack varias veces, si el catálogo lo permitía."
    ),
    "motivos_concretos": (
        "Cada motivo nombra un requisito concreto de la vacante. Fórmulas vacías como "
        "«encaja bien» o «es relevante para el puesto» NO lo cumplen."
    ),
    "sobre_mi_coherente": (
        "Los seis elementos del «Sobre mí» son coherentes con las skills elegidas y "
        "con lo que pide la vacante, y el grupo A (conceptos) y el B (tecnologías "
        "concretas) están bien repartidos."
    ),
    "huecos_reales": (
        "Los huecos señalados son de verdad requisitos de la vacante que el catálogo "
        "no cubre. Un hueco que el perfil sí cubre NO lo cumple."
    ),
    "huecos_completos": (
        "No falta ningún requisito importante de la vacante que el catálogo no cubra "
        "y que no aparezca en los huecos."
    ),
}

PROMPT_JUEZ = """\
Eres un evaluador de calidad de una herramienta que adapta el CV de una persona a una \
vacante. La herramienta NO redacta: elige, de un catálogo cerrado de experiencias y \
skills que la persona ya tiene documentadas, cuáles mostrar y en qué orden, y explica \
por qué cada una.

Te doy tres cosas: (1) el CATÁLOGO COMPLETO que la herramienta tenía disponible —esto \
es lo que hace posible juzgar de verdad, porque puedes ver qué se descartó, no solo qué \
se eligió—; (2) la VACANTE; (3) la PROPUESTA que produjo.

Juzga la propuesta contra el catálogo, no contra un CV ideal imaginario. Si la vacante \
pide algo que no está en el catálogo, la herramienta hace lo correcto al no ponerlo: \
inventarlo sería el peor fallo posible. Evalúa la CALIDAD DE LA ELECCIÓN entre lo que \
había disponible.

Puntúa CADA criterio con 0 (no lo cumple) o 1 (lo cumple), con una justificación de una \
frase que haga referencia al catálogo o a la vacante.

Responde ÚNICAMENTE con JSON válido, sin texto alrededor ni bloques de código:
{{"criterios": {{"<criterio>": {{"puntuacion": 0, "justificacion": "..."}}}}}}

=== CATÁLOGO DISPONIBLE ===
{catalogo}

=== VACANTE ===
{vacante}

=== PROPUESTA ===
{propuesta}

=== CRITERIOS A EVALUAR ===
{lista_criterios}
"""


# --------------------------------------------------------------------------


def _client() -> GroqClient:
    ajustes = load_settings()
    if not ajustes.configured():
        print(
            "No hay clave de API configurada. Ponla en Ajustes (o en ajustes.json) "
            "antes de evaluar.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return GroqClient(clave=ajustes.clave_api)


def _with_retry(hacer):
    """Retries only what can fail from the provider being saturated."""
    for intento in range(REINTENTOS):
        try:
            return hacer()
        except AIError as exc:
            if "cuota" not in str(exc).lower() or intento == REINTENTOS - 1:
                raise
            time.sleep(ESPERA_REINTENTO_S)
    raise AssertionError("inalcanzable")


def _cases() -> list[dict[str, Any]]:
    if not CASOS.exists():
        print(f"No existe {CASOS}. Añade tus vacantes reales ahí.", file=sys.stderr)
        raise SystemExit(1)
    return json.loads(CASOS.read_text(encoding="utf-8"))["casos"]


def _judge(cliente: GroqClient, perfil: Profile, caso: dict, propuesta: Proposal) -> dict:
    lista = "\n".join(f"- {nombre}: {texto}" for nombre, texto in CRITERIOS.items())
    peticion = PROMPT_JUEZ.format(
        catalogo=prompt.catalog(perfil, propuesta.language),
        vacante=caso["vacante"],
        propuesta=format.to_markdown(propuesta, perfil),
        lista_criterios=lista,
    )
    bruto = _with_retry(
        lambda: cliente.complete("Eres un evaluador estricto y conciso.", peticion)
    )
    inicio, fin = bruto.find("{"), bruto.rfind("}")
    if inicio == -1 or fin == -1:
        return {"error": "el juez no devolvió JSON"}
    try:
        return json.loads(bruto[inicio : fin + 1])
    except json.JSONDecodeError as exc:
        return {"error": f"JSON del juez ilegible: {exc}"}


# --------------------------------------------------------------------------
# Reports
# --------------------------------------------------------------------------


def _transcript_report(resultados: list[dict], momento: str) -> str:
    lineas = [
        f"# Evaluación — propuestas en crudo ({momento})",
        "",
        "Sin puntuaciones a propósito. Léelas y júzgalas con tu criterio **antes** de",
        "abrir el informe del juez-IA: su nota condiciona lo que ves.",
        "",
        "La pregunta para cada una: ¿pegarías esto en tu CV tal cual?",
        "",
    ]
    for resultado in resultados:
        lineas += ["---", "", f"## {resultado['nombre']}", ""]
        if resultado.get("error"):
            lineas += [f"**Falló:** {resultado['error']}", ""]
            continue
        lineas += [_checks_table(resultado["comprobaciones"]), "", resultado["markdown"], ""]
    return "\n".join(lineas)


def _checks_table(comprobaciones: list[Check]) -> str:
    fallos = [c for c in comprobaciones if not c.correcta]
    if not fallos:
        return f"*Comprobaciones automáticas: {len(comprobaciones)}/{len(comprobaciones)} correctas.*"
    lineas = ["**Comprobaciones automáticas FALLIDAS** (esto es un fallo, no una opinión):", ""]
    lineas += [f"- `{c.nombre}` — {c.detalle}" for c in fallos]
    return "\n".join(lineas)


def _judge_report(resultados: list[dict], momento: str) -> str:
    lineas = [
        f"# Evaluación — veredicto del juez-IA ({momento})",
        "",
        "Llamada independiente de la que generó cada propuesta. **Léelo después de la",
        "transcripción**: el juez premia lo largo y lo que suena seguro, así que tu",
        "criterio tiene que formarse antes.",
        "",
    ]
    totales: dict[str, list[int]] = {nombre: [] for nombre in CRITERIOS}
    for resultado in resultados:
        lineas += ["---", "", f"## {resultado['nombre']}", ""]
        veredicto = resultado.get("juez") or {}
        if veredicto.get("error") or resultado.get("error"):
            lineas += [f"**Sin veredicto:** {veredicto.get('error') or resultado['error']}", ""]
            continue
        for nombre in CRITERIOS:
            dato = (veredicto.get("criterios") or {}).get(nombre) or {}
            punto = dato.get("puntuacion")
            if punto in (0, 1):
                totales[nombre].append(punto)
            marca = {1: "✅", 0: "❌"}.get(punto, "—")
            lineas.append(f"- {marca} `{nombre}` — {dato.get('justificacion', 'sin justificar')}")
        lineas.append("")

    lineas += ["---", "", "## Resumen por criterio", ""]
    for nombre, puntos in totales.items():
        if puntos:
            lineas.append(f"- `{nombre}`: {sum(puntos)}/{len(puntos)}")
    return "\n".join(lineas)


# --------------------------------------------------------------------------


def main() -> None:
    opciones = argparse.ArgumentParser(description=__doc__)
    opciones.add_argument("--perfil", default="perfil", help="carpeta del perfil a usar")
    opciones.add_argument("--sin-juez", action="store_true", help="no llamar al juez-IA")
    args = opciones.parse_args()

    perfil = store.load_profile(RAIZ / args.perfil)
    if perfil.is_empty():
        print(f"El perfil «{args.perfil}» está vacío.", file=sys.stderr)
        raise SystemExit(1)

    cliente = _client()
    resultados: list[dict] = []

    for caso in _cases():
        nombre = caso.get("nombre") or caso["vacante"][:60]
        print(f"→ {nombre}")
        idioma = caso.get("idioma", "es")
        try:
            propuesta = _with_retry(
                lambda: motor.adapt(perfil, caso["vacante"], idioma, cliente)
            )
        except AIError as exc:
            resultados.append({"nombre": nombre, "error": str(exc)})
            continue

        resultado = {
            "nombre": nombre,
            "comprobaciones": check(propuesta, perfil, N_EXPERIENCES, N_SKILLS),
            "markdown": format.to_markdown(propuesta, perfil),
        }
        if not args.sin_juez:
            resultado["juez"] = _judge(cliente, perfil, caso, propuesta)
        resultados.append(resultado)

    momento = datetime.now().strftime("%Y-%m-%d %H:%M")
    sello = datetime.now().strftime("%Y%m%d_%H%M%S")
    EXPORTACIONES.mkdir(parents=True, exist_ok=True)

    ruta_t = EXPORTACIONES / f"eval_{sello}_propuestas.md"
    ruta_t.write_text(_transcript_report(resultados, momento), encoding="utf-8")
    print(f"\nTranscripción: {ruta_t}")

    if not args.sin_juez:
        ruta_j = EXPORTACIONES / f"eval_{sello}_juez_ia.md"
        ruta_j.write_text(_judge_report(resultados, momento), encoding="utf-8")
        print(f"Juez-IA:       {ruta_j}")
        print("\nLee la transcripción PRIMERO.")


if __name__ == "__main__":
    main()
