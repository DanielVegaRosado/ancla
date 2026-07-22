"""Tests del motor de selección.

Todos usan un `ClienteIA` falso: aquí no se toca la red ni se gasta una sola
llamada al proveedor. Lo que se comprueba no es que el modelo acierte —eso no
depende de nosotros— sino que **la propuesta que sale del motor cumple las
reglas duras del producto pase lo que pase por la respuesta del modelo**:
nada inventado, ningún bullet reescrito, y todo con motivo.
"""
from __future__ import annotations

import json

import pytest

from cv_adaptativo.ia.cliente import ErrorIA
from cv_adaptativo.perfil.modelo import (
    N_GRUPO_SOBRE_MI,
    Bilingue,
    Experiencia,
    IdiomaHablado,
    Perfil,
    Skill,
    SobreMi,
)
from cv_adaptativo.seleccion.motor import MOTIVO_AUSENTE, adaptar

VACANTE = """\
Backend Engineer en Nubelia

Buscamos a alguien que trabaje con Python y FastAPI sobre PostgreSQL,
y que haya montado pipelines con Airflow.

Requisitos: Python, FastAPI, PostgreSQL, Airflow, Kubernetes.
"""


# --------------------------------------------------------------------------
# Dobles y datos de prueba
# --------------------------------------------------------------------------


class ClienteFalso:
    """Cumple el Protocol `ClienteIA` y anota con qué se le llamó."""

    def __init__(self, respuesta: str | Exception = "") -> None:
        self.respuesta = respuesta
        self.llamadas: list[tuple[str, str]] = []

    def completar(self, sistema: str, usuario: str) -> str:
        self.llamadas.append((sistema, usuario))
        if isinstance(self.respuesta, Exception):
            raise self.respuesta
        return self.respuesta

    def disponible(self) -> bool:
        return True


def _experiencia(id: str, titulo_es: str, titulo_en: str, keywords: list[str]):
    return Experiencia(
        id=id,
        titulo=Bilingue(es=titulo_es, en=titulo_en),
        periodo=Bilingue(es="2025", en="2025"),
        bullets=Bilingue(es=[f"Bullet original de {id}"], en=[f"Original bullet {id}"]),
        stack=Bilingue(es="Python", en="Python"),
        keywords=keywords,
    )


def _skill(id: str, nombre_es: str, nombre_en: str, keywords: list[str] | None = None):
    return Skill(
        id=id,
        nombre=Bilingue(es=nombre_es, en=nombre_en),
        categoria="tecnica",
        keywords=keywords or [nombre_en],
    )


def _perfil() -> Perfil:
    return Perfil(
        experiencias=[
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
        sobre_mi=SobreMi(
            plantilla=Bilingue(
                es=(
                    "Ingeniero con interés en {GRUPO_A_1}, {GRUPO_A_2} y {GRUPO_A_3}. "
                    "Trabajo con {GRUPO_B_1}, {GRUPO_B_2} y {GRUPO_B_3}."
                ),
                en=(
                    "Engineer interested in {GRUPO_A_1}, {GRUPO_A_2} and {GRUPO_A_3}. "
                    "I work with {GRUPO_B_1}, {GRUPO_B_2} and {GRUPO_B_3}."
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


def _adaptar(respuesta: str | Exception = None, perfil: Perfil | None = None, **kwargs):
    cliente = ClienteFalso(_respuesta() if respuesta is None else respuesta)
    propuesta = adaptar(perfil or _perfil(), VACANTE, "es", cliente, **kwargs)
    return propuesta, cliente


# --------------------------------------------------------------------------
# El camino normal
# --------------------------------------------------------------------------


def test_respeta_las_elecciones_y_el_orden_del_modelo():
    propuesta, _ = _adaptar()
    assert [e.id for e in propuesta.experiencias] == [
        "api-pagos",
        "pipeline-datos",
        "bot-telegram",
        "tfg-vision",
    ]
    assert propuesta.skills[:4] == ["python", "fastapi", "bbdd", "airflow"]
    assert propuesta.idioma == "es"


def test_una_sola_llamada_al_modelo_por_adaptacion():
    _, cliente = _adaptar()
    assert len(cliente.llamadas) == 1


def test_no_devuelve_mas_elementos_de_los_que_caben():
    propuesta, _ = _adaptar(n_experiencias=2, n_skills=3)
    assert len(propuesta.experiencias) == 2
    assert len(propuesta.skills) == 3


def test_ignora_ids_repetidos():
    respuesta = _respuesta(
        experiencias=[{"id": "api-pagos", "motivo": "a"}, {"id": "api-pagos", "motivo": "b"}],
        skills=["python", "python", "fastapi"],
    )
    propuesta, _ = _adaptar(respuesta)
    assert [e.id for e in propuesta.experiencias][:1] == ["api-pagos"]
    assert propuesta.experiencias[0].motivo == "a"
    assert propuesta.skills.count("python") == 1


# --------------------------------------------------------------------------
# Regla 1: nunca proponer algo que no exista en el perfil
# --------------------------------------------------------------------------


def test_descarta_una_experiencia_que_el_modelo_se_ha_inventado():
    respuesta = _respuesta(
        experiencias=[
            {"id": "consultoria-en-kubernetes", "motivo": "Encaja con la vacante."},
            {"id": "api-pagos", "motivo": "Cubre FastAPI."},
        ]
    )
    propuesta, _ = _adaptar(respuesta)
    ids = [e.id for e in propuesta.experiencias]
    assert "consultoria-en-kubernetes" not in ids
    assert ids[0] == "api-pagos"


def test_descarta_una_skill_que_el_modelo_se_ha_inventado():
    propuesta, _ = _adaptar(_respuesta(skills=["kubernetes", "python"]))
    assert "kubernetes" not in propuesta.skills
    assert propuesta.skills[0] == "python"


def test_todo_lo_propuesto_existe_en_el_perfil():
    perfil = _perfil()
    propuesta, _ = _adaptar(perfil=perfil)
    assert all(perfil.experiencia(e.id) is not None for e in propuesta.experiencias)
    assert all(perfil.skill(s) is not None for s in propuesta.skills)


def test_devuelve_los_que_haya_si_el_perfil_tiene_menos():
    base = _perfil()
    perfil = Perfil(
        experiencias=base.experiencias[:2],
        skills=base.skills[:6],
        sobre_mi=base.sobre_mi,
    )
    propuesta, _ = _adaptar(perfil=perfil, n_experiencias=4, n_skills=9)
    assert len(propuesta.experiencias) == 2
    assert len(propuesta.skills) == 6


# --------------------------------------------------------------------------
# Regla 2: nunca reescribir al usuario
# --------------------------------------------------------------------------


def test_la_propuesta_guarda_referencias_no_texto_del_usuario():
    # Aunque el modelo devuelva bullets reescritos, no hay por dónde colarlos:
    # la propuesta solo tiene ids.
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
    nombres_reales = {s.nombre["es"] for s in perfil.skills}
    elegidos = propuesta.sobre_mi.grupo_a + propuesta.sobre_mi.grupo_b
    assert set(elegidos) <= nombres_reales
    for inventada in ("Kubernetes", "Blockchain", "Rust"):
        assert inventada not in propuesta.sobre_mi.texto


def test_el_sobre_mi_no_deja_huecos_sin_rellenar():
    propuesta, _ = _adaptar()
    assert "{GRUPO_A_1}" not in propuesta.sobre_mi.texto
    assert "{GRUPO_B_3}" not in propuesta.sobre_mi.texto
    assert len(propuesta.sobre_mi.grupo_a) == N_GRUPO_SOBRE_MI
    assert len(propuesta.sobre_mi.grupo_b) == N_GRUPO_SOBRE_MI


def test_el_sobre_mi_no_repite_una_skill_en_los_dos_grupos():
    respuesta = _respuesta(
        sobre_mi={
            "grupo_a": ["Python", "FastAPI", "Airflow"],
            "grupo_b": ["Python", "FastAPI", "Airflow"],
            "motivo": "",
        }
    )
    propuesta, _ = _adaptar(respuesta)
    assert not set(propuesta.sobre_mi.grupo_a) & set(propuesta.sobre_mi.grupo_b)


def test_el_sobre_mi_usa_el_nombre_en_el_idioma_del_cv():
    # El modelo responde en inglés y el CV es en español: manda el perfil.
    respuesta = _respuesta(
        sobre_mi={
            "grupo_a": ["Machine learning", "Databases", "Testing"],
            "grupo_b": ["Python", "FastAPI", "Airflow"],
            "motivo": "",
        }
    )
    propuesta, _ = _adaptar(respuesta)
    assert "Aprendizaje automático" in propuesta.sobre_mi.grupo_a
    assert "Bases de datos" in propuesta.sobre_mi.grupo_a
    assert "Machine learning" not in propuesta.sobre_mi.texto


def test_sin_skills_suficientes_deja_la_plantilla_a_la_vista():
    base = _perfil()
    perfil = Perfil(
        experiencias=base.experiencias,
        skills=base.skills[:2],
        sobre_mi=base.sobre_mi,
    )
    propuesta, _ = _adaptar(perfil=perfil)
    assert "{GRUPO_A_3}" in propuesta.sobre_mi.texto
    assert "skills" in propuesta.sobre_mi.motivo


# --------------------------------------------------------------------------
# Regla 3: toda elección lleva motivo
# --------------------------------------------------------------------------


def test_toda_experiencia_lleva_motivo_aunque_el_modelo_no_lo_dé():
    respuesta = _respuesta(experiencias=["api-pagos", "pipeline-datos"], motivo_skills="")
    propuesta, _ = _adaptar(respuesta)
    assert all(e.motivo.strip() for e in propuesta.experiencias)
    assert propuesta.experiencias[0].motivo == MOTIVO_AUSENTE
    assert propuesta.motivo_skills.strip()


def test_hay_motivo_en_todos_los_bloques():
    propuesta, _ = _adaptar()
    assert propuesta.motivo_skills.strip()
    assert propuesta.sobre_mi.motivo.strip()
    assert all(e.motivo.strip() for e in propuesta.experiencias)


def test_completa_desde_el_perfil_y_lo_dice_en_el_motivo():
    respuesta = _respuesta(experiencias=[{"id": "api-pagos", "motivo": "Cubre FastAPI."}])
    propuesta, _ = _adaptar(respuesta, n_experiencias=4)
    assert len(propuesta.experiencias) == 4
    completadas = propuesta.experiencias[1:]
    assert all("sistema" in e.motivo for e in completadas)
    # La primera completada es la que más keywords comparte con la vacante.
    assert completadas[0].id == "pipeline-datos"


def test_al_completar_skills_lo_avisa_en_el_motivo():
    propuesta, _ = _adaptar(_respuesta(skills=["python"]), n_skills=9)
    assert len(propuesta.skills) == 9
    assert "completado" in propuesta.motivo_skills


# --------------------------------------------------------------------------
# Regla 4: lo que falta va a huecos, no al CV
# --------------------------------------------------------------------------


def test_los_huecos_llegan_al_usuario():
    propuesta, _ = _adaptar()
    assert propuesta.huecos == ["Kubernetes"]
    assert "Kubernetes" not in propuesta.skills


def test_descarta_un_hueco_que_el_usuario_sí_tiene():
    respuesta = _respuesta(huecos=["Kubernetes", "Python", "  ", "kubernetes"])
    propuesta, _ = _adaptar(respuesta)
    assert propuesta.huecos == ["Kubernetes"]


def test_descarta_un_hueco_de_idioma_redactado_en_prosa():
    """El caso real que motivó esto: el modelo no ve `perfil.idiomas` (no se le
    envía, es lo que garantiza que nunca acabe en Sobre mí ni en Skills
    técnicas) así que reporta el idioma como hueco casi siempre, y encima lo
    redacta como frase («Nivel avanzado de inglés»), no como el nombre exacto
    de la skill. Coincidencia exacta no lo habría anulado."""
    perfil = _perfil()
    perfil = Perfil(
        experiencias=perfil.experiencias,
        skills=perfil.skills,
        idiomas=[
            IdiomaHablado(
                id="ingles",
                nombre=Bilingue(es="Inglés", en="English"),
                nivel=Bilingue(es="C1 — Avanzado", en="C1 — Advanced"),
                keywords=["advanced english", "fluido", "ingles avanzado"],
            )
        ],
        sobre_mi=perfil.sobre_mi,
    )
    respuesta = _respuesta(huecos=["Kubernetes", "Nivel avanzado de inglés"])
    propuesta, _ = _adaptar(respuesta, perfil=perfil)
    assert propuesta.huecos == ["Kubernetes"]


def test_descarta_un_hueco_de_skill_personal_por_nombre():
    perfil = _perfil()
    perfil = Perfil(
        experiencias=perfil.experiencias,
        skills=perfil.skills,
        skills_personales=[
            Skill(
                id="trabajo-equipo",
                nombre=Bilingue(es="Trabajo en equipo", en="Teamwork"),
                keywords=["team player", "colaboracion"],
            )
        ],
        sobre_mi=perfil.sobre_mi,
    )
    respuesta = _respuesta(huecos=["Kubernetes", "Capacidad de trabajo en equipo"])
    propuesta, _ = _adaptar(respuesta, perfil=perfil)
    assert propuesta.huecos == ["Kubernetes"]


def test_skills_personales_e_idiomas_nunca_llegan_al_modelo():
    """La garantía tiene que ser arquitectónica: si aparecieran en el prompt,
    dependería de que el modelo obedeciera una instrucción de no elegirlas."""
    perfil = _perfil()
    perfil = Perfil(
        experiencias=perfil.experiencias,
        skills=perfil.skills,
        skills_personales=[
            Skill(id="liderazgo", nombre=Bilingue(es="Liderazgo", en="Leadership"))
        ],
        idiomas=[
            IdiomaHablado(
                id="frances",
                nombre=Bilingue(es="Francés", en="French"),
                nivel=Bilingue(es="B2", en="B2"),
            )
        ],
        sobre_mi=perfil.sobre_mi,
    )
    _, cliente = _adaptar(perfil=perfil)
    _, usuario = cliente.llamadas[0]
    assert "Liderazgo" not in usuario
    assert "Francés" not in usuario


def test_skills_personales_e_idiomas_nunca_pueden_salir_seleccionados():
    """Aunque el modelo, por lo que sea, devolviera su id, el motor no puede
    seleccionar algo que no está en `perfil.skills` — es una lista distinta."""
    perfil = _perfil()
    perfil = Perfil(
        experiencias=perfil.experiencias,
        skills=perfil.skills,
        skills_personales=[
            Skill(id="liderazgo", nombre=Bilingue(es="Liderazgo", en="Leadership"))
        ],
        sobre_mi=perfil.sobre_mi,
    )
    respuesta = _respuesta(skills=["python", "liderazgo"])
    propuesta, _ = _adaptar(respuesta, perfil=perfil)
    assert "liderazgo" not in propuesta.skills


# --------------------------------------------------------------------------
# El prompt y la respuesta del proveedor
# --------------------------------------------------------------------------


def test_el_modelo_recibe_la_vacante_y_el_catalogo():
    _, cliente = _adaptar()
    _, usuario = cliente.llamadas[0]
    assert "Airflow" in usuario and "Kubernetes" in usuario  # la vacante
    assert "api-pagos" in usuario and "bbdd" in usuario  # los ids del perfil


def test_el_catalogo_va_en_el_idioma_del_cv():
    cliente = ClienteFalso(_respuesta())
    adaptar(_perfil(), VACANTE, "en", cliente)
    _, usuario = cliente.llamadas[0]
    assert "Payments API" in usuario
    assert "API de pagos" not in usuario


def test_entiende_un_json_envuelto_en_bloque_de_codigo():
    respuesta = f"Claro, aquí tienes:\n```json\n{_respuesta()}\n```\n¡Suerte!"
    propuesta, _ = _adaptar(respuesta)
    assert propuesta.experiencias[0].id == "api-pagos"


def test_una_respuesta_ilegible_es_un_error_para_el_usuario():
    with pytest.raises(ErrorIA):
        _adaptar("Lo siento, no puedo ayudarte con eso.")


def test_una_respuesta_mal_formada_es_un_error_para_el_usuario():
    with pytest.raises(ErrorIA):
        _adaptar('{"experiencias": [')


def test_una_respuesta_que_no_es_un_objeto_es_un_error_para_el_usuario():
    with pytest.raises(ErrorIA):
        _adaptar('["api-pagos"]')


def test_el_fallo_del_proveedor_se_propaga_tal_cual():
    with pytest.raises(ErrorIA):
        _adaptar(ErrorIA("Clave de API no válida."))


# --------------------------------------------------------------------------
# No se gasta una llamada si la petición no tiene sentido
# --------------------------------------------------------------------------


def test_un_perfil_vacio_no_llega_a_llamar_al_modelo():
    cliente = ClienteFalso(_respuesta())
    with pytest.raises(ValueError):
        adaptar(Perfil(), VACANTE, "es", cliente)
    assert cliente.llamadas == []


def test_un_perfil_sin_sobre_mi_no_llega_a_llamar_al_modelo():
    base = _perfil()
    perfil = Perfil(experiencias=base.experiencias, skills=base.skills, sobre_mi=None)
    cliente = ClienteFalso(_respuesta())
    with pytest.raises(ValueError):
        adaptar(perfil, VACANTE, "es", cliente)
    assert cliente.llamadas == []


def test_una_vacante_vacia_no_llega_a_llamar_al_modelo():
    cliente = ClienteFalso(_respuesta())
    with pytest.raises(ValueError):
        adaptar(_perfil(), "   \n ", "es", cliente)
    assert cliente.llamadas == []
