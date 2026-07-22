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
from cv_adaptativo.perfil.modelo import Bilingue, Perfil, Skill


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
    perfil = Perfil(skills=[Skill(id="python", nombre=Bilingue(es="Python", en="Python"))])
    cliente = ClienteFalso(_respuesta())
    resultado = analizar_cv(cliente, "texto", perfil)
    assert resultado.skills[0].id != "python"
    assert resultado.skills[0].id.startswith("python")


def test_dos_candidatas_del_mismo_lote_tampoco_chocan_entre_si():
    respuesta = _respuesta(
        skills=[
            {"nombre": {"es": "Python", "en": "Python"}, "categoria": "", "keywords": []},
            {"nombre": {"es": "Python", "en": "Python"}, "categoria": "", "keywords": []},
        ]
    )
    resultado = analizar_cv(ClienteFalso(respuesta), "texto", Perfil())
    ids = [skill.id for skill in resultado.skills]
    assert len(ids) == len(set(ids))


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
