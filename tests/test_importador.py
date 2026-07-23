"""Tests del análisis de CV con IA.

Mismo criterio que `test_seleccion.py`: un `ClienteIA` falso, sin tocar la
red. Lo que se comprueba no es que el modelo acierte, sino que las candidatas
que salen de aquí respetan las reglas duras pase lo que pase en la respuesta:
nada se guarda solo, los ids nunca chocan, y un fallo del proveedor nunca
revienta la pantalla de subida.
"""
from __future__ import annotations

import json


from cv_adaptativo.ia.cliente import ErrorIA
from cv_adaptativo.perfil.importador import analizar_cv
from cv_adaptativo.perfil.modelo import Bilingue, Experiencia, IdiomaHablado, Perfil, Skill


class ClienteFalso:
    def __init__(self, respuesta: str | Exception = "", disponible: bool = True):
        self.respuesta = respuesta
        self._disponible = disponible
        self.llamadas: list[tuple[str, str]] = []

    def completar(self, sistema: str, usuario: str) -> str:
        self.llamadas.append((sistema, usuario))
        if isinstance(self.respuesta, Exception):
            raise self.respuesta
        return self.respuesta

    def disponible(self) -> bool:
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
    resultado = analizar_cv(cliente, "Cualquier texto de CV.", Perfil())

    assert len(resultado.experiencias) == 1
    assert resultado.experiencias[0].titulo["es"] == "ML Developer"
    assert len(resultado.skills) == 1
    assert resultado.skills[0].nombre["es"] == "Python"


def test_nada_se_guarda_aqui():
    """Solo devuelve objetos en memoria: no debe existir ninguna llamada a
    almacen dentro de este módulo."""
    import inspect

    import cv_adaptativo.perfil.importador as modulo

    codigo = inspect.getsource(modulo)
    assert "almacen." not in codigo


def test_los_ids_de_las_candidatas_no_chocan_con_el_perfil():
    """"C++" y "C#" son skills distintas (no se deduplican por nombre), pero
    slugifican al mismo id "c" — no deberían pisarse el fichero el uno al otro."""
    perfil = Perfil(skills=[Skill(id="c", nombre=Bilingue(es="C++", en="C++"))])
    respuesta = _respuesta(
        skills=[{"nombre": {"es": "C#", "en": "C#"}, "categoria": "", "keywords": []}]
    )
    resultado = analizar_cv(ClienteFalso(respuesta), "texto", perfil)
    assert resultado.skills[0].id != "c"
    assert resultado.skills[0].id.startswith("c")


def test_dos_candidatas_del_mismo_lote_con_el_mismo_nombre_se_fusionan_en_una():
    respuesta = _respuesta(
        skills=[
            {"nombre": {"es": "Python", "en": "Python"}, "categoria": "", "keywords": []},
            {"nombre": {"es": "Python", "en": "Python"}, "categoria": "", "keywords": []},
        ]
    )
    resultado = analizar_cv(ClienteFalso(respuesta), "texto", Perfil())
    assert len(resultado.skills) == 1


def test_una_skill_que_ya_esta_en_el_perfil_no_se_vuelve_a_proponer():
    """El caso real que motivó esto: importar el CV en inglés después del CV
    en español no debe duplicar lo que el español ya guardó."""
    perfil = Perfil(skills=[Skill(id="python", nombre=Bilingue(es="Python", en="Python"))])
    resultado = analizar_cv(ClienteFalso(_respuesta()), "texto", perfil)
    assert resultado.skills == []
    assert "1 elemento(s)" in resultado.avisos[0]


def test_una_skill_que_ya_esta_en_el_perfil_solo_en_ingles_tampoco_se_repite():
    """El nombre puede coincidir en cualquiera de los dos idiomas — el CV que
    se importa ahora puede estar en el idioma que le faltaba al perfil."""
    perfil = Perfil(skills=[Skill(id="python", nombre=Bilingue(es="", en="Python"))])
    resultado = analizar_cv(ClienteFalso(_respuesta()), "texto", perfil)
    assert resultado.skills == []


def test_una_experiencia_ya_en_el_perfil_no_se_repite_pero_las_skills_nuevas_si():
    """El escenario completo de Daniel: dos CVs del mismo puesto, el segundo
    con un par de skills nuevas. La experiencia no se duplica; lo nuevo sí entra."""
    perfil = Perfil(
        skills=[Skill(id="python", nombre=Bilingue(es="Python", en="Python"))],
        experiencias=[
            Experiencia(
                id="ml-developer",
                titulo=Bilingue(es="ML Developer", en="ML Developer"),
                periodo=Bilingue(es="2026 - actualidad", en="2026 - present"),
                bullets=Bilingue(es=["Pipeline completo"], en=["Full pipeline"]),
                stack=Bilingue(es="Python, Optuna", en="Python, Optuna"),
            )
        ],
    )
    respuesta = _respuesta(
        skills=[
            {"nombre": {"es": "Python", "en": "Python"}, "categoria": "", "keywords": []},
            {"nombre": {"es": "Docker", "en": "Docker"}, "categoria": "", "keywords": []},
        ]
    )
    resultado = analizar_cv(ClienteFalso(respuesta), "texto", perfil)
    assert resultado.experiencias == []
    assert [s.nombre["es"] for s in resultado.skills] == ["Docker"]


def test_sin_clave_no_llama_y_lo_dice():
    cliente = ClienteFalso(disponible=False)
    resultado = analizar_cv(cliente, "texto", Perfil())
    assert resultado.experiencias == [] and resultado.skills == []
    assert "Ajustes" in resultado.avisos[0]
    assert cliente.llamadas == []


def test_un_fallo_del_proveedor_no_revienta_la_pantalla():
    cliente = ClienteFalso(ErrorIA("clave inválida"))
    resultado = analizar_cv(cliente, "texto", Perfil())
    assert resultado.experiencias == [] and resultado.skills == []
    assert resultado.avisos


def test_una_respuesta_ilegible_se_explica_como_tal():
    resultado = analizar_cv(ClienteFalso("esto no es JSON"), "texto", Perfil())
    assert resultado.experiencias == [] and resultado.skills == []
    assert resultado.avisos


def test_sin_texto_no_gasta_una_llamada():
    cliente = ClienteFalso(_respuesta())
    resultado = analizar_cv(cliente, "   ", Perfil())
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
    resultado = analizar_cv(ClienteFalso(respuesta), "texto", Perfil())
    assert resultado.experiencias == []


def test_campos_con_tipos_inesperados_no_revientan():
    """Si el modelo devuelve un número donde se esperaba texto, o `null` en
    vez de una lista, se trata como vacío, igual que en el resto del proyecto."""
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
    resultado = analizar_cv(ClienteFalso(respuesta), "texto", Perfil())
    assert resultado.experiencias[0].titulo["es"] == "ML Developer"
    assert resultado.experiencias[0].bullets["es"] == []
    assert resultado.skills == []


def test_avisa_si_no_encuentra_nada_reconocible():
    resultado = analizar_cv(
        ClienteFalso('{"experiencias": [], "skills": []}'), "texto", Perfil()
    )
    assert resultado.avisos


def test_el_modelo_recibe_el_texto_del_cv():
    cliente = ClienteFalso(_respuesta())
    analizar_cv(cliente, "Experiencia en analisis de datos con Python.", Perfil())
    _, usuario = cliente.llamadas[0]
    assert "analisis de datos" in usuario


def test_un_cv_larguisimo_se_recorta_antes_de_enviarlo():
    cliente = ClienteFalso(_respuesta())
    analizar_cv(cliente, "x" * 50000, Perfil())
    _, usuario = cliente.llamadas[0]
    assert len(usuario) < 50000


# --------------------------------------------------------------------------
# Skills personales e idiomas
#
# Caso real que motivó esto: un CV con una sección "PERSONAL" (Problem-
# solving, Team player...) además de "SKILLS" técnicas — el importador no
# tenía dónde meter lo primero y todo acababa en skills técnicas.
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
    resultado = analizar_cv(ClienteFalso(respuesta), "texto", Perfil())

    assert len(resultado.skills_personales) == 1
    assert resultado.skills_personales[0].nombre["es"] == "Trabajo en equipo"
    assert len(resultado.idiomas) == 1
    assert resultado.idiomas[0].nombre["es"] == "Inglés"
    assert resultado.idiomas[0].nivel["es"] == "C1 Avanzado"
    # Nunca se cuelan entre las skills técnicas.
    assert all(s.nombre["es"] != "Trabajo en equipo" for s in resultado.skills)
    assert all(s.nombre["es"] != "Inglés" for s in resultado.skills)


def test_una_skill_personal_sin_nombre_se_descarta():
    respuesta = _respuesta(
        skills_personales=[{"nombre": {"es": "", "en": ""}, "keywords": []}]
    )
    resultado = analizar_cv(ClienteFalso(respuesta), "texto", Perfil())
    assert resultado.skills_personales == []


def test_un_idioma_sin_nombre_se_descarta():
    respuesta = _respuesta(
        idiomas=[{"nombre": {"es": "", "en": ""}, "nivel": {"es": "B2", "en": "B2"}, "keywords": []}]
    )
    resultado = analizar_cv(ClienteFalso(respuesta), "texto", Perfil())
    assert resultado.idiomas == []


def test_el_id_de_una_skill_personal_no_choca_con_una_tecnica_del_perfil():
    perfil = Perfil(skills=[Skill(id="python", nombre=Bilingue(es="Python", en="Python"))])
    respuesta = _respuesta(
        skills_personales=[
            {"nombre": {"es": "Python", "en": "Python"}, "keywords": []}
        ]
    )
    # Coincidencia de nombre deliberadamente rara, solo para comprobar que
    # el id provisional se genera bien aunque el nombre choque con otra
    # categoría — no debería fallar ni mezclarse.
    resultado = analizar_cv(ClienteFalso(respuesta), "texto", perfil)
    assert len(resultado.skills_personales) == 1


def test_un_idioma_que_ya_esta_en_el_perfil_no_se_vuelve_a_proponer():
    """Aunque el nivel detectado sea distinto (B2 en el perfil, C1 en el CV
    nuevo): el dedup es por nombre, no por nivel — actualizar el nivel es
    cosa de editar el idioma a mano, no de que se cuele un duplicado."""
    perfil = Perfil(
        idiomas=[
            IdiomaHablado(
                id="ingles",
                nombre=Bilingue(es="Inglés", en="English"),
                nivel=Bilingue(es="B2", en="B2"),
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
    resultado = analizar_cv(ClienteFalso(respuesta), "texto", perfil)
    assert resultado.idiomas == []


def test_sin_skills_personales_ni_idiomas_en_la_respuesta_no_revienta():
    """La mayoría de CVs no tendrán ninguna de las dos categorías: ausentes
    del JSON, no es un error."""
    resultado = analizar_cv(ClienteFalso(_respuesta()), "texto", Perfil())
    assert resultado.skills_personales == []
    assert resultado.idiomas == []


def test_el_aviso_de_nada_encontrado_tiene_en_cuenta_las_cuatro_categorias():
    """Antes solo miraba experiencias y skills: si un CV solo tuviera un
    idioma reconocible, no debería avisar de que no se encontró nada."""
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
    resultado = analizar_cv(ClienteFalso(respuesta), "texto", Perfil())
    assert resultado.avisos == []
    assert len(resultado.idiomas) == 1
