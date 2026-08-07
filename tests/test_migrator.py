"""Tests for the migrator from the old (.txt) format to YAML.

The example files are written here on purpose, with the same quirks the
real ones had (a loose NOTA, a period that does not match between
languages, bullets with a ":" inside). That way the test can run against a
freshly cloned repository, without depending on anyone's personal data.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from ancla.profile import store, migrator

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
Estudiante con conocimientos en {GROUP_A_1}, {GROUP_A_2} y {GROUP_A_3}. Desarrollo en {GROUP_B_1}, {GROUP_B_2} y {GROUP_B_3}.

EN:
Student with knowledge of {GROUP_A_1}, {GROUP_A_2}, and {GROUP_A_3}. I build in {GROUP_B_1}, {GROUP_B_2}, and {GROUP_B_3}.

NOTA: la versión EN original terminaba en "...agile team in Bucharest" (por el Erasmus).
Mantener esa coletilla solo en la versión Rumania/EN.
"""


def _origen(tmp_path: Path) -> Path:
    """Recreates the shape of the old folder: two subfolders and the template."""
    origen = tmp_path / "Informacion"
    (origen / migrator.CARPETA_EXPERIENCIA_ORIGEN).mkdir(parents=True)
    (origen / migrator.CARPETA_SKILLS_ORIGEN).mkdir(parents=True)

    experiencias = origen / migrator.CARPETA_EXPERIENCIA_ORIGEN
    (experiencias / "data-analyst-urban-mobility.txt").write_text(
        EXPERIENCIA_TXT, encoding="utf-8"
    )
    (experiencias / "quantum-computing-hzh.txt").write_text(
        EXPERIENCIA_CON_NOTA_TXT, encoding="utf-8"
    )
    (origen / migrator.CARPETA_SKILLS_ORIGEN / "data-pipelines-etl.txt").write_text(
        SKILL_TXT, encoding="utf-8"
    )
    (origen / migrator.FICHERO_SOBRE_MI_ORIGEN).write_text(
        SOBRE_MI_TXT, encoding="utf-8"
    )
    return origen


def _huella(carpeta: Path) -> list[tuple[str, str]]:
    """Name and content of everything inside, to compare afterwards."""
    return sorted(
        (
            str(ruta.relative_to(carpeta)),
            hashlib.sha256(ruta.read_bytes()).hexdigest(),
        )
        for ruta in carpeta.rglob("*")
        if ruta.is_file()
    )


# --------------------------------------------------------------------------
# The main guarantee
# --------------------------------------------------------------------------


def test_el_migrador_no_toca_la_carpeta_de_origen(tmp_path: Path):
    """It is a person's real data and it stays their good copy."""
    origen = _origen(tmp_path)
    antes = _huella(origen)

    migrator.migrate(origen, tmp_path / "perfil")

    assert _huella(origen) == antes


# --------------------------------------------------------------------------
# The conversion
# --------------------------------------------------------------------------


def test_migra_experiencias_skills_y_sobre_mi(tmp_path: Path):
    destino = tmp_path / "perfil"

    informe = migrator.migrate(_origen(tmp_path), destino)

    assert informe.experiencias == [
        "data-analyst-urban-mobility",
        "quantum-computing-hzh",
    ]
    assert informe.skills == ["data-pipelines-etl"]
    assert informe.sobre_mi is True


def test_lo_migrado_se_puede_volver_a_cargar_como_perfil(tmp_path: Path):
    """The real test: the app opens what the migrator wrote."""
    destino = tmp_path / "perfil"
    migrator.migrate(_origen(tmp_path), destino)

    perfil = store.load_profile(destino)

    experiencia = perfil.experience("data-analyst-urban-mobility")
    assert experiencia.title["en"] == "Data Analyst — Urban Mobility Pipeline"
    assert experiencia.period["es"] == "2025 - ACTUALIDAD"
    assert experiencia.status == "actualidad"
    assert experiencia.stack["es"] == "Python · Pandas · NumPy"
    assert experiencia.keywords == ["etl", "limpieza de datos", "pandas", "numpy"]


def test_los_bullets_llegan_tal_cual_los_escribio_el_usuario(tmp_path: Path):
    """Hard product rule: the user is never rewritten."""
    destino = tmp_path / "perfil"
    migrator.migrate(_origen(tmp_path), destino)

    experiencia = store.load_profile(destino).experience(
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
    migrator.migrate(_origen(tmp_path), destino)

    skill = store.load_profile(destino).skill("data-pipelines-etl")

    assert skill.name["es"] == "Pipelines de Datos (ETL)"
    assert skill.name["en"] == "Data Pipelines (ETL)"
    assert skill.category == "datos"
    assert "orquestación" in skill.keywords


def test_el_sobre_mi_conserva_los_seis_huecos(tmp_path: Path):
    """The instructions paragraph at the top of the file is not part of the text."""
    destino = tmp_path / "perfil"
    migrator.migrate(_origen(tmp_path), destino)

    sobre_mi = store.load_profile(destino).about_me

    assert sobre_mi.template["es"].startswith("Estudiante con conocimientos")
    assert sobre_mi.template["en"].startswith("Student with knowledge")
    for hueco in sobre_mi.gaps():
        assert hueco in sobre_mi.template["es"]
        assert hueco in sobre_mi.template["en"]


def test_un_periodo_incoherente_se_migra_tal_cual(tmp_path: Path):
    """ES saying TERMINADO and EN saying PRESENT is the user's business, not
    the migrator's: it is never "fixed" on its own."""
    destino = tmp_path / "perfil"
    migrator.migrate(_origen(tmp_path), destino)

    experiencia = store.load_profile(destino).experience("quantum-computing-hzh")

    assert experiencia.period["es"] == "2026 - TERMINADO"
    assert experiencia.period["en"] == "2026 - PRESENT"


# --------------------------------------------------------------------------
# What the model does not represent, and what was already there
# --------------------------------------------------------------------------


def test_una_nota_del_formato_antiguo_no_se_pierde(tmp_path: Path):
    """The model has no field for notes: it is kept as a comment and flagged."""
    destino = tmp_path / "perfil"

    informe = migrator.migrate(_origen(tmp_path), destino)

    yaml_ = store.experience_path(destino, "quantum-computing-hzh")
    texto = yaml_.read_text(encoding="utf-8")
    assert texto.startswith("# NOTA heredada de quantum-computing-hzh.txt:")
    assert "TERMINADO" in texto.splitlines()[1]
    assert any("NOTA" in aviso for aviso in informe.avisos)
    # And it is still a valid YAML file that can be loaded.
    assert store.load_profile(destino).experience("quantum-computing-hzh")


def test_no_pisa_lo_que_ya_existe_y_lo_dice(tmp_path: Path):
    origen, destino = _origen(tmp_path), tmp_path / "perfil"
    migrator.migrate(origen, destino)
    ruta = store.skill_path(destino, "data-pipelines-etl")
    ruta.write_text("name: editada a mano\n", encoding="utf-8")

    informe = migrator.migrate(origen, destino)

    assert informe.skills == []
    assert any("data-pipelines-etl.yaml" in texto for texto in informe.omitidos)
    assert ruta.read_text(encoding="utf-8") == "name: editada a mano\n"


def test_sobrescribir_pisa_lo_que_haya_solo_si_se_pide(tmp_path: Path):
    origen, destino = _origen(tmp_path), tmp_path / "perfil"
    migrator.migrate(origen, destino)
    store.skill_path(destino, "data-pipelines-etl").write_text("name: x\n", encoding="utf-8")

    informe = migrator.migrate(origen, destino, sobrescribir=True)

    assert informe.skills == ["data-pipelines-etl"]
    assert store.load_profile(destino).skill("data-pipelines-etl").category == "datos"


# --------------------------------------------------------------------------
# Edge cases
# --------------------------------------------------------------------------


def test_un_origen_que_no_existe_lo_dice_sin_reventar(tmp_path: Path):
    informe = migrator.migrate(tmp_path / "no-existe", tmp_path / "perfil")

    assert informe.experiencias == []
    assert any("no existe" in aviso for aviso in informe.avisos)


def test_una_carpeta_sin_sobre_mi_avisa_pero_migra_el_resto(tmp_path: Path):
    origen = _origen(tmp_path)
    (origen / migrator.FICHERO_SOBRE_MI_ORIGEN).unlink()

    informe = migrator.migrate(origen, tmp_path / "perfil")

    assert informe.sobre_mi is False
    assert informe.experiencias
    assert any("Sobre mí" in aviso for aviso in informe.avisos)


def test_el_informe_avisa_de_lo_que_quedo_incompleto(tmp_path: Path):
    """Migrating and validating go together: if a .txt was half-done, it is
    reported now."""
    origen = _origen(tmp_path)
    (origen / migrator.CARPETA_SKILLS_ORIGEN / "a-medias.txt").write_text(
        "NOMBRE_ES: Sin nada más\n", encoding="utf-8"
    )

    informe = migrator.migrate(origen, tmp_path / "perfil")

    assert "a-medias" in informe.skills
    assert any("a-medias.txt →" in aviso for aviso in informe.avisos)


def test_el_resumen_se_puede_enseñar_tal_cual(tmp_path: Path):
    informe = migrator.migrate(_origen(tmp_path), tmp_path / "perfil")

    summary = informe.summary()

    assert "Experiencias migradas: 2" in summary
    assert "Skills migradas: 1" in summary
