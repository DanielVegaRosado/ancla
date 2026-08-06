"""Comprobaciones deterministas sobre una propuesta. Cero tokens.

Todo lo que una máquina puede verificar sola no se le pregunta a un juez-IA:
sale más barato, no falla por azar y su veredicto no se discute. El juez queda
solo para lo que de verdad requiere criterio (¿era esta la mejor elección
posible?, ¿este motivo dice algo?).

Si alguna de estas falla, es un fallo del motor, no una opinión.
"""
from __future__ import annotations

from dataclasses import dataclass

from ancla.perfil.modelo import Perfil, Propuesta
from ancla.texto import normalizar


@dataclass(frozen=True)
class Comprobacion:
    nombre: str
    correcta: bool
    detalle: str = ""


def comprobar(propuesta: Propuesta, perfil: Perfil, n_exp: int, n_skills: int) -> list[Comprobacion]:
    return [
        _todo_del_catalogo(propuesta, perfil),
        _sin_repetidos(propuesta),
        _cantidades(propuesta, perfil, n_exp, n_skills),
        _todo_lleva_motivo(propuesta),
        _sobre_mi_sin_huecos(propuesta),
        _grupos_sin_solaparse(propuesta),
        _huecos_no_estan_en_el_perfil(propuesta, perfil),
    ]


def _todo_del_catalogo(propuesta: Propuesta, perfil: Perfil) -> Comprobacion:
    """La regla número uno del producto. El motor ya filtra, pero esto lo
    verifica de punta a punta con datos reales, que es distinto."""
    inventados = [
        exp.id for exp in propuesta.experiencias if perfil.experiencia(exp.id) is None
    ] + [id_ for id_ in propuesta.skills if perfil.skill(id_) is None]
    return Comprobacion(
        "todo_del_catalogo",
        not inventados,
        "" if not inventados else f"fuera del perfil: {', '.join(inventados)}",
    )


def _sin_repetidos(propuesta: Propuesta) -> Comprobacion:
    ids = [exp.id for exp in propuesta.experiencias] + propuesta.skills
    repetidos = {id_ for id_ in ids if ids.count(id_) > 1}
    return Comprobacion(
        "sin_repetidos", not repetidos, ", ".join(sorted(repetidos))
    )


def _cantidades(
    propuesta: Propuesta, perfil: Perfil, n_exp: int, n_skills: int
) -> Comprobacion:
    """Se esperan tantos como se pidieron, o todos los que haya si hay menos."""
    esperadas = min(n_exp, len(perfil.experiencias))
    esperadas_skills = min(n_skills, len(perfil.skills))
    fallos = []
    if len(propuesta.experiencias) != esperadas:
        fallos.append(f"{len(propuesta.experiencias)} experiencias (esperadas {esperadas})")
    if len(propuesta.skills) != esperadas_skills:
        fallos.append(f"{len(propuesta.skills)} skills (esperadas {esperadas_skills})")
    return Comprobacion("cantidades", not fallos, "; ".join(fallos))


def _todo_lleva_motivo(propuesta: Propuesta) -> Comprobacion:
    """Regla 3: sin motivo, el usuario no puede juzgar la propuesta."""
    sin_motivo = [exp.id for exp in propuesta.experiencias if not exp.motivo.strip()]
    if not propuesta.motivo_skills.strip():
        sin_motivo.append("(conjunto de skills)")
    if not propuesta.sobre_mi.motivo.strip():
        sin_motivo.append("(sobre mí)")
    return Comprobacion("todo_lleva_motivo", not sin_motivo, ", ".join(sin_motivo))


def _sobre_mi_sin_huecos(propuesta: Propuesta) -> Comprobacion:
    """Un `{GRUPO_A_1}` sin rellenar se copiaría tal cual al CV."""
    hay_hueco = "{GRUPO_" in propuesta.sobre_mi.texto
    return Comprobacion(
        "sobre_mi_sin_huecos",
        not hay_hueco,
        "quedan huecos sin rellenar en el texto" if hay_hueco else "",
    )


def _grupos_sin_solaparse(propuesta: Propuesta) -> Comprobacion:
    a = {normalizar(x) for x in propuesta.sobre_mi.grupo_a}
    b = {normalizar(x) for x in propuesta.sobre_mi.grupo_b}
    comunes = a & b
    return Comprobacion("grupos_sin_solaparse", not comunes, ", ".join(sorted(comunes)))


def _huecos_no_estan_en_el_perfil(propuesta: Propuesta, perfil: Perfil) -> Comprobacion:
    """Un hueco que sí está en el perfil es un falso positivo: le diría al
    usuario que le falta algo que tiene documentado."""
    nombres = {
        normalizar(skill.nombre[propuesta.idioma]) for skill in perfil.skills
    } | {normalizar(palabra) for skill in perfil.skills for palabra in skill.keywords}
    falsos = [hueco for hueco in propuesta.huecos if normalizar(hueco) in nombres]
    return Comprobacion(
        "huecos_no_estan_en_el_perfil", not falsos, ", ".join(falsos)
    )
