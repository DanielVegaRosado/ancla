"""Banco de pruebas del motor de selección (comprobaciones + transcripción + juez-IA).

Portado del patrón de MedAI (`evaluacion/evaluar_bots.py`): ejecuta casos reales
contra **la misma lógica que usa la app**, sin pasar por la web, y produce dos
ficheros separados a propósito.

Existe para responder a una pregunta que ninguna suite de tests responde: *¿la
propuesta es buena?* Los tests unitarios comprueban que el motor cumple su
contrato; esto comprueba si la selección sirve. Sin esto, retocar el prompt es
afinar a ciegas.

Tres capas, de más barata a más cara:

1. **Comprobaciones deterministas** (`comprobaciones.py`, 0 tokens) — lo que una
   máquina verifica sola. Si una falla es un fallo, no una opinión.
2. **Transcripción** — las propuestas en crudo, sin nota, para que las juzgue
   una persona con su propio criterio.
3. **Juez-IA** — llamada aparte, independiente de la que generó la propuesta,
   puntuando una rúbrica.

El orden de los dos ficheros importa: **el juez-IA tiene sesgos** (premia lo
largo y lo que suena seguro), así que tu criterio debe formarse leyendo la
transcripción antes de ver ninguna nota. Aquí más aún que en MedAI: quien mejor
sabe si un CV le representa es su dueño.

Uso (desde `app/`):

    python -m evaluacion.evaluar                 # todo
    python -m evaluacion.evaluar --sin-juez      # sin gastar llamadas de juez
    python -m evaluacion.evaluar --perfil perfil-ejemplo
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from cv_adaptativo.ia.cliente import ErrorIA
from cv_adaptativo.ia.groq import ClienteGroq
from cv_adaptativo.perfil import almacen
from cv_adaptativo.perfil.modelo import N_EXPERIENCIAS, N_SKILLS, Perfil, Propuesta
from cv_adaptativo.propuesta import formato
from cv_adaptativo.seleccion import motor, prompt
from cv_adaptativo.web.ajustes import cargar_ajustes
from evaluacion.comprobaciones import Comprobacion, comprobar

RAIZ = Path(__file__).resolve().parent.parent
CASOS = Path(__file__).resolve().parent / "vacantes.json"
EXPORTACIONES = RAIZ / "exportaciones"

# Groq gratuito limita por minuto: un caso podría fallar por turno y no por un
# problema real. Mismo criterio que en MedAI.
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


def _cliente() -> ClienteGroq:
    ajustes = cargar_ajustes()
    if not ajustes.configurado():
        print(
            "No hay clave de API configurada. Ponla en Ajustes (o en ajustes.json) "
            "antes de evaluar.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return ClienteGroq(clave=ajustes.clave_api)


def _con_reintento(hacer):
    """Reintenta solo lo que puede fallar por saturación del proveedor."""
    for intento in range(REINTENTOS):
        try:
            return hacer()
        except ErrorIA as exc:
            if "cuota" not in str(exc).lower() or intento == REINTENTOS - 1:
                raise
            time.sleep(ESPERA_REINTENTO_S)
    raise AssertionError("inalcanzable")


def _casos() -> list[dict[str, Any]]:
    if not CASOS.exists():
        print(f"No existe {CASOS}. Añade tus vacantes reales ahí.", file=sys.stderr)
        raise SystemExit(1)
    return json.loads(CASOS.read_text(encoding="utf-8"))["casos"]


def _juzgar(cliente: ClienteGroq, perfil: Perfil, caso: dict, propuesta: Propuesta) -> dict:
    lista = "\n".join(f"- {nombre}: {texto}" for nombre, texto in CRITERIOS.items())
    peticion = PROMPT_JUEZ.format(
        catalogo=prompt.catalogo(perfil, propuesta.idioma),
        vacante=caso["vacante"],
        propuesta=formato.a_markdown(propuesta, perfil),
        lista_criterios=lista,
    )
    bruto = _con_reintento(
        lambda: cliente.completar("Eres un evaluador estricto y conciso.", peticion)
    )
    inicio, fin = bruto.find("{"), bruto.rfind("}")
    if inicio == -1 or fin == -1:
        return {"error": "el juez no devolvió JSON"}
    try:
        return json.loads(bruto[inicio : fin + 1])
    except json.JSONDecodeError as exc:
        return {"error": f"JSON del juez ilegible: {exc}"}


# --------------------------------------------------------------------------
# Informes
# --------------------------------------------------------------------------


def _informe_transcripcion(resultados: list[dict], momento: str) -> str:
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
        lineas += [_tabla_comprobaciones(resultado["comprobaciones"]), "", resultado["markdown"], ""]
    return "\n".join(lineas)


def _tabla_comprobaciones(comprobaciones: list[Comprobacion]) -> str:
    fallos = [c for c in comprobaciones if not c.correcta]
    if not fallos:
        return f"*Comprobaciones automáticas: {len(comprobaciones)}/{len(comprobaciones)} correctas.*"
    lineas = ["**Comprobaciones automáticas FALLIDAS** (esto es un fallo, no una opinión):", ""]
    lineas += [f"- `{c.nombre}` — {c.detalle}" for c in fallos]
    return "\n".join(lineas)


def _informe_juez(resultados: list[dict], momento: str) -> str:
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

    perfil = almacen.cargar_perfil(RAIZ / args.perfil)
    if perfil.esta_vacio():
        print(f"El perfil «{args.perfil}» está vacío.", file=sys.stderr)
        raise SystemExit(1)

    cliente = _cliente()
    resultados: list[dict] = []

    for caso in _casos():
        nombre = caso.get("nombre") or caso["vacante"][:60]
        print(f"→ {nombre}")
        idioma = caso.get("idioma", "es")
        try:
            propuesta = _con_reintento(
                lambda: motor.adaptar(perfil, caso["vacante"], idioma, cliente)
            )
        except ErrorIA as exc:
            resultados.append({"nombre": nombre, "error": str(exc)})
            continue

        resultado = {
            "nombre": nombre,
            "comprobaciones": comprobar(propuesta, perfil, N_EXPERIENCIAS, N_SKILLS),
            "markdown": formato.a_markdown(propuesta, perfil),
        }
        if not args.sin_juez:
            resultado["juez"] = _juzgar(cliente, perfil, caso, propuesta)
        resultados.append(resultado)

    momento = datetime.now().strftime("%Y-%m-%d %H:%M")
    sello = datetime.now().strftime("%Y%m%d_%H%M%S")
    EXPORTACIONES.mkdir(parents=True, exist_ok=True)

    ruta_t = EXPORTACIONES / f"eval_{sello}_propuestas.md"
    ruta_t.write_text(_informe_transcripcion(resultados, momento), encoding="utf-8")
    print(f"\nTranscripción: {ruta_t}")

    if not args.sin_juez:
        ruta_j = EXPORTACIONES / f"eval_{sello}_juez_ia.md"
        ruta_j.write_text(_informe_juez(resultados, momento), encoding="utf-8")
        print(f"Juez-IA:       {ruta_j}")
        print("\nLee la transcripción PRIMERO.")


if __name__ == "__main__":
    main()
