"""Tests del migrador del formato antiguo (.txt) a YAML.

Los ficheros de ejemplo se escriben aquí a propósito, con las mismas rarezas que
tenían los reales (una NOTA suelta, un periodo que no coincide entre idiomas,
bullets con «:» dentro). Así el test se puede ejecutar en un repositorio recién
clonado, sin depender de los datos personales de nadie.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from ancla.perfil import almacen, migrador

EXPERIENCIA_TXT = """ID: data-analyst-urban-mobility
TITULO_ES: Data Analyst — Urban Mobility Pipeline
TITULO_EN: Data Analyst — Urban Mobility Pipeline
PERIODO_ES: 2025 - ACTUALIDAD
PERIODO_EN: 2025 - PRESENT
ESTADO: actualidad

BULLETS_ES:
- Desarrollo de un pipeline ETL para procesar y limpiar conjuntos de datos.
- Aplicación de depuración sistemática para valores nulos y atípicos (outliers).

BULLETS_EN:
- Built ETL pipeline to process and clean large-scale datasets
- Applied systematic debugging to handle missing values and outliers

STACK_ES: Python · Pandas · NumPy
STACK_EN: Python · Pandas · NumPy

KEYWORDS: etl, limpieza de datos, pandas, numpy
"""

EXPERIENCIA_CON_NOTA_TXT = """ID: quantum-computing-hzh
TITULO_ES: Quantum Computing — HZH
TITULO_EN: Quantum Computing — HZH
PERIODO_ES: 2026 - TERMINADO
PERIODO_EN: 2026 - PRESENT
ESTADO: terminado

NOTA: en el CV en español el periodo pone "TERMINADO" y en el de inglés "PRESENT".
Se mantiene tal cual estaba; revisar cuando toque actualizar este proyecto.

BULLETS_ES:
- Implementación de un circuito cuántico con Qiskit: puertas H-Z-H.

BULLETS_EN:
- Implemented a quantum circuit using Qiskit

STACK_ES: Python · Qiskit
STACK_EN: Python · Qiskit

KEYWORDS: quantum computing, qiskit
"""

SKILL_TXT = """NOMBRE_ES: Pipelines de Datos (ETL)
NOMBRE_EN: Data Pipelines (ETL)
CATEGORIA: datos
KEYWORDS: etl, elt, data pipelines, orquestación
"""

SOBRE_MI_TXT = """Plantilla fija del bloque "Sobre mí". Solo se sustituyen los dos grupos de 3
elementos marcados entre llaves; el resto del texto NO se toca nunca.

GRUPO_A (3 elementos, conceptos/dominios — ej. LLMs, machine learning...):
GRUPO_B (3 elementos, lenguajes/tecnologías concretas — ej. Python, Java...):

---

ES:
Estudiante con conocimientos en {GRUPO_A_1}, {GRUPO_A_2} y {GRUPO_A_3}. Desarrollo en {GRUPO_B_1}, {GRUPO_B_2} y {GRUPO_B_3}.

EN:
Student with knowledge of {GRUPO_A_1}, {GRUPO_A_2}, and {GRUPO_A_3}. I build in {GRUPO_B_1}, {GRUPO_B_2}, and {GRUPO_B_3}.

NOTA: la versión EN original terminaba en "...agile team in Bucharest" (por el Erasmus).
Mantener esa coletilla solo en la versión Rumania/EN.
"""


def _origen(tmp_path: Path) -> Path:
    """Recrea la forma de la carpeta antigua: dos subcarpetas y la plantilla."""
    origen = tmp_path / "Informacion"
    (origen / migrador.CARPETA_EXPERIENCIA_ORIGEN).mkdir(parents=True)
    (origen / migrador.CARPETA_SKILLS_ORIGEN).mkdir(parents=True)

    experiencias = origen / migrador.CARPETA_EXPERIENCIA_ORIGEN
    (experiencias / "data-analyst-urban-mobility.txt").write_text(
        EXPERIENCIA_TXT, encoding="utf-8"
    )
    (experiencias / "quantum-computing-hzh.txt").write_text(
        EXPERIENCIA_CON_NOTA_TXT, encoding="utf-8"
    )
    (origen / migrador.CARPETA_SKILLS_ORIGEN / "data-pipelines-etl.txt").write_text(
        SKILL_TXT, encoding="utf-8"
    )
    (origen / migrador.FICHERO_SOBRE_MI_ORIGEN).write_text(
        SOBRE_MI_TXT, encoding="utf-8"
    )
    return origen


def _huella(carpeta: Path) -> list[tuple[str, str]]:
    """Nombre y contenido de todo lo que hay dentro, para comparar después."""
    return sorted(
        (
            str(ruta.relative_to(carpeta)),
            hashlib.sha256(ruta.read_bytes()).hexdigest(),
        )
        for ruta in carpeta.rglob("*")
        if ruta.is_file()
    )


# --------------------------------------------------------------------------
# La garantía principal
# --------------------------------------------------------------------------


def test_el_migrador_no_toca_la_carpeta_de_origen(tmp_path: Path):
    """Son los datos reales de una persona y siguen siendo su copia buena."""
    origen = _origen(tmp_path)
    antes = _huella(origen)

    migrador.migrar(origen, tmp_path / "perfil")

    assert _huella(origen) == antes


# --------------------------------------------------------------------------
# La conversión
# --------------------------------------------------------------------------


def test_migra_experiencias_skills_y_sobre_mi(tmp_path: Path):
    destino = tmp_path / "perfil"

    informe = migrador.migrar(_origen(tmp_path), destino)

    assert informe.experiencias == [
        "data-analyst-urban-mobility",
        "quantum-computing-hzh",
    ]
    assert informe.skills == ["data-pipelines-etl"]
    assert informe.sobre_mi is True


def test_lo_migrado_se_puede_volver_a_cargar_como_perfil(tmp_path: Path):
    """La prueba de verdad: la app abre lo que ha escrito el migrador."""
    destino = tmp_path / "perfil"
    migrador.migrar(_origen(tmp_path), destino)

    perfil = almacen.cargar_perfil(destino)

    experiencia = perfil.experiencia("data-analyst-urban-mobility")
    assert experiencia.titulo["en"] == "Data Analyst — Urban Mobility Pipeline"
    assert experiencia.periodo["es"] == "2025 - ACTUALIDAD"
    assert experiencia.estado == "actualidad"
    assert experiencia.stack["es"] == "Python · Pandas · NumPy"
    assert experiencia.keywords == ["etl", "limpieza de datos", "pandas", "numpy"]


def test_los_bullets_llegan_tal_cual_los_escribio_el_usuario(tmp_path: Path):
    """Regla dura del producto: al usuario no se le reescribe."""
    destino = tmp_path / "perfil"
    migrador.migrar(_origen(tmp_path), destino)

    experiencia = almacen.cargar_perfil(destino).experiencia(
        "data-analyst-urban-mobility"
    )

    assert experiencia.bullets["es"] == [
        "Desarrollo de un pipeline ETL para procesar y limpiar conjuntos de datos.",
        "Aplicación de depuración sistemática para valores nulos y atípicos (outliers).",
    ]
    assert experiencia.bullets["en"] == [
        "Built ETL pipeline to process and clean large-scale datasets",
        "Applied systematic debugging to handle missing values and outliers",
    ]


def test_migra_la_skill_con_su_categoria(tmp_path: Path):
    destino = tmp_path / "perfil"
    migrador.migrar(_origen(tmp_path), destino)

    skill = almacen.cargar_perfil(destino).skill("data-pipelines-etl")

    assert skill.nombre["es"] == "Pipelines de Datos (ETL)"
    assert skill.nombre["en"] == "Data Pipelines (ETL)"
    assert skill.categoria == "datos"
    assert "orquestación" in skill.keywords


def test_el_sobre_mi_conserva_los_seis_huecos(tmp_path: Path):
    """El párrafo de instrucciones de arriba del fichero no es parte del texto."""
    destino = tmp_path / "perfil"
    migrador.migrar(_origen(tmp_path), destino)

    sobre_mi = almacen.cargar_perfil(destino).sobre_mi

    assert sobre_mi.plantilla["es"].startswith("Estudiante con conocimientos")
    assert sobre_mi.plantilla["en"].startswith("Student with knowledge")
    for hueco in sobre_mi.huecos():
        assert hueco in sobre_mi.plantilla["es"]
        assert hueco in sobre_mi.plantilla["en"]


def test_un_periodo_incoherente_se_migra_tal_cual(tmp_path: Path):
    """Que ES diga TERMINADO y EN diga PRESENT es cosa del usuario, no del
    migrador: no se «arregla» por su cuenta."""
    destino = tmp_path / "perfil"
    migrador.migrar(_origen(tmp_path), destino)

    experiencia = almacen.cargar_perfil(destino).experiencia("quantum-computing-hzh")

    assert experiencia.periodo["es"] == "2026 - TERMINADO"
    assert experiencia.periodo["en"] == "2026 - PRESENT"


# --------------------------------------------------------------------------
# Lo que el modelo no representa, y lo que ya estaba
# --------------------------------------------------------------------------


def test_una_nota_del_formato_antiguo_no_se_pierde(tmp_path: Path):
    """El modelo no tiene campo para notas: se conserva como comentario y se avisa."""
    destino = tmp_path / "perfil"

    informe = migrador.migrar(_origen(tmp_path), destino)

    yaml_ = almacen.ruta_experiencia(destino, "quantum-computing-hzh")
    texto = yaml_.read_text(encoding="utf-8")
    assert texto.startswith("# NOTA heredada de quantum-computing-hzh.txt:")
    assert "TERMINADO" in texto.splitlines()[1]
    assert any("NOTA" in aviso for aviso in informe.avisos)
    # Y sigue siendo un YAML válido que se puede cargar.
    assert almacen.cargar_perfil(destino).experiencia("quantum-computing-hzh")


def test_no_pisa_lo_que_ya_existe_y_lo_dice(tmp_path: Path):
    origen, destino = _origen(tmp_path), tmp_path / "perfil"
    migrador.migrar(origen, destino)
    ruta = almacen.ruta_skill(destino, "data-pipelines-etl")
    ruta.write_text("nombre: editada a mano\n", encoding="utf-8")

    informe = migrador.migrar(origen, destino)

    assert informe.skills == []
    assert any("data-pipelines-etl.yaml" in texto for texto in informe.omitidos)
    assert ruta.read_text(encoding="utf-8") == "nombre: editada a mano\n"


def test_sobrescribir_pisa_lo_que_haya_solo_si_se_pide(tmp_path: Path):
    origen, destino = _origen(tmp_path), tmp_path / "perfil"
    migrador.migrar(origen, destino)
    almacen.ruta_skill(destino, "data-pipelines-etl").write_text("nombre: x\n", encoding="utf-8")

    informe = migrador.migrar(origen, destino, sobrescribir=True)

    assert informe.skills == ["data-pipelines-etl"]
    assert almacen.cargar_perfil(destino).skill("data-pipelines-etl").categoria == "datos"


# --------------------------------------------------------------------------
# Casos de borde
# --------------------------------------------------------------------------


def test_un_origen_que_no_existe_lo_dice_sin_reventar(tmp_path: Path):
    informe = migrador.migrar(tmp_path / "no-existe", tmp_path / "perfil")

    assert informe.experiencias == []
    assert any("no existe" in aviso for aviso in informe.avisos)


def test_una_carpeta_sin_sobre_mi_avisa_pero_migra_el_resto(tmp_path: Path):
    origen = _origen(tmp_path)
    (origen / migrador.FICHERO_SOBRE_MI_ORIGEN).unlink()

    informe = migrador.migrar(origen, tmp_path / "perfil")

    assert informe.sobre_mi is False
    assert informe.experiencias
    assert any("Sobre mí" in aviso for aviso in informe.avisos)


def test_el_informe_avisa_de_lo_que_quedo_incompleto(tmp_path: Path):
    """Migrar y validar van juntos: si un .txt venía a medias, se dice ahora."""
    origen = _origen(tmp_path)
    (origen / migrador.CARPETA_SKILLS_ORIGEN / "a-medias.txt").write_text(
        "NOMBRE_ES: Sin nada más\n", encoding="utf-8"
    )

    informe = migrador.migrar(origen, tmp_path / "perfil")

    assert "a-medias" in informe.skills
    assert any("a-medias.txt →" in aviso for aviso in informe.avisos)


def test_el_resumen_se_puede_enseñar_tal_cual(tmp_path: Path):
    informe = migrador.migrar(_origen(tmp_path), tmp_path / "perfil")

    resumen = informe.resumen()

    assert "Experiencias migradas: 2" in resumen
    assert "Skills migradas: 1" in resumen
