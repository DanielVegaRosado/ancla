"""Validación del perfil.

Los ficheros los mantenía a mano una sola persona que sabía el formato. En
cuanto el perfil lo escribe cualquiera desde la app —o edita el YAML a mano—
hay que decirle qué está mal en su idioma, no reventar con un stack trace.

Dos criterios que explican por qué la lista dice lo que dice:

- **Un problema es algo que empeora el CV**, no solo lo que impide generarlo.
  Una skill sin palabras clave no rompe nada: simplemente no se elegirá casi
  nunca, y el usuario no tiene forma de adivinarlo mirando la pantalla.
- **Cada mensaje dice qué falta y dónde**, empezando por el elemento («Skill
  «python»: …»), porque `validar_perfil` devuelve los de todo el perfil
  juntos y hay que poder ir al fichero correcto.

Lo que no se valida a propósito: que las dos versiones de los bullets tengan
el mismo número de líneas. El CV en inglés y el español no tienen por qué
decir lo mismo, y es el usuario quien escribe los dos.

CONTRATO — implementa el agente A.
"""
from __future__ import annotations

import re

from cv_adaptativo.perfil.modelo import (
    IDIOMAS,
    Experiencia,
    Idioma,
    IdiomaHablado,
    Perfil,
    Skill,
    SobreMi,
)

_NOMBRE_IDIOMA: dict[Idioma, str] = {"es": "español", "en": "inglés"}

# Cualquier {COSA} escrita en la plantilla del "Sobre mí".
_HUECO = re.compile(r"\{[^{}]*\}")


def validar_experiencia(experiencia: Experiencia) -> list[str]:
    """Problemas encontrados, en español y dirigidos al usuario. Vacío = correcta."""
    etiqueta = f"Experiencia «{experiencia.id}»" if experiencia.id else "Una experiencia"
    problemas: list[str] = []

    if not experiencia.id.strip():
        problemas.append(
            "Hay una experiencia sin identificador. El identificador es el nombre "
            "del fichero, por ejemplo «data-analyst-movilidad.yaml»."
        )

    for idioma in IDIOMAS:
        nombre = _NOMBRE_IDIOMA[idioma]
        if not experiencia.titulo[idioma].strip():
            problemas.append(f"{etiqueta}: falta el título en {nombre}.")
        if not experiencia.periodo[idioma].strip():
            problemas.append(
                f"{etiqueta}: falta el periodo en {nombre} (por ejemplo «2025 - ACTUALIDAD»)."
            )
        if not experiencia.stack[idioma].strip():
            problemas.append(
                f"{etiqueta}: falta el stack en {nombre} (las tecnologías que usaste)."
            )
        problemas += _problemas_bullets(experiencia.bullets[idioma], etiqueta, nombre)

    if not experiencia.keywords:
        problemas.append(
            f"{etiqueta}: no tiene palabras clave, así que casi nunca se elegirá "
            "para un CV. Añade los términos con los que la buscaría una empresa."
        )
    return problemas


def _problemas_bullets(bullets: list[str], etiqueta: str, nombre: str) -> list[str]:
    if not bullets:
        problemas = [f"{etiqueta}: no tiene ningún punto en {nombre}."]
    elif any(not bullet.strip() for bullet in bullets):
        problemas = [
            f"{etiqueta}: hay algún punto vacío en {nombre}; escríbelo o quítalo."
        ]
    else:
        problemas = []
    return problemas


def validar_skill(skill: Skill) -> list[str]:
    etiqueta = f"Skill «{skill.id}»" if skill.id else "Una skill"
    problemas: list[str] = []

    if not skill.id.strip():
        problemas.append(
            "Hay una skill sin identificador. El identificador es el nombre del "
            "fichero, por ejemplo «python.yaml»."
        )
    for idioma in IDIOMAS:
        if not skill.nombre[idioma].strip():
            problemas.append(f"{etiqueta}: falta el nombre en {_NOMBRE_IDIOMA[idioma]}.")
    if not skill.categoria.strip():
        problemas.append(
            f"{etiqueta}: no tiene categoría. Se usa para agrupar las skills del "
            "CV y para repartirlas en el «Sobre mí»."
        )
    if not skill.keywords:
        problemas.append(
            f"{etiqueta}: no tiene palabras clave, así que casi nunca se elegirá "
            "para un CV. Añade cómo la nombran las ofertas."
        )
    return problemas


def validar_skill_personal(skill: Skill) -> list[str]:
    """Como `validar_skill`, pero sin exigir categoría: no hay agrupación por
    categoría para skills personales, así que pedirla sería un campo sin uso."""
    etiqueta = f"Skill personal «{skill.id}»" if skill.id else "Una skill personal"
    problemas: list[str] = []

    if not skill.id.strip():
        problemas.append(
            "Hay una skill personal sin identificador. El identificador es el "
            "nombre del fichero, por ejemplo «trabajo-en-equipo.yaml»."
        )
    for idioma in IDIOMAS:
        if not skill.nombre[idioma].strip():
            problemas.append(f"{etiqueta}: falta el nombre en {_NOMBRE_IDIOMA[idioma]}.")
    if not skill.keywords:
        problemas.append(
            f"{etiqueta}: no tiene palabras clave, así que puede que una vacante "
            "la siga marcando como hueco aunque ya la tengas. Añade cómo se "
            "nombra en las ofertas."
        )
    return problemas


def validar_idioma(idioma: IdiomaHablado) -> list[str]:
    """Igual de estricto que `validar_skill`: sin nivel, un idioma no dice nada
    en un CV, y sin keywords casi nunca anulará un hueco falso de la vacante."""
    etiqueta = f"Idioma «{idioma.id}»" if idioma.id else "Un idioma"
    problemas: list[str] = []

    if not idioma.id.strip():
        problemas.append(
            "Hay un idioma sin identificador. El identificador es el nombre del "
            "fichero, por ejemplo «ingles.yaml»."
        )
    for cod in IDIOMAS:
        nombre_cod = _NOMBRE_IDIOMA[cod]
        if not idioma.nombre[cod].strip():
            problemas.append(f"{etiqueta}: falta el nombre en {nombre_cod}.")
        if not idioma.nivel[cod].strip():
            problemas.append(
                f"{etiqueta}: falta el nivel en {nombre_cod} (por ejemplo «C1 — "
                "Avanzado»)."
            )
    if not idioma.keywords:
        problemas.append(
            f"{etiqueta}: no tiene palabras clave, así que puede que una vacante "
            "lo siga marcando como hueco aunque ya lo tengas. Añade cómo se "
            "nombra en las ofertas (p. ej. «advanced english», «fluido»)."
        )
    return problemas


def validar_sobre_mi(sobre_mi: SobreMi) -> list[str]:
    """Comprueba que la plantilla tenga los 6 huecos, en ES y en EN."""
    problemas: list[str] = []
    huecos = set(sobre_mi.huecos())

    for idioma in IDIOMAS:
        nombre = _NOMBRE_IDIOMA[idioma]
        texto = sobre_mi.plantilla[idioma]
        if not texto.strip():
            problemas.append(f"El «Sobre mí» está vacío en {nombre}.")
            continue

        faltan = [hueco for hueco in sobre_mi.huecos() if hueco not in texto]
        if faltan:
            problemas.append(
                f"Al «Sobre mí» en {nombre} le faltan estos huecos: "
                f"{', '.join(faltan)}. Escríbelos tal cual donde quieras que "
                "entren las skills elegidas."
            )
        # Un {GRUPO_A_4} o un {GRUPO_C_1} se quedarían escritos tal cual en el
        # CV final, y eso el usuario solo lo vería al leer el resultado.
        desconocidos = sorted(set(_HUECO.findall(texto)) - huecos)
        if desconocidos:
            problemas.append(
                f"El «Sobre mí» en {nombre} tiene huecos que el sistema no sabe "
                f"rellenar: {', '.join(desconocidos)}. Los válidos son: "
                f"{', '.join(sobre_mi.huecos())}."
            )
    return problemas


def validar_perfil(perfil: Perfil) -> list[str]:
    """Valida el conjunto: ids duplicados, perfil vacío, falta de "Sobre mí"."""
    problemas: list[str] = []

    if perfil.esta_vacio():
        problemas.append(
            "El perfil está vacío. Añade al menos una experiencia y una skill "
            "antes de generar un CV: la app solo puede elegir entre lo que tú "
            "hayas escrito."
        )
    else:
        if not perfil.experiencias:
            problemas.append(
                "No hay ninguna experiencia, así que el CV saldría sin proyectos."
            )
        if not perfil.skills:
            problemas.append(
                "No hay ninguna skill, así que el CV saldría sin la sección "
                "técnica y el «Sobre mí» no se podría componer."
            )

    problemas += _duplicados(
        [experiencia.id for experiencia in perfil.experiencias], "experiencias"
    )
    problemas += _duplicados([skill.id for skill in perfil.skills], "skills")
    problemas += _duplicados(
        [skill.id for skill in perfil.skills_personales], "skills personales"
    )
    problemas += _duplicados([idioma.id for idioma in perfil.idiomas], "idiomas")

    if perfil.sobre_mi is None:
        problemas.append(
            "Falta el «Sobre mí». Escríbelo en «Mi perfil»: es el bloque que abre "
            "el CV y el único que la app compone."
        )
    else:
        problemas += validar_sobre_mi(perfil.sobre_mi)

    for experiencia in perfil.experiencias:
        problemas += validar_experiencia(experiencia)
    for skill in perfil.skills:
        problemas += validar_skill(skill)
    # Skills personales e idiomas son opcionales (a diferencia de las técnicas
    # y la experiencia): no pasar ninguna no es un problema del perfil, solo
    # significa que esos dos bloques saldrán vacíos en la Propuesta.
    for skill in perfil.skills_personales:
        problemas += validar_skill_personal(skill)
    for idioma in perfil.idiomas:
        problemas += validar_idioma(idioma)
    return problemas


def _duplicados(ids: list[str], que: str) -> list[str]:
    """Normalmente el id es el nombre del fichero y no se puede repetir, pero sí
    si conviven `python.yaml` y `python.yml`."""
    vistos: set[str] = set()
    repetidos: list[str] = []
    for id_ in ids:
        if id_ in vistos and id_ not in repetidos:
            repetidos.append(id_)
        vistos.add(id_)
    if not repetidos:
        return []
    return [
        f"Hay {que} con el mismo identificador ({', '.join(repetidos)}). Cada una "
        "tiene que tener el suyo: es como el CV guardado sabe a cuál se refiere."
    ]
