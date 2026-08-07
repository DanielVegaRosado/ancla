"""`perfil-ejemplo/` is the first thing anyone sees when they clone the repo
without writing their own profile (see README). This test is the safety net
that stops someone leaving it broken or incomplete without noticing."""
from __future__ import annotations

from pathlib import Path

from ancla.profile import store, validation

RAIZ = Path(__file__).resolve().parents[1] / "perfil-ejemplo"


def test_perfil_ejemplo_carga_sin_errores_de_validacion():
    perfil = store.load_profile(RAIZ)
    assert validation.validate_profile(perfil) == []


def test_perfil_ejemplo_no_esta_vacio():
    perfil = store.load_profile(RAIZ)
    assert not perfil.is_empty()
    assert perfil.experiences
    assert perfil.skills
    assert perfil.personal_skills
    assert perfil.languages
    assert perfil.about_me is not None


def test_perfil_ejemplo_tiene_suficientes_skills_para_rellenar_sobre_mi():
    """With fewer than 3 skills per group, "About me" is left with visible
    gaps (see `AVISO_SOBRE_MI_INCOMPLETO` in `seleccion/motor.py`) — the
    example profile has to demonstrate the good case, not that warning."""
    from ancla.profile.model import N_ABOUT_ME_GROUP

    perfil = store.load_profile(RAIZ)
    assert len(perfil.skills) >= N_ABOUT_ME_GROUP * 2
