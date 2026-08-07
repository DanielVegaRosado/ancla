"""Tests for the selection engine.

All of these use a fake `ClienteIA`: no network is touched here, not a
single call to the provider is spent. What is checked is not that the
model gets it right — that is not up to us — but that **the proposal
coming out of the engine follows the product's hard rules no matter what
the model's response says**: nothing invented, no bullet rewritten, and
everything with a reason.
"""
from __future__ import annotations

import json

import pytest

from ancla.ai.client import AIError
from ancla.profile.model import (
    N_ABOUT_ME_GROUP,
    AboutMe,
    Bilingual,
    Experience,
    Profile,
    Skill,
    SpokenLanguage,
)
from ancla.selection.engine import MOTIVO_AUSENTE, adapt

VACANTE = """\
Backend Engineer en Nubelia

Buscamos a alguien que trabaje con Python y FastAPI sobre PostgreSQL,
y que haya montado pipelines con Airflow.

Requisitos: Python, FastAPI, PostgreSQL, Airflow, Kubernetes.
"""


# --------------------------------------------------------------------------
# Test doubles and fixtures
# --------------------------------------------------------------------------


class ClienteFalso:
    """Satisfies the `ClienteIA` Protocol and records what it was called with."""

    def __init__(self, respuesta: str | Exception = "") -> None:
        self.respuesta = respuesta
        self.llamadas: list[tuple[str, str]] = []

    def complete(self, sistema: str, usuario: str) -> str:
        self.llamadas.append((sistema, usuario))
        if isinstance(self.respuesta, Exception):
            raise self.respuesta
        return self.respuesta

    def available(self) -> bool:
        return True


def _experiencia(id: str, titulo_es: str, titulo_en: str, keywords: list[str]):
    return Experience(
        id=id,
        title=Bilingual(es=titulo_es, en=titulo_en),
        period=Bilingual(es="2025", en="2025"),
        bullets=Bilingual(es=[f"Bullet original de {id}"], en=[f"Original bullet {id}"]),
        stack=Bilingual(es="Python", en="Python"),
        keywords=keywords,
    )


def _skill(id: str, nombre_es: str, nombre_en: str, keywords: list[str] | None = None):
    return Skill(
        id=id,
        name=Bilingual(es=nombre_es, en=nombre_en),
        category="tecnica",
        keywords=keywords or [nombre_en],
    )


def _perfil() -> Profile:
    return Profile(
        experiences=[
            _experiencia("api-pagos", "API de pagos", "Payments API", ["FastAPI", "PostgreSQL"]),
            _experiencia("pipeline-datos", "Pipeline de datos", "Data pipeline", ["Airflow", "ETL"]),
            _experiencia("bot-telegram", "Bot de Telegram", "Telegram bot", ["LLM", "agentes"]),
            _experiencia("web-inmobiliaria", "Web inmobiliaria", "Real estate site", ["React"]),
            _experiencia("tfg-vision", "TFG de visión", "Computer vision thesis", ["PyTorch"]),
        ],
        skills=[
            _skill("python", "Python", "Python"),
            _skill("fastapi", "FastAPI", "FastAPI"),
            _skill("bbdd", "Bases de datos", "Databases", ["PostgreSQL"]),
            _skill("airflow", "Airflow", "Airflow"),
            _skill("docker", "Docker", "Docker"),
            _skill("git", "Git", "Git"),
            _skill("ml", "Aprendizaje automático", "Machine learning", ["PyTorch"]),
            _skill("react", "React", "React"),
            _skill("javascript", "JavaScript", "JavaScript"),
            _skill("testing", "Testing", "Testing"),
        ],
        about_me=AboutMe(
            template=Bilingual(
                es=(
                    "Ingeniero con interés en {GROUP_A_1}, {GROUP_A_2} y {GROUP_A_3}. "
                    "Trabajo con {GROUP_B_1}, {GROUP_B_2} y {GROUP_B_3}."
                ),
                en=(
                    "Engineer interested in {GROUP_A_1}, {GROUP_A_2} and {GROUP_A_3}. "
                    "I work with {GROUP_B_1}, {GROUP_B_2} and {GROUP_B_3}."
                ),
            )
        ),
    )


def _respuesta(**cambios) -> str:
    datos = {
        "experiencias": [
            {"id": "api-pagos", "motivo": "Cubre FastAPI y PostgreSQL."},
            {"id": "pipeline-datos", "motivo": "Cubre Airflow."},
            {"id": "bot-telegram", "motivo": "Python en producción."},
            {"id": "tfg-vision", "motivo": "Aporta variedad de stack."},
        ],
        "skills": ["python", "fastapi", "bbdd", "airflow", "docker", "git", "testing"],
        "motivo_skills": "Las que pide la vacante, primero el stack principal.",
        "sobre_mi": {
            "grupo_a": ["Bases de datos", "Aprendizaje automático", "Testing"],
            "grupo_b": ["Python", "FastAPI", "Airflow"],
            "motivo": "Refleja el stack de la vacante.",
        },
        "huecos": ["Kubernetes"],
    }
    datos.update(cambios)
    return json.dumps(datos, ensure_ascii=False)


def _adaptar(respuesta: str | Exception = None, perfil: Profile | None = None, **kwargs):
    cliente = ClienteFalso(_respuesta() if respuesta is None else respuesta)
    propuesta = adapt(perfil or _perfil(), VACANTE, "es", cliente, **kwargs)
    return propuesta, cliente


# --------------------------------------------------------------------------
# The normal path
# --------------------------------------------------------------------------


def test_respeta_las_elecciones_y_el_orden_del_modelo():
    propuesta, _ = _adaptar()
    assert [e.id for e in propuesta.experiences] == [
        "api-pagos",
        "pipeline-datos",
        "bot-telegram",
        "tfg-vision",
    ]
    assert propuesta.skills[:4] == ["python", "fastapi", "bbdd", "airflow"]
    assert propuesta.language == "es"


def test_una_sola_llamada_al_modelo_por_adaptacion():
    _, cliente = _adaptar()
    assert len(cliente.llamadas) == 1


def test_no_devuelve_mas_elementos_de_los_que_caben():
    propuesta, _ = _adaptar(n_experiencias=2, n_skills=3)
    assert len(propuesta.experiences) == 2
    assert len(propuesta.skills) == 3


def test_ignora_ids_repetidos():
    respuesta = _respuesta(
        experiencias=[{"id": "api-pagos", "motivo": "a"}, {"id": "api-pagos", "motivo": "b"}],
        skills=["python", "python", "fastapi"],
    )
    propuesta, _ = _adaptar(respuesta)
    assert [e.id for e in propuesta.experiences][:1] == ["api-pagos"]
    assert propuesta.experiences[0].reason == "a"
    assert propuesta.skills.count("python") == 1


# --------------------------------------------------------------------------
# Rule 1: never propose something that does not exist in the profile
# --------------------------------------------------------------------------


def test_descarta_una_experiencia_que_el_modelo_se_ha_inventado():
    respuesta = _respuesta(
        experiencias=[
            {"id": "consultoria-en-kubernetes", "motivo": "Encaja con la vacante."},
            {"id": "api-pagos", "motivo": "Cubre FastAPI."},
        ]
    )
    propuesta, _ = _adaptar(respuesta)
    ids = [e.id for e in propuesta.experiences]
    assert "consultoria-en-kubernetes" not in ids
    assert ids[0] == "api-pagos"


def test_descarta_una_skill_que_el_modelo_se_ha_inventado():
    propuesta, _ = _adaptar(_respuesta(skills=["kubernetes", "python"]))
    assert "kubernetes" not in propuesta.skills
    assert propuesta.skills[0] == "python"


def test_todo_lo_propuesto_existe_en_el_perfil():
    perfil = _perfil()
    propuesta, _ = _adaptar(perfil=perfil)
    assert all(perfil.experience(e.id) is not None for e in propuesta.experiences)
    assert all(perfil.skill(s) is not None for s in propuesta.skills)


def test_devuelve_los_que_haya_si_el_perfil_tiene_menos():
    base = _perfil()
    perfil = Profile(
        experiences=base.experiences[:2],
        skills=base.skills[:6],
        about_me=base.about_me,
    )
    propuesta, _ = _adaptar(perfil=perfil, n_experiencias=4, n_skills=9)
    assert len(propuesta.experiences) == 2
    assert len(propuesta.skills) == 6


# --------------------------------------------------------------------------
# Rule 2: never rewrite the user
# --------------------------------------------------------------------------


def test_la_propuesta_guarda_referencias_no_texto_del_usuario():
    # Even if the model returns rewritten bullets, there is nowhere for
    # them to sneak in: the proposal only holds ids.
    respuesta = _respuesta(
        experiencias=[
            {
                "id": "api-pagos",
                "motivo": "Cubre FastAPI.",
                "bullets": ["Bullet REESCRITO por el modelo"],
                "titulo": "Título inventado",
            }
        ]
    )
    propuesta, _ = _adaptar(respuesta)
    serializada = json.dumps(propuesta.__dict__, default=str, ensure_ascii=False)
    assert "REESCRITO" not in serializada
    assert "Bullet original" not in serializada


def test_el_sobre_mi_solo_inserta_nombres_de_skills_del_perfil():
    perfil = _perfil()
    respuesta = _respuesta(
        sobre_mi={
            "grupo_a": ["Kubernetes", "Blockchain", "Bases de datos"],
            "grupo_b": ["Python", "Rust", "FastAPI"],
            "motivo": "Lo que pide la vacante.",
        }
    )
    propuesta, _ = _adaptar(respuesta, perfil=perfil)
    nombres_reales = {s.name["es"] for s in perfil.skills}
    elegidos = propuesta.about_me.group_a + propuesta.about_me.group_b
    assert set(elegidos) <= nombres_reales
    for inventada in ("Kubernetes", "Blockchain", "Rust"):
        assert inventada not in propuesta.about_me.text


def test_el_sobre_mi_no_deja_huecos_sin_rellenar():
    propuesta, _ = _adaptar()
    assert "{GROUP_A_1}" not in propuesta.about_me.text
    assert "{GROUP_B_3}" not in propuesta.about_me.text
    assert len(propuesta.about_me.group_a) == N_ABOUT_ME_GROUP
    assert len(propuesta.about_me.group_b) == N_ABOUT_ME_GROUP


def test_el_sobre_mi_no_repite_una_skill_en_los_dos_grupos():
    respuesta = _respuesta(
        sobre_mi={
            "grupo_a": ["Python", "FastAPI", "Airflow"],
            "grupo_b": ["Python", "FastAPI", "Airflow"],
            "motivo": "",
        }
    )
    propuesta, _ = _adaptar(respuesta)
    assert not set(propuesta.about_me.group_a) & set(propuesta.about_me.group_b)


def test_el_sobre_mi_usa_el_nombre_en_el_idioma_del_cv():
    # The model responds in English and the CV is in Spanish: the profile wins.
    respuesta = _respuesta(
        sobre_mi={
            "grupo_a": ["Machine learning", "Databases", "Testing"],
            "grupo_b": ["Python", "FastAPI", "Airflow"],
            "motivo": "",
        }
    )
    propuesta, _ = _adaptar(respuesta)
    assert "Aprendizaje automático" in propuesta.about_me.group_a
    assert "Bases de datos" in propuesta.about_me.group_a
    assert "Machine learning" not in propuesta.about_me.text


def test_sin_skills_suficientes_deja_la_plantilla_a_la_vista():
    base = _perfil()
    perfil = Profile(
        experiences=base.experiences,
        skills=base.skills[:2],
        about_me=base.about_me,
    )
    propuesta, _ = _adaptar(perfil=perfil)
    assert "{GROUP_A_3}" in propuesta.about_me.text
    assert "skills" in propuesta.about_me.reason


# --------------------------------------------------------------------------
# Rule 3: every choice carries a reason
# --------------------------------------------------------------------------


def test_toda_experiencia_lleva_motivo_aunque_el_modelo_no_lo_dé():
    respuesta = _respuesta(experiencias=["api-pagos", "pipeline-datos"], motivo_skills="")
    propuesta, _ = _adaptar(respuesta)
    assert all(e.reason.strip() for e in propuesta.experiences)
    assert propuesta.experiences[0].reason == MOTIVO_AUSENTE
    assert propuesta.skills_reason.strip()


def test_hay_motivo_en_todos_los_bloques():
    propuesta, _ = _adaptar()
    assert propuesta.skills_reason.strip()
    assert propuesta.about_me.reason.strip()
    assert all(e.reason.strip() for e in propuesta.experiences)


def test_completa_desde_el_perfil_y_lo_dice_en_el_motivo():
    respuesta = _respuesta(experiencias=[{"id": "api-pagos", "motivo": "Cubre FastAPI."}])
    propuesta, _ = _adaptar(respuesta, n_experiencias=4)
    assert len(propuesta.experiences) == 4
    completadas = propuesta.experiences[1:]
    assert all("sistema" in e.reason for e in completadas)
    # The first one filled in is the one sharing the most keywords with the posting.
    assert completadas[0].id == "pipeline-datos"


def test_al_completar_skills_lo_avisa_en_el_motivo():
    propuesta, _ = _adaptar(_respuesta(skills=["python"]), n_skills=9)
    assert len(propuesta.skills) == 9
    assert "completado" in propuesta.skills_reason


# --------------------------------------------------------------------------
# Rule 4: what is missing goes to gaps, not the CV
# --------------------------------------------------------------------------


def test_los_huecos_llegan_al_usuario():
    propuesta, _ = _adaptar()
    assert propuesta.gaps == ["Kubernetes"]
    assert "Kubernetes" not in propuesta.skills


def test_descarta_un_hueco_que_el_usuario_sí_tiene():
    respuesta = _respuesta(huecos=["Kubernetes", "Python", "  ", "kubernetes"])
    propuesta, _ = _adaptar(respuesta)
    assert propuesta.gaps == ["Kubernetes"]


def test_descarta_un_hueco_de_idioma_redactado_en_prosa():
    """Real case that prompted this: the model never sees `perfil.idiomas`
    (never sent to it: that is what guarantees it can never end up in About
    me nor in technical Skills), so it reports the language as a gap almost
    every time, and worded as a sentence ("Advanced level of English"), not
    the skill's exact name. An exact match would not have cleared it."""
    perfil = _perfil()
    perfil = Profile(
        experiences=perfil.experiences,
        skills=perfil.skills,
        languages=[
            SpokenLanguage(
                id="ingles",
                name=Bilingual(es="Inglés", en="English"),
                level=Bilingual(es="C1 — Avanzado", en="C1 — Advanced"),
                keywords=["advanced english", "fluido", "ingles avanzado"],
            )
        ],
        about_me=perfil.about_me,
    )
    respuesta = _respuesta(huecos=["Kubernetes", "Nivel avanzado de inglés"])
    propuesta, _ = _adaptar(respuesta, perfil=perfil)
    assert propuesta.gaps == ["Kubernetes"]


def test_descarta_un_hueco_de_skill_personal_por_nombre():
    perfil = _perfil()
    perfil = Profile(
        experiences=perfil.experiences,
        skills=perfil.skills,
        personal_skills=[
            Skill(
                id="trabajo-equipo",
                name=Bilingual(es="Trabajo en equipo", en="Teamwork"),
                keywords=["team player", "colaboracion"],
            )
        ],
        about_me=perfil.about_me,
    )
    respuesta = _respuesta(huecos=["Kubernetes", "Capacidad de trabajo en equipo"])
    propuesta, _ = _adaptar(respuesta, perfil=perfil)
    assert propuesta.gaps == ["Kubernetes"]


def test_skills_personales_e_idiomas_nunca_llegan_al_modelo():
    """The guarantee has to be architectural: if they showed up in the
    prompt, it would depend on the model obeying an instruction not to pick them."""
    perfil = _perfil()
    perfil = Profile(
        experiences=perfil.experiences,
        skills=perfil.skills,
        personal_skills=[
            Skill(id="liderazgo", name=Bilingual(es="Liderazgo", en="Leadership"))
        ],
        languages=[
            SpokenLanguage(
                id="frances",
                name=Bilingual(es="Francés", en="French"),
                level=Bilingual(es="B2", en="B2"),
            )
        ],
        about_me=perfil.about_me,
    )
    _, cliente = _adaptar(perfil=perfil)
    _, usuario = cliente.llamadas[0]
    assert "Liderazgo" not in usuario
    assert "Francés" not in usuario


def test_skills_personales_e_idiomas_nunca_pueden_salir_seleccionados():
    """Even if the model somehow returned its id, the engine cannot select
    something that is not in `perfil.skills` — it is a different list."""
    perfil = _perfil()
    perfil = Profile(
        experiences=perfil.experiences,
        skills=perfil.skills,
        personal_skills=[
            Skill(id="liderazgo", name=Bilingual(es="Liderazgo", en="Leadership"))
        ],
        about_me=perfil.about_me,
    )
    respuesta = _respuesta(skills=["python", "liderazgo"])
    propuesta, _ = _adaptar(respuesta, perfil=perfil)
    assert "liderazgo" not in propuesta.skills


# --------------------------------------------------------------------------
# The prompt and the provider's response
# --------------------------------------------------------------------------


def test_el_modelo_recibe_la_vacante_y_el_catalogo():
    _, cliente = _adaptar()
    _, usuario = cliente.llamadas[0]
    assert "Airflow" in usuario and "Kubernetes" in usuario  # the job posting
    assert "api-pagos" in usuario and "bbdd" in usuario  # the profile's ids


def test_el_catalogo_va_en_el_idioma_del_cv():
    cliente = ClienteFalso(_respuesta())
    adapt(_perfil(), VACANTE, "en", cliente)
    _, usuario = cliente.llamadas[0]
    assert "Payments API" in usuario
    assert "API de pagos" not in usuario


def test_entiende_un_json_envuelto_en_bloque_de_codigo():
    respuesta = f"Claro, aquí tienes:\n```json\n{_respuesta()}\n```\n¡Suerte!"
    propuesta, _ = _adaptar(respuesta)
    assert propuesta.experiences[0].id == "api-pagos"


def test_una_respuesta_ilegible_es_un_error_para_el_usuario():
    with pytest.raises(AIError):
        _adaptar("Lo siento, no puedo ayudarte con eso.")


def test_una_respuesta_mal_formada_es_un_error_para_el_usuario():
    with pytest.raises(AIError):
        _adaptar('{"experiencias": [')


def test_una_respuesta_que_no_es_un_objeto_es_un_error_para_el_usuario():
    with pytest.raises(AIError):
        _adaptar('["api-pagos"]')


def test_el_fallo_del_proveedor_se_propaga_tal_cual():
    with pytest.raises(AIError):
        _adaptar(AIError("Clave de API no válida."))


# --------------------------------------------------------------------------
# No call is spent if the request makes no sense
# --------------------------------------------------------------------------


def test_un_perfil_vacio_no_llega_a_llamar_al_modelo():
    cliente = ClienteFalso(_respuesta())
    with pytest.raises(ValueError):
        adapt(Profile(), VACANTE, "es", cliente)
    assert cliente.llamadas == []


def test_un_perfil_sin_sobre_mi_no_llega_a_llamar_al_modelo():
    base = _perfil()
    perfil = Profile(experiences=base.experiences, skills=base.skills, about_me=None)
    cliente = ClienteFalso(_respuesta())
    with pytest.raises(ValueError):
        adapt(perfil, VACANTE, "es", cliente)
    assert cliente.llamadas == []


def test_una_vacante_vacia_no_llega_a_llamar_al_modelo():
    cliente = ClienteFalso(_respuesta())
    with pytest.raises(ValueError):
        adapt(_perfil(), "   \n ", "es", cliente)
    assert cliente.llamadas == []
