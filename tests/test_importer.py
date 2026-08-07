"""Tests for AI-powered CV analysis.

Same approach as `test_seleccion.py`: a fake `ClienteIA`, no network. What
is checked is not that the model gets it right, but that the candidates
coming out of here respect the hard rules no matter what the response
says: nothing is saved on its own, ids never collide, and a provider
failure never crashes the upload screen.
"""
from __future__ import annotations

import json


from ancla.ai.client import AIError
from ancla.profile.importer import analyze_cv
from ancla.profile.model import Bilingual, Experience, Profile, Skill, SpokenLanguage


class ClienteFalso:
    def __init__(self, respuesta: str | Exception = "", available: bool = True):
        self.respuesta = respuesta
        self._disponible = available
        self.llamadas: list[tuple[str, str]] = []

    def complete(self, sistema: str, usuario: str) -> str:
        self.llamadas.append((sistema, usuario))
        if isinstance(self.respuesta, Exception):
            raise self.respuesta
        return self.respuesta

    def available(self) -> bool:
        return self._disponible


def _respuesta(**cambios) -> str:
    datos = {
        "experiencias": [
            {
                "titulo": {"es": "ML Developer", "en": "ML Developer"},
                "periodo": {"es": "2026 - actualidad", "en": "2026 - present"},
                "bullets": {"es": ["Pipeline completo"], "en": ["Full pipeline"]},
                "stack": {"es": "Python, Optuna", "en": "Python, Optuna"},
                "keywords": ["machine learning"],
            }
        ],
        "skills": [
            {
                "nombre": {"es": "Python", "en": "Python"},
                "categoria": "lenguaje",
                "keywords": ["python"],
            }
        ],
    }
    datos.update(cambios)
    return json.dumps(datos, ensure_ascii=False)


def test_propone_experiencias_y_skills_del_texto():
    cliente = ClienteFalso(_respuesta())
    resultado = analyze_cv(cliente, "Cualquier texto de CV.", Profile())

    assert len(resultado.experiencias) == 1
    assert resultado.experiencias[0].title["es"] == "ML Developer"
    assert len(resultado.skills) == 1
    assert resultado.skills[0].name["es"] == "Python"


def test_nada_se_guarda_aqui():
    """Only returns in-memory objects: there must be no call to almacen
    anywhere in this module."""
    import inspect

    import ancla.profile.importer as modulo

    codigo = inspect.getsource(modulo)
    assert "almacen." not in codigo


def test_los_ids_de_las_candidatas_no_chocan_con_el_perfil():
    """"C++" and "C#" are different skills (not deduplicated by name), but
    they slugify to the same id "c" — they should not overwrite each
    other's file."""
    perfil = Profile(skills=[Skill(id="c", name=Bilingual(es="C++", en="C++"))])
    respuesta = _respuesta(
        skills=[{"nombre": {"es": "C#", "en": "C#"}, "categoria": "", "keywords": []}]
    )
    resultado = analyze_cv(ClienteFalso(respuesta), "texto", perfil)
    assert resultado.skills[0].id != "c"
    assert resultado.skills[0].id.startswith("c")


def test_dos_candidatas_del_mismo_lote_con_el_mismo_nombre_se_fusionan_en_una():
    respuesta = _respuesta(
        skills=[
            {"nombre": {"es": "Python", "en": "Python"}, "categoria": "", "keywords": []},
            {"nombre": {"es": "Python", "en": "Python"}, "categoria": "", "keywords": []},
        ]
    )
    resultado = analyze_cv(ClienteFalso(respuesta), "texto", Profile())
    assert len(resultado.skills) == 1


def test_una_skill_que_ya_esta_en_el_perfil_no_se_vuelve_a_proponer():
    """Real case that prompted this: importing the English CV after the
    Spanish one must not duplicate what the Spanish one already saved."""
    perfil = Profile(skills=[Skill(id="python", name=Bilingual(es="Python", en="Python"))])
    resultado = analyze_cv(ClienteFalso(_respuesta()), "texto", perfil)
    assert resultado.skills == []
    assert "1 elemento(s)" in resultado.avisos[0]


def test_una_skill_que_ya_esta_en_el_perfil_solo_en_ingles_tampoco_se_repite():
    """The name can match in either language — the CV being imported now
    might be in whichever language the profile was missing."""
    perfil = Profile(skills=[Skill(id="python", name=Bilingual(es="", en="Python"))])
    resultado = analyze_cv(ClienteFalso(_respuesta()), "texto", perfil)
    assert resultado.skills == []


def test_una_experiencia_ya_en_el_perfil_no_se_repite_pero_las_skills_nuevas_si():
    """Daniel's full scenario: two CVs for the same role, the second with a
    couple of new skills. The experience is not duplicated; the new part is added."""
    perfil = Profile(
        skills=[Skill(id="python", name=Bilingual(es="Python", en="Python"))],
        experiences=[
            Experience(
                id="ml-developer",
                title=Bilingual(es="ML Developer", en="ML Developer"),
                period=Bilingual(es="2026 - actualidad", en="2026 - present"),
                bullets=Bilingual(es=["Pipeline completo"], en=["Full pipeline"]),
                stack=Bilingual(es="Python, Optuna", en="Python, Optuna"),
            )
        ],
    )
    respuesta = _respuesta(
        skills=[
            {"nombre": {"es": "Python", "en": "Python"}, "categoria": "", "keywords": []},
            {"nombre": {"es": "Docker", "en": "Docker"}, "categoria": "", "keywords": []},
        ]
    )
    resultado = analyze_cv(ClienteFalso(respuesta), "texto", perfil)
    assert resultado.experiencias == []
    assert [s.name["es"] for s in resultado.skills] == ["Docker"]


def test_sin_clave_no_llama_y_lo_dice():
    cliente = ClienteFalso(available=False)
    resultado = analyze_cv(cliente, "texto", Profile())
    assert resultado.experiencias == [] and resultado.skills == []
    assert "Ajustes" in resultado.avisos[0]
    assert cliente.llamadas == []


def test_un_fallo_del_proveedor_no_revienta_la_pantalla():
    cliente = ClienteFalso(AIError("clave inválida"))
    resultado = analyze_cv(cliente, "texto", Profile())
    assert resultado.experiencias == [] and resultado.skills == []
    assert resultado.avisos


def test_una_respuesta_ilegible_se_explica_como_tal():
    resultado = analyze_cv(ClienteFalso("esto no es JSON"), "texto", Profile())
    assert resultado.experiencias == [] and resultado.skills == []
    assert resultado.avisos


def test_sin_texto_no_gasta_una_llamada():
    cliente = ClienteFalso(_respuesta())
    resultado = analyze_cv(cliente, "   ", Profile())
    assert cliente.llamadas == []
    assert resultado.avisos


def test_una_experiencia_sin_titulo_se_descarta_no_se_propone_vacia():
    respuesta = _respuesta(
        experiencias=[
            {
                "titulo": {"es": "", "en": ""},
                "periodo": {"es": "", "en": ""},
                "bullets": {"es": [], "en": []},
                "stack": {"es": "", "en": ""},
                "keywords": [],
            }
        ]
    )
    resultado = analyze_cv(ClienteFalso(respuesta), "texto", Profile())
    assert resultado.experiencias == []


def test_campos_con_tipos_inesperados_no_revientan():
    """If the model returns a number where text was expected, or `null`
    instead of a list, it is treated as empty, same as the rest of the project."""
    respuesta = json.dumps(
        {
            "experiencias": [
                {
                    "titulo": {"es": "ML Developer", "en": None},
                    "periodo": 42,
                    "bullets": {"es": "no es una lista", "en": None},
                    "stack": None,
                    "keywords": "tampoco es una lista",
                }
            ],
            "skills": "esto ni siquiera es una lista",
        }
    )
    resultado = analyze_cv(ClienteFalso(respuesta), "texto", Profile())
    assert resultado.experiencias[0].title["es"] == "ML Developer"
    assert resultado.experiencias[0].bullets["es"] == []
    assert resultado.skills == []


def test_avisa_si_no_encuentra_nada_reconocible():
    resultado = analyze_cv(
        ClienteFalso('{"experiencias": [], "skills": []}'), "texto", Profile()
    )
    assert resultado.avisos


def test_el_modelo_recibe_el_texto_del_cv():
    cliente = ClienteFalso(_respuesta())
    analyze_cv(cliente, "Experiencia en analisis de datos con Python.", Profile())
    _, usuario = cliente.llamadas[0]
    assert "analisis de datos" in usuario


def test_un_cv_larguisimo_se_recorta_antes_de_enviarlo():
    cliente = ClienteFalso(_respuesta())
    analyze_cv(cliente, "x" * 50000, Profile())
    _, usuario = cliente.llamadas[0]
    assert len(usuario) < 50000


# --------------------------------------------------------------------------
# Personal skills and languages
#
# Real case that prompted this: a CV with a "PERSONAL" section (Problem-
# solving, Team player...) alongside technical "SKILLS" — the importer had
# nowhere to put the former and everything ended up as technical skills.
# --------------------------------------------------------------------------


def test_propone_skills_personales_e_idiomas_por_separado_de_las_tecnicas():
    respuesta = _respuesta(
        skills_personales=[
            {"nombre": {"es": "Trabajo en equipo", "en": "Team player"}, "keywords": ["team player"]}
        ],
        idiomas=[
            {
                "nombre": {"es": "Inglés", "en": "English"},
                "nivel": {"es": "C1 Avanzado", "en": "C1 Advanced"},
                "keywords": ["advanced english"],
            }
        ],
    )
    resultado = analyze_cv(ClienteFalso(respuesta), "texto", Profile())

    assert len(resultado.skills_personales) == 1
    assert resultado.skills_personales[0].name["es"] == "Trabajo en equipo"
    assert len(resultado.idiomas) == 1
    assert resultado.idiomas[0].name["es"] == "Inglés"
    assert resultado.idiomas[0].level["es"] == "C1 Avanzado"
    # Never sneak in among the technical skills.
    assert all(s.name["es"] != "Trabajo en equipo" for s in resultado.skills)
    assert all(s.name["es"] != "Inglés" for s in resultado.skills)


def test_una_skill_personal_sin_nombre_se_descarta():
    respuesta = _respuesta(
        skills_personales=[{"nombre": {"es": "", "en": ""}, "keywords": []}]
    )
    resultado = analyze_cv(ClienteFalso(respuesta), "texto", Profile())
    assert resultado.skills_personales == []


def test_un_idioma_sin_nombre_se_descarta():
    respuesta = _respuesta(
        idiomas=[{"nombre": {"es": "", "en": ""}, "nivel": {"es": "B2", "en": "B2"}, "keywords": []}]
    )
    resultado = analyze_cv(ClienteFalso(respuesta), "texto", Profile())
    assert resultado.idiomas == []


def test_el_id_de_una_skill_personal_no_choca_con_una_tecnica_del_perfil():
    perfil = Profile(skills=[Skill(id="python", name=Bilingual(es="Python", en="Python"))])
    respuesta = _respuesta(
        skills_personales=[
            {"nombre": {"es": "Python", "en": "Python"}, "keywords": []}
        ]
    )
    # Deliberately unusual name collision, just to check the provisional id
    # is generated correctly even when the name collides with another
    # category — it should not fail or mix up.
    resultado = analyze_cv(ClienteFalso(respuesta), "texto", perfil)
    assert len(resultado.skills_personales) == 1


def test_un_idioma_que_ya_esta_en_el_perfil_no_se_vuelve_a_proponer():
    """Even if the detected level differs (B2 in the profile, C1 in the new
    CV): dedup is by name, not by level — updating the level is a matter of
    editing the language by hand, not letting a duplicate sneak in."""
    perfil = Profile(
        languages=[
            SpokenLanguage(
                id="ingles",
                name=Bilingual(es="Inglés", en="English"),
                level=Bilingual(es="B2", en="B2"),
            )
        ]
    )
    respuesta = _respuesta(
        idiomas=[
            {
                "nombre": {"es": "Inglés", "en": "English"},
                "nivel": {"es": "C1", "en": "C1"},
                "keywords": [],
            }
        ]
    )
    resultado = analyze_cv(ClienteFalso(respuesta), "texto", perfil)
    assert resultado.idiomas == []


def test_sin_skills_personales_ni_idiomas_en_la_respuesta_no_revienta():
    """Most CVs will have neither category: absent from the JSON is not an error."""
    resultado = analyze_cv(ClienteFalso(_respuesta()), "texto", Profile())
    assert resultado.skills_personales == []
    assert resultado.idiomas == []


def test_el_aviso_de_nada_encontrado_tiene_en_cuenta_las_cuatro_categorias():
    """Used to only look at experiences and skills: if a CV only had one
    recognisable language, it should not warn that nothing was found."""
    respuesta = json.dumps(
        {
            "experiencias": [],
            "skills": [],
            "skills_personales": [],
            "idiomas": [
                {
                    "nombre": {"es": "Francés", "en": "French"},
                    "nivel": {"es": "B1", "en": "B1"},
                    "keywords": [],
                }
            ],
        }
    )
    resultado = analyze_cv(ClienteFalso(respuesta), "texto", Profile())
    assert resultado.avisos == []
    assert len(resultado.idiomas) == 1
