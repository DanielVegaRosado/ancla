"""Profile validation tests.

What is checked is not just *that* a failure is detected, but that the
message is useful: in Spanish, saying which item it is, with no Python
jargon. The user reads it on screen and has to know which file to open.
"""
from __future__ import annotations

from ancla.profile import validation
from ancla.profile.model import (
    AboutMe,
    Bilingual,
    Education,
    Experience,
    Profile,
    Skill,
    SpokenLanguage,
)

PLANTILLA = (
    "Estudiante con conocimientos en {GROUP_A_1}, {GROUP_A_2} y {GROUP_A_3}. "
    "Desarrollo en {GROUP_B_1}, {GROUP_B_2} y {GROUP_B_3}."
)


def _experiencia(**cambios) -> Experience:
    base = dict(
        id="ml-telco-churn",
        title=Bilingual(es="ML Developer", en="ML Developer"),
        period_start="2026", period_end="ongoing",
        bullets=Bilingual(es=["Pipeline completo"], en=["Full pipeline"]),
        stack="Python · Optuna",
        keywords=["machine learning"],
    )
    return Experience(**{**base, **cambios})


def _skill(**cambios) -> Skill:
    base = dict(
        id="python",
        name=Bilingual(es="Python", en="Python"),
        category="lenguaje",
        keywords=["python"],
    )
    return Skill(**{**base, **cambios})


def _idioma(**cambios) -> SpokenLanguage:
    base = dict(
        id="ingles",
        name=Bilingual(es="Inglés", en="English"),
        level=Bilingual(es="C1 — Avanzado", en="C1 — Advanced"),
        keywords=["advanced english"],
    )
    return SpokenLanguage(**{**base, **cambios})


def _educacion(**cambios) -> Education:
    base = dict(
        id="grado",
        title=Bilingual(es="Grado en Ingeniería Informática", en="BSc in Computer Engineering"),
        institution="UEMC",
        period_start="2023", period_end="2027",
    )
    return Education(**{**base, **cambios})


def _sobre_mi(es: str = PLANTILLA, en: str = PLANTILLA) -> AboutMe:
    return AboutMe(template=Bilingual(es=es, en=en))


def _perfil_completo() -> Profile:
    return Profile(
        experiences=[_experiencia()], skills=[_skill()], about_me=_sobre_mi()
    )


# --------------------------------------------------------------------------
# Valid data raises no issues
# --------------------------------------------------------------------------


def test_un_perfil_completo_no_tiene_ningun_problema():
    assert validation.validate_profile(_perfil_completo()).messages() == []


def test_una_experiencia_completa_no_tiene_ningun_problema():
    assert validation.validate_experience(_experiencia()).messages() == []


def test_una_skill_completa_no_tiene_ningun_problema():
    assert validation.validate_skill(_skill()).messages() == []


# --------------------------------------------------------------------------
# Experience
# --------------------------------------------------------------------------


def test_falta_la_traduccion_al_ingles_avisa_pero_no_bloquea():
    """The whole point of importing in one language: half a bilingual entry
    is unfinished, not wrong, and it has to be savable."""
    problemas = validation.validate_experience(
        _experiencia(title=Bilingual(es="ML Developer", en="   "))
    )

    assert problemas.errors == []
    assert len(problemas.warnings) == 1
    assert "inglés" in problemas.warnings[0]
    assert "ml-telco-churn" in problemas.warnings[0]


def test_detecta_una_experiencia_sin_puntos():
    problemas = validation.validate_experience(
        _experiencia(bullets=Bilingual(es=[], en=["Full pipeline"]))
    ).messages()

    assert any("no tiene ningún punto" in p and "español" in p for p in problemas)


def test_detecta_un_punto_en_blanco():
    problemas = validation.validate_experience(
        _experiencia(bullets=Bilingual(es=["Pipeline", "  "], en=["Full pipeline"]))
    ).messages()

    assert any("punto vacío" in p for p in problemas)


def test_avisa_de_una_experiencia_sin_palabras_clave():
    """Breaks nothing: it would simply never be chosen, and that is invisible."""
    problemas = validation.validate_experience(_experiencia(keywords=[])).messages()

    assert any("palabras clave" in p for p in problemas)


def test_un_inicio_posterior_al_fin_es_un_error():
    problemas = validation.validate_experience(
        _experiencia(period_start="2026", period_end="2025")
    )

    assert any("coherente" in e for e in problemas.errors)


def test_un_inicio_igual_al_fin_es_coherente():
    problemas = validation.validate_experience(
        _experiencia(period_start="2025", period_end="2025")
    )

    assert problemas.errors == []


def test_un_fin_marcador_no_se_compara_con_el_inicio():
    """`ongoing` / `finished` are words, not years: nothing to compare."""
    problemas = validation.validate_experience(
        _experiencia(period_start="2026", period_end="ongoing")
    )

    assert problemas.errors == []


def test_un_fin_vacio_no_se_compara_con_el_inicio():
    problemas = validation.validate_experience(
        _experiencia(period_start="2026", period_end="")
    )

    assert problemas.errors == []


def test_los_mensajes_van_en_castellano_y_sin_jerga():
    problemas = validation.validate_experience(
        Experience(
            id="a-medias",
            title=Bilingual(es="", en=""),
            period_start="", period_end="",
            bullets=Bilingual(es=[], en=[]),
            stack="",
        )
    ).messages()

    assert problemas
    for problema in problemas:
        assert "a-medias" in problema
        assert problema[-1] == "."
        for jerga in ("None", "Traceback", "Exception", "NotImplemented"):
            assert jerga not in problema


# --------------------------------------------------------------------------
# Skills
# --------------------------------------------------------------------------


def test_detecta_una_skill_sin_categoria_ni_palabras_clave():
    problemas = validation.validate_skill(_skill(category="", keywords=[])).messages()

    assert len(problemas) == 2
    assert any("categoría" in p for p in problemas)
    assert any("palabras clave" in p for p in problemas)


# --------------------------------------------------------------------------
# About me
# --------------------------------------------------------------------------


def test_detecta_que_falta_un_hueco_en_el_sobre_mi():
    problemas = validation.validate_about_me(
        _sobre_mi(es=PLANTILLA.replace("{GROUP_B_3}", "Java"))
    ).messages()

    assert len(problemas) == 1
    assert "{GROUP_B_3}" in problemas[0]
    assert "español" in problemas[0]


def test_detecta_un_hueco_inventado_que_nadie_va_a_rellenar():
    """A {GROUP_C_1} would be left in the final CV exactly as written."""
    problemas = validation.validate_about_me(
        _sobre_mi(en=PLANTILLA + " Además {GROUP_C_1}.")
    ).messages()

    assert any("{GROUP_C_1}" in p for p in problemas)


def test_un_sobre_mi_escrito_en_un_solo_idioma_solo_avisa():
    problemas = validation.validate_about_me(_sobre_mi(es=""))

    assert problemas.errors == []
    assert len(problemas.warnings) == 1
    assert "español" in problemas.warnings[0]


def test_detecta_un_sobre_mi_vacio_en_los_dos_idiomas():
    problemas = validation.validate_about_me(_sobre_mi(es="", en="")).messages()

    assert len(problemas) == 1
    assert "vacío" in problemas[0]


# --------------------------------------------------------------------------
# The whole profile
# --------------------------------------------------------------------------


def test_un_perfil_vacio_lo_dice_una_sola_vez():
    problemas = validation.validate_profile(Profile()).messages()

    assert any("está vacío" in p for p in problemas)
    assert any("Sobre mí" in p for p in problemas)
    assert not any("No hay ninguna experiencia" in p for p in problemas)


def test_un_perfil_sin_skills_pero_con_experiencia_avisa_de_las_skills():
    problemas = validation.validate_profile(
        Profile(experiences=[_experiencia()], about_me=_sobre_mi())
    ).messages()

    assert any("No hay ninguna skill" in p for p in problemas)


def test_detecta_ids_repetidos():
    """Saved CVs reference by id: repeating it breaks the historical archive."""
    perfil = Profile(
        experiences=[_experiencia(), _experiencia()],
        skills=[_skill()],
        about_me=_sobre_mi(),
    )

    problemas = validation.validate_profile(perfil).messages()

    assert any("mismo identificador" in p and "ml-telco-churn" in p for p in problemas)


def test_el_perfil_junta_los_problemas_de_cada_elemento():
    perfil = Profile(
        experiences=[_experiencia(keywords=[])],
        skills=[_skill(category="")],
        about_me=_sobre_mi(),
    )

    problemas = validation.validate_profile(perfil).messages()

    assert any("ml-telco-churn" in p for p in problemas)
    assert any("python" in p for p in problemas)


def test_falta_el_sobre_mi():
    problemas = validation.validate_profile(
        Profile(experiences=[_experiencia()], skills=[_skill()])
    ).messages()

    assert any("Falta el «Sobre mí»" in p for p in problemas)


# --------------------------------------------------------------------------
# Personal skills and languages: optional catalogs
# --------------------------------------------------------------------------


def test_una_skill_personal_completa_no_tiene_ningun_problema():
    skill = Skill(id="equipo", name=Bilingual(es="Trabajo en equipo", en="Teamwork"),
                   keywords=["team player"])
    assert validation.validate_personal_skill(skill).messages() == []


def test_una_skill_personal_no_necesita_categoria():
    """Unlike a technical skill: there is no category grouping here."""
    skill = Skill(id="equipo", name=Bilingual(es="Trabajo en equipo", en="Teamwork"),
                   keywords=["team player"])
    problemas = validation.validate_personal_skill(skill).messages()
    assert not any("categoría" in problema for problema in problemas)


def test_detecta_una_skill_personal_sin_palabras_clave():
    skill = Skill(id="equipo", name=Bilingual(es="Trabajo en equipo", en="Teamwork"))
    problemas = validation.validate_personal_skill(skill).messages()
    assert any("palabras clave" in problema for problema in problemas)


def test_un_idioma_completo_no_tiene_ningun_problema():
    assert validation.validate_language(_idioma()).messages() == []


def test_detecta_que_falta_el_nivel_de_un_idioma():
    idioma = _idioma(level=Bilingual(es="C1 — Avanzado", en=""))
    problemas = validation.validate_language(idioma).messages()
    assert any("nivel" in problema and "inglés" in problema for problema in problemas)


def test_avisa_de_un_idioma_sin_palabras_clave():
    idioma = _idioma(keywords=[])
    problemas = validation.validate_language(idioma).messages()
    assert any("hueco" in problema for problema in problemas)


def test_una_educacion_completa_no_tiene_ningun_problema():
    assert validation.validate_education(_educacion()).messages() == []


def test_detecta_que_falta_el_centro_de_una_educacion():
    educacion = _educacion(institution="")
    problemas = validation.validate_education(educacion).messages()
    assert any("centro" in problema for problema in problemas)


def test_una_educacion_no_necesita_palabras_clave():
    """A diferencia de skills/idiomas: la educación nunca se compara contra
    los huecos de una vacante, así que no necesita keywords."""
    assert validation.validate_education(_educacion()).messages() == []


def test_una_educacion_con_inicio_posterior_al_fin_es_un_error():
    """Misma regla que en experiencia: la coherencia del periodo se
    comparte, no se duplica."""
    problemas = validation.validate_education(
        _educacion(period_start="2027", period_end="2023")
    )

    assert any("coherente" in e for e in problemas.errors)


def test_una_educacion_en_curso_no_se_compara_con_el_marcador():
    problemas = validation.validate_education(
        _educacion(period_start="2027", period_end="ongoing")
    )

    assert problemas.errors == []


def test_un_perfil_sin_skills_personales_ni_idiomas_es_valido():
    """They are optional: not passing them is not a problem with the profile."""
    assert validation.validate_profile(_perfil_completo()).messages() == []


def test_el_perfil_valida_las_skills_personales_y_los_idiomas_que_tenga():
    perfil = Profile(
        experiences=[_experiencia()],
        skills=[_skill()],
        personal_skills=[Skill(id="", name=Bilingual(es="", en=""))],
        languages=[_idioma(level=Bilingual(es="", en=""))],
        about_me=_sobre_mi(),
    )
    problemas = validation.validate_profile(perfil).messages()
    assert any("skill personal" in p.lower() for p in problemas)
    assert any("nivel" in p for p in problemas)


def test_detecta_ids_repetidos_en_skills_personales_e_idiomas():
    perfil = Profile(
        experiences=[_experiencia()],
        skills=[_skill()],
        personal_skills=[
            Skill(id="equipo", name=Bilingual(es="A", en="A"), keywords=["a"]),
            Skill(id="equipo", name=Bilingual(es="B", en="B"), keywords=["b"]),
        ],
        languages=[_idioma(id="fr"), _idioma(id="fr")],
        about_me=_sobre_mi(),
    )
    problemas = validation.validate_profile(perfil).messages()
    assert any("skills personales" in p for p in problemas)
    assert any("idiomas" in p for p in problemas)
