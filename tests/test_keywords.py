"""Tests de la sugerencia de keywords.

Lo importante aquí no es que acierte —eso lo decide el modelo— sino que
**nunca rompa el formulario**: cualquier fallo tiene que salir como "no hay
sugerencias", no como una excepción que tira la pantalla donde el usuario
estaba escribiendo.
"""
from __future__ import annotations

from cv_adaptativo.ia.cliente import ErrorIA
from cv_adaptativo.perfil import keywords


class ClienteFalso:
    def __init__(self, respuesta: str = "[]", disponible: bool = True, falla: bool = False):
        self.respuesta = respuesta
        self._disponible = disponible
        self.falla = falla
        self.peticiones: list[str] = []

    def disponible(self) -> bool:
        return self._disponible

    def completar(self, sistema: str, usuario: str) -> str:
        self.peticiones.append(usuario)
        if self.falla:
            raise ErrorIA("clave inválida")
        return self.respuesta


def test_propone_keywords_de_una_skill():
    cliente = ClienteFalso('["python", "scripting", "backend"]')
    assert keywords.sugerir_para_skill(cliente, "Python", "Python", "lenguaje") == [
        "python",
        "scripting",
        "backend",
    ]


def test_el_modelo_recibe_nombre_y_categoria():
    cliente = ClienteFalso('["a"]')
    keywords.sugerir_para_skill(cliente, "SQL", "SQL", "dato")
    assert "SQL" in cliente.peticiones[0] and "dato" in cliente.peticiones[0]


def test_una_experiencia_se_describe_con_titulo_stack_y_bullets():
    cliente = ClienteFalso('["ml"]')
    keywords.sugerir_para_experiencia(
        cliente, "ML Developer", ["Optimicé hiperparámetros"], "Python · Optuna"
    )
    peticion = cliente.peticiones[0]
    assert "ML Developer" in peticion
    assert "Optuna" in peticion
    assert "Optimicé hiperparámetros" in peticion


def test_sin_clave_no_llama_y_devuelve_vacio():
    cliente = ClienteFalso(disponible=False)
    assert keywords.sugerir_para_skill(cliente, "Python", "Python") == []
    assert cliente.peticiones == []


def test_un_fallo_del_proveedor_no_revienta_el_formulario():
    """Sugerir keywords es una ayuda; una ayuda que rompe la pantalla no lo es."""
    assert keywords.sugerir_para_skill(ClienteFalso(falla=True), "Python", "Python") == []


def test_una_respuesta_ilegible_devuelve_vacio():
    assert keywords.sugerir_para_skill(ClienteFalso("lo siento, no puedo"), "Py", "Py") == []


def test_quita_duplicados_ignorando_acentos_y_mayusculas():
    cliente = ClienteFalso('["Automatización", "automatizacion", "AUTOMATIZACIÓN", "otra"]')
    assert keywords.sugerir_para_skill(cliente, "Python", "Python") == [
        "automatización",
        "otra",
    ]


def test_descarta_lo_que_no_son_cadenas_y_lo_larguisimo():
    cliente = ClienteFalso(f'["buena", 42, null, "{"x" * 60}"]')
    assert keywords.sugerir_para_skill(cliente, "Python", "Python") == ["buena"]


def test_hay_un_tope_de_sugerencias():
    cliente = ClienteFalso(str([f"k{n}" for n in range(50)]).replace("'", '"'))
    assert len(keywords.sugerir_para_skill(cliente, "Python", "Python")) == (
        keywords.MAX_SUGERENCIAS
    )


def test_sin_nombre_no_se_gasta_una_llamada():
    cliente = ClienteFalso('["a"]')
    assert keywords.sugerir_para_skill(cliente, "  ", "") == []
    assert cliente.peticiones == []
