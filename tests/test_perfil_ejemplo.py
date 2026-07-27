"""`perfil-ejemplo/` es lo primero que ve quien clona el repo sin escribirse un
perfil propio (ver README). Este test es la red que evita que alguien lo deje
roto o incompleto sin darse cuenta."""
from __future__ import annotations

from pathlib import Path

from cv_adaptativo.perfil import almacen, validacion

RAIZ = Path(__file__).resolve().parents[1] / "perfil-ejemplo"


def test_perfil_ejemplo_carga_sin_errores_de_validacion():
    perfil = almacen.cargar_perfil(RAIZ)
    assert validacion.validar_perfil(perfil) == []


def test_perfil_ejemplo_no_esta_vacio():
    perfil = almacen.cargar_perfil(RAIZ)
    assert not perfil.esta_vacio()
    assert perfil.experiencias
    assert perfil.skills
    assert perfil.skills_personales
    assert perfil.idiomas
    assert perfil.sobre_mi is not None


def test_perfil_ejemplo_tiene_suficientes_skills_para_rellenar_sobre_mi():
    """Con menos de 3 skills por grupo, "Sobre mí" se queda con los huecos a
    la vista (ver `AVISO_SOBRE_MI_INCOMPLETO` en `seleccion/motor.py`) — el
    perfil de ejemplo tiene que enseñar el caso bueno, no ese aviso."""
    from cv_adaptativo.perfil.modelo import N_GRUPO_SOBRE_MI

    perfil = almacen.cargar_perfil(RAIZ)
    assert len(perfil.skills) >= N_GRUPO_SOBRE_MI * 2
