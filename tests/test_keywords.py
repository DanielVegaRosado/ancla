"""Tests for keyword suggestions.

What matters here isn't that it gets it right —that's up to the model—
but two things: that it **never breaks the form** (any failure turns into
an empty `Suggestion`, never an exception), and that **the reason for the
failure reaches the user** instead of getting lost in a generic "couldn't
do it". Without this, a user with the wrong key has no way of knowing
what to check.
"""
from __future__ import annotations

from ancla.ai.client import AIError
from ancla.profile import keywords


class ClienteFalso:
    def __init__(self, respuesta: str = "[]", available: bool = True, error: Exception | None = None):
        self.respuesta = respuesta
        self._disponible = available
        self.error = error
        self.peticiones: list[str] = []

    def available(self) -> bool:
        return self._disponible

    def complete(self, sistema: str, usuario: str) -> str:
        self.peticiones.append(usuario)
        if self.error:
            raise self.error
        return self.respuesta


def test_propone_keywords_de_una_skill():
    cliente = ClienteFalso('["python", "scripting", "backend"]')
    sugerencia = keywords.suggest_for_skill(cliente, "Python", "Python", "lenguaje")
    assert sugerencia.keywords == ["python", "scripting", "backend"]
    assert sugerencia.motivo == ""


def test_el_modelo_recibe_nombre_y_categoria():
    cliente = ClienteFalso('["a"]')
    keywords.suggest_for_skill(cliente, "SQL", "SQL", "dato")
    assert "SQL" in cliente.peticiones[0] and "dato" in cliente.peticiones[0]


def test_una_experiencia_se_describe_con_titulo_stack_y_bullets():
    cliente = ClienteFalso('["ml"]')
    keywords.suggest_for_experience(
        cliente, "ML Developer", ["Optimicé hiperparámetros"], "Python · Optuna"
    )
    peticion = cliente.peticiones[0]
    assert "ML Developer" in peticion
    assert "Optuna" in peticion
    assert "Optimicé hiperparámetros" in peticion


def test_sin_clave_no_llama_y_explica_que_falta_configurarla():
    cliente = ClienteFalso(available=False)
    sugerencia = keywords.suggest_for_skill(cliente, "Python", "Python")
    assert sugerencia.keywords == []
    assert "Ajustes" in sugerencia.motivo
    assert cliente.peticiones == []


def test_una_clave_invalida_no_revienta_el_formulario_y_dice_por_que():
    """El caso real que motivó esto: una clave de xAI (Grok) usada contra Groq
    devolvía «no se pudo» sin más, y el usuario no tenía forma de saber que el
    problema era la clave. El motivo de `ErrorIA` ya viene pensado para
    enseñarse tal cual, así que se propaga en vez de sustituirlo."""
    error = AIError("Tu clave de Groq no es válida o ha caducado. Revísala en Ajustes.")
    sugerencia = keywords.suggest_for_skill(ClienteFalso(error=error), "Python", "Python")
    assert sugerencia.keywords == []
    assert sugerencia.motivo == str(error)


def test_un_fallo_inesperado_del_proveedor_tambien_se_traduce_sin_reventar():
    sugerencia = keywords.suggest_for_skill(
        ClienteFalso(error=RuntimeError("boom")), "Python", "Python"
    )
    assert sugerencia.keywords == []
    assert sugerencia.motivo != ""


def test_una_respuesta_ilegible_se_explica_como_tal():
    sugerencia = keywords.suggest_for_skill(ClienteFalso("lo siento, no puedo"), "Py", "Py")
    assert sugerencia.keywords == []
    assert sugerencia.motivo != ""


def test_quita_duplicados_ignorando_acentos_y_mayusculas():
    cliente = ClienteFalso('["Automatización", "automatizacion", "AUTOMATIZACIÓN", "otra"]')
    assert keywords.suggest_for_skill(cliente, "Python", "Python").keywords == [
        "automatización",
        "otra",
    ]


def test_descarta_lo_que_no_son_cadenas_y_lo_larguisimo():
    cliente = ClienteFalso(f'["buena", 42, null, "{"x" * 60}"]')
    assert keywords.suggest_for_skill(cliente, "Python", "Python").keywords == ["buena"]


def test_hay_un_tope_de_sugerencias():
    cliente = ClienteFalso(str([f"k{n}" for n in range(50)]).replace("'", '"'))
    sugerencia = keywords.suggest_for_skill(cliente, "Python", "Python")
    assert len(sugerencia.keywords) == keywords.MAX_SUGERENCIAS


def test_sin_nombre_no_se_gasta_una_llamada():
    cliente = ClienteFalso('["a"]')
    assert keywords.suggest_for_skill(cliente, "  ", "").keywords == []
    assert cliente.peticiones == []
