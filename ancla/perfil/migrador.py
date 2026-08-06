"""Conversión del formato de texto antiguo al perfil en YAML.

Antes de que existiera la app, la base de hechos se mantenía a mano en ficheros
`.txt` con campos en mayúsculas:

    relevant_experience/<id>.txt   ID, TITULO_ES/EN, PERIODO_ES/EN, ESTADO,
                                   BULLETS_ES/EN, STACK_ES/EN, KEYWORDS
    technical-skills/<id>.txt      NOMBRE_ES/EN, CATEGORIA, KEYWORDS
    about-me-template.txt          los bloques ES: y EN: de la plantilla

Aquello funcionaba porque lo cuidaba una sola persona que conocía el formato.
Se migra a YAML por eso mismo: en cuanto lo escribe cualquiera desde la app, un
parser propio se convierte en una fuente constante de fallos.

Dos garantías, en este orden de importancia:

1. **La carpeta de origen no se toca.** Ni se modifica, ni se mueve, ni se
   borra nada de ella. Son los datos reales de una persona y siguen siendo su
   copia buena hasta que decida lo contrario. Este módulo solo la lee.
2. **Nunca pisa un fichero ya migrado** salvo que se pida `sobrescribir=True`.
   Lo que se salta lo cuenta en el informe, no lo hace en silencio.

Uso:

    python -m ancla.perfil.migrador <carpeta-origen> <carpeta-perfil>
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from ancla.perfil import almacen, validacion
from ancla.perfil.modelo import Bilingue, Experiencia, Skill, SobreMi

CARPETA_EXPERIENCIA_ORIGEN = "relevant_experience"
CARPETA_SKILLS_ORIGEN = "technical-skills"
FICHERO_SOBRE_MI_ORIGEN = "about-me-template.txt"

# Una línea "CLAVE: valor". Los bullets empiezan por "- ", así que no coinciden,
# y una frase normal tampoco: la clave va toda en mayúsculas y pegada a los dos
# puntos.
_CAMPO = re.compile(r"^([A-Z][A-Z0-9_]*):[ \t]?(.*)$")


@dataclass
class InformeMigracion:
    """Qué se migró y qué conviene mirar a mano después."""

    experiencias: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    sobre_mi: bool = False
    omitidos: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    def resumen(self) -> str:
        lineas = [
            f"Experiencias migradas: {len(self.experiencias)}",
            f"Skills migradas: {len(self.skills)}",
            f"«Sobre mí»: {'sí' if self.sobre_mi else 'no encontrado'}",
        ]
        if self.omitidos:
            lineas.append("")
            lineas.append("Omitidos (ya existían, no se han tocado):")
            lineas += [f"  - {texto}" for texto in self.omitidos]
        if self.avisos:
            lineas.append("")
            lineas.append("Avisos:")
            lineas += [f"  - {texto}" for texto in self.avisos]
        return "\n".join(lineas)


def migrar(origen: Path, destino: Path, sobrescribir: bool = False) -> InformeMigracion:
    """Convierte la carpeta de `.txt` de `origen` en un perfil YAML en `destino`.

    `origen` se abre solo para leer. Devuelve el informe; no imprime nada.
    """
    origen, destino = Path(origen), Path(destino)
    informe = InformeMigracion()
    if not origen.is_dir():
        informe.avisos.append(f"La carpeta de origen «{origen}» no existe.")
        return informe

    _migrar_experiencias(origen, destino, sobrescribir, informe)
    _migrar_skills(origen, destino, sobrescribir, informe)
    _migrar_sobre_mi(origen, destino, sobrescribir, informe)
    return informe


# --------------------------------------------------------------------------
# Experiencias
# --------------------------------------------------------------------------


def _migrar_experiencias(
    origen: Path, destino: Path, sobrescribir: bool, informe: InformeMigracion
) -> None:
    for fichero in _ficheros_txt(origen / CARPETA_EXPERIENCIA_ORIGEN):
        campos = _leer_campos(fichero)
        id_ = campos.get("ID", "").strip() or fichero.stem
        if id_ != fichero.stem:
            informe.avisos.append(
                f"«{fichero.name}» declara el id «{id_}», distinto del nombre del "
                f"fichero. Se ha guardado como «{id_}.yaml»."
            )

        experiencia = Experiencia(
            id=id_,
            titulo=_bilingue(campos, "TITULO"),
            periodo=_bilingue(campos, "PERIODO"),
            bullets=Bilingue(
                es=_lista(campos, "BULLETS_ES"), en=_lista(campos, "BULLETS_EN")
            ),
            stack=_bilingue(campos, "STACK"),
            keywords=_palabras(campos.get("KEYWORDS", "")),
            estado=campos.get("ESTADO", "").strip(),
        )
        try:
            ruta = almacen.ruta_experiencia(destino, experiencia.id)
        except almacen.ErrorPerfil as exc:
            # Un id que no sirve tumba ese elemento, no la migración entera: los
            # otros doce ficheros no tienen la culpa.
            informe.avisos.append(f"{fichero.name} → {exc}")
            continue
        if not _libre(ruta, sobrescribir, informe, fichero):
            continue

        almacen.guardar_experiencia(destino, experiencia)
        _conservar_nota(ruta, campos, fichero, informe)
        informe.experiencias.append(experiencia.id)
        informe.avisos += _problemas(validacion.validar_experiencia(experiencia), fichero)


# --------------------------------------------------------------------------
# Skills
# --------------------------------------------------------------------------


def _migrar_skills(
    origen: Path, destino: Path, sobrescribir: bool, informe: InformeMigracion
) -> None:
    for fichero in _ficheros_txt(origen / CARPETA_SKILLS_ORIGEN):
        campos = _leer_campos(fichero)
        skill = Skill(
            id=fichero.stem,
            nombre=_bilingue(campos, "NOMBRE"),
            categoria=campos.get("CATEGORIA", "").strip(),
            keywords=_palabras(campos.get("KEYWORDS", "")),
        )
        try:
            ruta = almacen.ruta_skill(destino, skill.id)
        except almacen.ErrorPerfil as exc:
            informe.avisos.append(f"{fichero.name} → {exc}")
            continue
        if not _libre(ruta, sobrescribir, informe, fichero):
            continue

        almacen.guardar_skill(destino, skill)
        _conservar_nota(ruta, campos, fichero, informe)
        informe.skills.append(skill.id)
        informe.avisos += _problemas(validacion.validar_skill(skill), fichero)


# --------------------------------------------------------------------------
# Sobre mí
# --------------------------------------------------------------------------


def _migrar_sobre_mi(
    origen: Path, destino: Path, sobrescribir: bool, informe: InformeMigracion
) -> None:
    fichero = origen / FICHERO_SOBRE_MI_ORIGEN
    if not fichero.is_file():
        informe.avisos.append(
            f"No se encontró «{FICHERO_SOBRE_MI_ORIGEN}»: el perfil se queda sin "
            "«Sobre mí» y habrá que escribirlo en la app."
        )
        return

    # El fichero empieza con un párrafo de instrucciones que no es un campo;
    # se ignora solo, porque ninguna de sus líneas parece "CLAVE: valor".
    campos = _leer_campos(fichero)
    sobre_mi = SobreMi(
        plantilla=Bilingue(es=campos.get("ES", ""), en=campos.get("EN", ""))
    )
    ruta = almacen.ruta_sobre_mi(destino)
    if not _libre(ruta, sobrescribir, informe, fichero):
        return

    almacen.guardar_sobre_mi(destino, sobre_mi)
    _conservar_nota(ruta, campos, fichero, informe)
    informe.sobre_mi = True
    informe.avisos += _problemas(validacion.validar_sobre_mi(sobre_mi), fichero)


# --------------------------------------------------------------------------
# Piezas comunes
# --------------------------------------------------------------------------


def _ficheros_txt(carpeta: Path) -> list[Path]:
    if not carpeta.is_dir():
        return []
    return sorted(
        (ruta for ruta in carpeta.iterdir() if ruta.is_file() and ruta.suffix == ".txt"),
        key=lambda ruta: ruta.name,
    )


def _leer_campos(fichero: Path) -> dict[str, str]:
    """Lee el formato antiguo a un diccionario de campo → texto.

    Un campo puede venir de tres formas, y las tres aparecen en los ficheros
    reales: en la misma línea (`ESTADO: actualidad`), como lista de líneas que
    empiezan por `- ` (los bullets), o como párrafo debajo de la clave (los
    bloques `ES:` y `EN:`). Una línea en blanco cierra el campo abierto.
    """
    campos: dict[str, str] = {}
    actual: str | None = None
    for linea in fichero.read_text(encoding="utf-8").splitlines():
        if not linea.strip():
            actual = None
            continue
        coincidencia = _CAMPO.match(linea)
        if coincidencia:
            actual = coincidencia.group(1)
            campos[actual] = coincidencia.group(2).strip()
            continue
        if actual is None:
            continue  # Texto suelto antes del primer campo: no es un dato.
        # Continuación: una nota que ocupa varias líneas, un bullet, o el
        # párrafo que va justo debajo de su clave.
        campos[actual] = f"{campos[actual]}\n{linea.strip()}".strip()
    return campos


def _bilingue(campos: dict[str, str], prefijo: str) -> Bilingue[str]:
    return Bilingue(
        es=campos.get(f"{prefijo}_ES", "").strip(),
        en=campos.get(f"{prefijo}_EN", "").strip(),
    )


def _lista(campos: dict[str, str], campo: str) -> list[str]:
    """Las líneas `- ...` de un bloque de bullets, tal cual las escribió el
    usuario. No se reescribe ni se recorta nada: esa es la regla del producto."""
    elementos: list[str] = []
    for cruda in campos.get(campo, "").splitlines():
        linea = cruda.strip()
        if not linea:
            continue
        if linea.startswith("- "):
            elementos.append(linea[2:].strip())
        elif elementos:
            # Un bullet largo partido en dos líneas sigue siendo un bullet.
            elementos[-1] = f"{elementos[-1]} {linea}"
        else:
            elementos.append(linea)
    return elementos


def _palabras(bruto: str) -> list[str]:
    return [palabra.strip() for palabra in bruto.split(",") if palabra.strip()]


def _libre(
    ruta: Path, sobrescribir: bool, informe: InformeMigracion, fichero: Path
) -> bool:
    if ruta.exists() and not sobrescribir:
        informe.omitidos.append(f"{ruta.name} (venía de {fichero.name})")
        return False
    return True


def _conservar_nota(
    ruta: Path, campos: dict[str, str], fichero: Path, informe: InformeMigracion
) -> None:
    """El formato antiguo permitía un campo `NOTA:` libre y el modelo de datos no
    tiene dónde meterlo. Se guarda como comentario del YAML para no perderlo, y
    se avisa: es una decisión pendiente del usuario, no un dato del CV."""
    nota = campos.get("NOTA", "").strip()
    if not nota:
        return
    almacen.anotar(ruta, f"NOTA heredada de {fichero.name}:\n{nota}")
    informe.avisos.append(
        f"«{fichero.name}» tenía una NOTA que el modelo no representa. Se ha "
        f"copiado como comentario al principio de «{ruta.name}», pero se perderá "
        "la próxima vez que guardes ese elemento desde la app."
    )


def _problemas(problemas: list[str], fichero: Path) -> list[str]:
    return [f"{fichero.name} → {problema}" for problema in problemas]


# --------------------------------------------------------------------------
# Línea de órdenes
# --------------------------------------------------------------------------


def main(argumentos: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convierte el perfil en .txt del formato antiguo a YAML. "
        "La carpeta de origen no se modifica nunca."
    )
    parser.add_argument("origen", type=Path, help="carpeta con los .txt originales")
    parser.add_argument("destino", type=Path, help="carpeta del perfil (se crea)")
    parser.add_argument(
        "--sobrescribir",
        action="store_true",
        help="pisa los ficheros del perfil que ya existan (por defecto se saltan)",
    )
    opciones = parser.parse_args(argumentos)

    informe = migrar(opciones.origen, opciones.destino, opciones.sobrescribir)
    print(informe.resumen())
    return 0 if (informe.experiencias or informe.skills or informe.sobre_mi) else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
