"""Modelo de datos del perfil y de las propuestas de CV.

Este módulo es el contrato del que dependen todos los demás: almacén, motor de
selección, archivo, formato y web. Se define primero y en serie, a propósito.

Todo el contenido del usuario es bilingüe (ES/EN) porque una misma base de
hechos sirve para candidaturas en los dos idiomas. La interfaz de la app es
solo española en la V1, pero los datos no lo son.

Regla de fondo del producto: aquí solo viven hechos que el usuario ha escrito o
validado. El sistema selecciona y ordena; nunca inventa contenido nuevo.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time
from enum import Enum
from typing import Generic, Literal, TypeVar

Idioma = Literal["es", "en"]
IDIOMAS: tuple[Idioma, ...] = ("es", "en")

# Cuántos elementos entran en cada sección del CV. Son los valores por defecto
# (los del CV de una página), no una ley: el usuario los puede cambiar en
# ajustes porque cada plantilla tiene un espacio distinto.
N_EXPERIENCIAS = 4
N_SKILLS = 9
N_GRUPO_SOBRE_MI = 3

T = TypeVar("T")


@dataclass(frozen=True)
class Bilingue(Generic[T]):
    """Un mismo dato en español e inglés (un texto, una lista de bullets...)."""

    es: T
    en: T

    def __getitem__(self, idioma: Idioma) -> T:
        if idioma not in IDIOMAS:
            raise ValueError(f"Idioma no soportado: {idioma!r}")
        return self.es if idioma == "es" else self.en


# --------------------------------------------------------------------------
# Perfil: la base de hechos verificados del usuario
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Experiencia:
    """Un proyecto o puesto de la base personal.

    `id` es el nombre del fichero YAML sin extensión y se usa como referencia
    estable desde las propuestas guardadas: si cambia, los CV del archivo dejan
    de resolver esa experiencia.
    """

    id: str
    titulo: Bilingue[str]
    periodo: Bilingue[str]
    bullets: Bilingue[list[str]]
    stack: Bilingue[str]
    keywords: list[str] = field(default_factory=list)
    estado: str = ""


@dataclass(frozen=True)
class Skill:
    """Una skill técnica de la base personal."""

    id: str
    nombre: Bilingue[str]
    categoria: str = ""
    keywords: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class IdiomaHablado:
    """Un idioma que el usuario habla, con su nivel.

    Distinto del tipo `Idioma` (el idioma *de salida* del CV, "es"/"en"): este
    representa un idioma como dato del perfil — inglés, francés... — por eso
    el nombre no coincide a propósito.
    """

    id: str
    nombre: Bilingue[str]
    nivel: Bilingue[str]
    keywords: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SobreMi:
    """Plantilla del bloque "Sobre mí".

    El texto es fijo y lo escribe el usuario; el sistema solo rellena los huecos
    `{GRUPO_A_1..3}` (conceptos/dominios) y `{GRUPO_B_1..3}` (lenguajes y
    tecnologías concretas). Es la única parte del CV donde el sistema compone
    texto, y aun así se limita a insertar nombres de skills existentes.
    """

    plantilla: Bilingue[str]

    def huecos(self) -> tuple[str, ...]:
        return tuple(
            f"{{GRUPO_{grupo}_{n}}}"
            for grupo in ("A", "B")
            for n in range(1, N_GRUPO_SOBRE_MI + 1)
        )

    def render(self, grupo_a: list[str], grupo_b: list[str], idioma: Idioma) -> str:
        """Sustituye los huecos por los elementos elegidos."""
        for nombre, grupo in (("GRUPO_A", grupo_a), ("GRUPO_B", grupo_b)):
            if len(grupo) != N_GRUPO_SOBRE_MI:
                raise ValueError(
                    f"{nombre} necesita {N_GRUPO_SOBRE_MI} elementos, recibió {len(grupo)}"
                )
        texto = self.plantilla[idioma]
        for n, valor in enumerate(grupo_a, start=1):
            texto = texto.replace(f"{{GRUPO_A_{n}}}", valor)
        for n, valor in enumerate(grupo_b, start=1):
            texto = texto.replace(f"{{GRUPO_B_{n}}}", valor)
        return texto


@dataclass(frozen=True)
class Perfil:
    """Toda la base de hechos del usuario, ya cargada en memoria.

    `skills_personales` e `idiomas` son catálogos aparte, deliberadamente
    fuera del alcance de `seleccion/motor.py`: no se envían al modelo, así que
    no pueden acabar ni en "Sobre mí" ni entre las skills técnicas — no es un
    filtro que se aplica después, es que la selección no tiene acceso a ellos.
    En la Propuesta se muestran siempre completos, sin seleccionar un
    subconjunto: a diferencia de la experiencia o las skills técnicas, en un
    CV real no se recortan según la vacante.
    """

    experiencias: list[Experiencia] = field(default_factory=list)
    skills: list[Skill] = field(default_factory=list)
    skills_personales: list[Skill] = field(default_factory=list)
    idiomas: list[IdiomaHablado] = field(default_factory=list)
    sobre_mi: SobreMi | None = None

    def experiencia(self, id: str) -> Experiencia | None:
        return next((e for e in self.experiencias if e.id == id), None)

    def skill(self, id: str) -> Skill | None:
        return next((s for s in self.skills if s.id == id), None)

    def skill_personal(self, id: str) -> Skill | None:
        return next((s for s in self.skills_personales if s.id == id), None)

    def idioma(self, id: str) -> IdiomaHablado | None:
        return next((i for i in self.idiomas if i.id == id), None)

    def esta_vacio(self) -> bool:
        return not self.experiencias and not self.skills


# --------------------------------------------------------------------------
# Propuesta: el resultado de adaptar el perfil a una vacante
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SeleccionSobreMi:
    grupo_a: list[str]
    grupo_b: list[str]
    texto: str
    motivo: str = ""


@dataclass(frozen=True)
class ExperienciaSeleccionada:
    """Referencia a una experiencia del perfil, más el porqué de la elección."""

    id: str
    motivo: str = ""


@dataclass(frozen=True)
class Propuesta:
    """Qué mostrar en el CV para una vacante concreta.

    Solo guarda *referencias* (ids) al perfil, nunca copias del contenido: así
    una corrección en la base se refleja en todo el archivo. El texto del
    "Sobre mí" sí se guarda ya compuesto, porque es lo que el usuario pegó.

    `huecos` son los requisitos de la vacante que no existen en el perfil. Van
    aparte de la propuesta a propósito: son información para el usuario, no
    material para el CV, y es justo lo que no se debe inventar.
    """

    idioma: Idioma
    sobre_mi: SeleccionSobreMi
    skills: list[str]
    experiencias: list[ExperienciaSeleccionada]
    motivo_skills: str = ""
    huecos: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------
# Archivo: las propuestas guardadas a lo largo del tiempo
# --------------------------------------------------------------------------


class EstadoCV(str, Enum):
    """Dónde está esa candidatura. Alimentará el apartado de mejoras (v2)."""

    BORRADOR = "borrador"
    ENVIADO = "enviado"
    ENTREVISTA = "entrevista"
    DESCARTADO = "descartado"
    ACEPTADO = "aceptado"


@dataclass(frozen=True)
class CVGuardado:
    """Una adaptación archivada, para consultarla, duplicarla o reciclarla.

    `adjunto` es la ruta al CV final que el usuario montó por su cuenta, en el
    formato que sea (PDF, docx, imagen): la app lo copia y lo referencia, no lo
    valida ni lo convierte.

    `hora` es opcional (`None` si no se conoce) para que un CV guardado antes
    de que existiera este campo se siga leyendo sin problema: no tener la hora
    no es un fichero roto, solo un dato que no se capturó entonces.
    """

    id: str
    fecha: date
    empresa: str
    puesto: str
    vacante: str
    propuesta: Propuesta
    estado: EstadoCV = EstadoCV.BORRADOR
    adjunto: str | None = None
    notas: str = ""
    hora: time | None = None
