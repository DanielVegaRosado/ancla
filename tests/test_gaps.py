"""Tests para la propuesta de huecos del «Sobre mí».

Lo que se comprueba aquí no es que el modelo acierte —eso es cosa suya— sino
las dos garantías que sostienen la regla de no reescribir al usuario: que el
texto solo puede cambiar sustituyendo un fragmento que estaba **literal** en
lo que él escribió, y que el mismo hueco cae en el mismo sitio semántico en
español y en inglés, porque los dos se rellenan con la misma skill.
"""
from __future__ import annotations

import json

from ancla.ai.client import AIError
from ancla.profile import gaps
from ancla.profile.model import AboutMe, Bilingual, Skill

SOBRE_MI_ES = (
    "Desarrollador centrado en aprendizaje automático y en backend, "
    "con experiencia en análisis de datos usando Python, Docker y PostgreSQL."
)
SOBRE_MI_EN = (
    "Developer focused on machine learning and backend, "
    "with experience in data analysis using Python, Docker and PostgreSQL."
)


class ClienteFalso:
    def __init__(self, respuesta: str = "{}", available: bool = True, error: Exception | None = None):
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


def _sobre_mi(es: str = SOBRE_MI_ES, en: str = SOBRE_MI_EN) -> AboutMe:
    return AboutMe(template=Bilingual(es=es, en=en))


def _respuesta_completa() -> str:
    return json.dumps(
        {
            "GROUP_A_1": {"es": "aprendizaje automático", "en": "machine learning"},
            "GROUP_A_2": {"es": "backend", "en": "backend"},
            "GROUP_A_3": {"es": "análisis de datos", "en": "data analysis"},
            "GROUP_B_1": {"es": "Python", "en": "Python"},
            "GROUP_B_2": {"es": "Docker", "en": "Docker"},
            "GROUP_B_3": {"es": "PostgreSQL", "en": "PostgreSQL"},
        }
    )


# --------------------------------------------------------------------------
# La sustitución literal
# --------------------------------------------------------------------------


def test_los_seis_huecos_quedan_en_el_mismo_sitio_en_los_dos_idiomas():
    """`AboutMe.render` rellena `{GROUP_A_1}` con la misma skill en español y
    en inglés, así que si los huecos no marcan la misma idea el CV en inglés
    queda hablando de otra cosa."""
    propuesta = gaps.suggest_gaps(ClienteFalso(_respuesta_completa()), _sobre_mi(), [])

    assert propuesta.avisos == []
    assert propuesta.about_me.template["es"] == (
        "Desarrollador centrado en {GROUP_A_1} y en {GROUP_A_2}, "
        "con experiencia en {GROUP_A_3} usando {GROUP_B_1}, {GROUP_B_2} y {GROUP_B_3}."
    )
    assert propuesta.about_me.template["en"] == (
        "Developer focused on {GROUP_A_1} and {GROUP_A_2}, "
        "with experience in {GROUP_A_3} using {GROUP_B_1}, {GROUP_B_2} and {GROUP_B_3}."
    )


def test_un_fragmento_que_no_esta_literal_se_descarta_y_se_avisa():
    """La garantía de la regla 2: el modelo no puede meter texto propio, solo
    señalar trozos del texto del usuario. Un fragmento reescrito («machine
    learning» donde el usuario puso «aprendizaje automático») no encuentra
    dónde encajar, así que no toca nada."""
    respuesta = json.loads(_respuesta_completa())
    respuesta["GROUP_A_1"]["es"] = "machine learning aplicado"
    propuesta = gaps.suggest_gaps(ClienteFalso(json.dumps(respuesta)), _sobre_mi(), [])

    texto_es = propuesta.about_me.template["es"]
    assert "aprendizaje automático" in texto_es
    assert "{GROUP_A_1}" not in texto_es
    assert "machine learning aplicado" not in texto_es
    assert len(propuesta.avisos) == 1
    assert "GROUP_A_1" in propuesta.avisos[0]
    # El resto sí se coloca: descartar los cinco buenos por uno malo dejaría
    # al usuario en el mismo muro que esta pantalla existe para quitar.
    assert "{GROUP_B_3}" in texto_es
    assert "{GROUP_A_1}" in propuesta.about_me.template["en"]


def test_un_fragmento_solo_se_sustituye_una_vez():
    texto, sin_colocar = gaps.place("Python y más Python", {"{GROUP_B_1}": "Python"})

    assert texto == "{GROUP_B_1} y más Python"
    assert sin_colocar == []


def test_dos_huecos_que_se_pelean_por_el_mismo_trozo_no_se_solapan():
    texto, sin_colocar = gaps.place(
        "trabajo con Python", {"{GROUP_B_1}": "Python", "{GROUP_B_2}": "Python"}
    )

    assert texto == "trabajo con {GROUP_B_1}"
    assert sin_colocar == ["{GROUP_B_2}"]


def test_un_hueco_ya_escrito_a_mano_no_se_mueve():
    """Marcar a mano y proponer con IA editan el mismo campo: lo que el
    usuario ya decidió manda sobre lo que proponga el modelo."""
    texto, sin_colocar = gaps.place(
        "trabajo con {GROUP_B_1} y Docker", {"{GROUP_B_1}": "Docker"}
    )

    assert texto == "trabajo con {GROUP_B_1} y Docker"
    assert sin_colocar == []


# --------------------------------------------------------------------------
# Qué llega al modelo
# --------------------------------------------------------------------------


def test_al_modelo_le_llegan_los_dos_idiomas_en_una_sola_llamada():
    """Una llamada por idioma costaría el doble y, sobre todo, dejaría de
    garantizar que un hueco marque la misma idea en los dos."""
    cliente = ClienteFalso(_respuesta_completa())
    gaps.suggest_gaps(cliente, _sobre_mi(), [])

    assert len(cliente.peticiones) == 1
    assert SOBRE_MI_ES in cliente.peticiones[0]
    assert SOBRE_MI_EN in cliente.peticiones[0]


def test_al_modelo_le_llegan_los_nombres_de_las_skills_tecnicas():
    cliente = ClienteFalso(_respuesta_completa())
    skills = [Skill(id="python", name=Bilingual(es="Python", en="Python"))]
    gaps.suggest_gaps(cliente, _sobre_mi(), skills)

    assert "Python" in cliente.peticiones[0]


# --------------------------------------------------------------------------
# Nada de esto puede romper la pantalla
# --------------------------------------------------------------------------


def test_sin_clave_no_llama_y_devuelve_el_texto_intacto():
    cliente = ClienteFalso(available=False)
    propuesta = gaps.suggest_gaps(cliente, _sobre_mi(), [])

    assert cliente.peticiones == []
    assert propuesta.about_me.template["es"] == SOBRE_MI_ES
    assert "Ajustes" in propuesta.avisos[0]


def test_un_fallo_del_proveedor_devuelve_el_texto_intacto_y_su_motivo():
    error = AIError("Tu clave de Groq no es válida o ha caducado.")
    propuesta = gaps.suggest_gaps(ClienteFalso(error=error), _sobre_mi(), [])

    assert propuesta.about_me.template["en"] == SOBRE_MI_EN
    assert str(error) in propuesta.avisos[0]


def test_una_respuesta_ilegible_no_revienta():
    propuesta = gaps.suggest_gaps(ClienteFalso("lo siento, no puedo"), _sobre_mi(), [])

    assert propuesta.about_me.template["es"] == SOBRE_MI_ES
    assert propuesta.avisos


def test_una_respuesta_con_huecos_inventados_los_ignora():
    respuesta = json.dumps({"GROUP_C_1": {"es": "Python", "en": "Python"}})
    propuesta = gaps.suggest_gaps(ClienteFalso(respuesta), _sobre_mi(), [])

    assert "{GROUP_C_1}" not in propuesta.about_me.template["es"]
    assert propuesta.about_me.template["es"] == SOBRE_MI_ES


class _ClienteConPresupuesto(ClienteFalso):
    """Like a provider that understands `ai.client.complete_with_budget`'s
    hint, unlike the plain `ClienteFalso` above."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_tokens_recibido: int | None = None

    def complete(self, sistema: str, usuario: str, max_tokens: int | None = None) -> str:
        self.max_tokens_recibido = max_tokens
        return super().complete(sistema, usuario)


def test_declara_su_propio_presupuesto_a_un_cliente_que_lo_entiende():
    """This module's response never grows with the length of the "About me"
    text or the skill catalog (see `RESERVED_TOKENS`), so the number handed
    to a budget-aware client has to be the fixed constant, not something
    derived from either input."""
    cliente = _ClienteConPresupuesto(_respuesta_completa())
    gaps.suggest_gaps(cliente, _sobre_mi(), [])

    assert cliente.max_tokens_recibido == gaps.RESERVED_TOKENS


def test_un_cliente_que_no_entiende_el_presupuesto_se_llama_igual():
    """`ClienteFalso.complete` only accepts `(sistema, usuario)` — the same
    shape as Anthropic's and the generic OpenAI-compatible client. The call
    must still go through."""
    cliente = ClienteFalso(_respuesta_completa())
    propuesta = gaps.suggest_gaps(cliente, _sobre_mi(), [])

    assert propuesta.about_me.template["es"] != SOBRE_MI_ES
