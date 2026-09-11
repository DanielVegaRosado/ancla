"""Tests for splitting a paragraph of experience into bullets.

What is checked here is not whether the model cuts well — that is its own
concern — but the guarantee behind the rule against rewriting the user: the
text can only change by being cut at fragments that were **literally** in
what they wrote, and a split that does not add up is dropped whole instead
of losing the piece between two cut points.
"""
from __future__ import annotations

import json

from ancla.ai.client import AIError
from ancla.profile import bullets

PARRAFO = (
    "Diseñé el pipeline de datos que alimenta el modelo de riesgo, procesando "
    "cuatro millones de registros diarios. Automaticé el despliegue con Docker y "
    "GitHub Actions, reduciendo a la mitad el tiempo de publicación. Formé a dos "
    "compañeros nuevos en el stack de datos del equipo."
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


def _respuesta(*fragmentos: str) -> str:
    return json.dumps({"fragmentos": list(fragmentos)})


# --------------------------------------------------------------------------
# split_at: all-or-nothing, and never a character of its own
# --------------------------------------------------------------------------


def test_corta_el_texto_en_los_fragmentos_senalados():
    trozos = bullets.split_at(PARRAFO, ["Diseñé el pipeline", "Automaticé el despliegue", "Formé a dos"])
    assert len(trozos) == 3
    assert trozos[0].startswith("Diseñé el pipeline")
    assert trozos[1].startswith("Automaticé el despliegue")
    assert trozos[2] == "Formé a dos compañeros nuevos en el stack de datos del equipo."


def test_los_bullets_juntos_son_el_texto_del_usuario():
    trozos = bullets.split_at(PARRAFO, ["Diseñé el pipeline", "Automaticé el despliegue"])
    assert " ".join(trozos) == PARRAFO


def test_un_solo_fragmento_devuelve_el_texto_entero():
    assert bullets.split_at(PARRAFO, ["Diseñé el pipeline"]) == [PARRAFO]


def test_el_texto_anterior_al_primer_corte_no_se_pierde():
    trozos = bullets.split_at(PARRAFO, ["Automaticé el despliegue"])
    assert trozos == [PARRAFO]


def test_un_fragmento_que_no_esta_en_el_texto_descarta_la_division_entera():
    assert bullets.split_at(
        PARRAFO,
        ["Diseñé el pipeline", "Lideré la migración a Kubernetes", "Formé a dos"],
    ) is None


def test_fragmentos_fuera_de_orden_descartan_la_division_entera():
    assert bullets.split_at(PARRAFO, ["Formé a dos", "Automaticé el despliegue"]) is None


def test_tolera_el_salto_de_linea_que_el_modelo_se_come_al_copiar():
    texto = "Diseñé el pipeline de\ndatos del equipo. Automaticé el despliegue con Docker."
    trozos = bullets.split_at(texto, ["Diseñé el pipeline de datos", "Automaticé el despliegue"])
    assert trozos is not None and len(trozos) == 2


def test_no_tolera_un_cambio_de_mayusculas_ni_de_tildes():
    assert bullets.split_at(PARRAFO, ["Disene el pipeline"]) is None


# --------------------------------------------------------------------------
# looks_unsplit: which texts are worth a call
# --------------------------------------------------------------------------


def test_un_parrafo_largo_con_varias_frases_parece_sin_dividir():
    assert bullets.looks_unsplit([PARRAFO])


def test_varios_bullets_ya_escritos_no_se_tocan():
    assert not bullets.looks_unsplit([PARRAFO, "Otro bullet."])


def test_un_bullet_corto_no_parece_un_parrafo():
    assert not bullets.looks_unsplit(["Automaticé el despliegue con Docker."])


def test_una_sola_frase_larga_no_parece_un_parrafo():
    assert not bullets.looks_unsplit([
        "Diseñé y mantuve el pipeline de datos que alimenta el modelo de riesgo del "
        "equipo de crédito procesando cuatro millones de registros diarios sin "
        "interrupciones durante los dos años que duró el proyecto"
    ])


# --------------------------------------------------------------------------
# suggest_split: never raises, never rewrites
# --------------------------------------------------------------------------


def test_divide_el_parrafo_con_lo_que_propone_el_modelo():
    cliente = ClienteFalso(_respuesta("Diseñé el pipeline", "Automaticé el despliegue", "Formé a dos"))
    propuesta = bullets.suggest_split(cliente, PARRAFO)
    assert len(propuesta.bullets) == 3
    assert propuesta.avisos == []


def test_un_parrafo_que_no_se_divide_vuelve_entero_y_sin_avisos():
    cliente = ClienteFalso(_respuesta("Diseñé el pipeline"))
    propuesta = bullets.suggest_split(cliente, PARRAFO)
    assert propuesta.bullets == [PARRAFO]
    assert propuesta.avisos == []


def test_un_fragmento_no_localizado_deja_el_texto_entero_y_avisa():
    cliente = ClienteFalso(_respuesta("Diseñé el pipeline", "Lideré la migración", "Formé a dos"))
    propuesta = bullets.suggest_split(cliente, PARRAFO)
    assert propuesta.bullets == [PARRAFO]
    assert propuesta.avisos


def test_el_texto_reescrito_por_el_modelo_no_llega_al_resultado():
    cliente = ClienteFalso(_respuesta("Lideré el diseño de un pipeline de datos de última generación"))
    propuesta = bullets.suggest_split(cliente, PARRAFO)
    assert propuesta.bullets == [PARRAFO]


def test_una_respuesta_ilegible_deja_el_texto_entero_y_avisa():
    propuesta = bullets.suggest_split(ClienteFalso("lo siento, no puedo"), PARRAFO)
    assert propuesta.bullets == [PARRAFO]
    assert propuesta.avisos


def test_un_fallo_del_proveedor_no_revienta_el_formulario():
    cliente = ClienteFalso(error=AIError("tu clave de Groq no es válida"))
    propuesta = bullets.suggest_split(cliente, PARRAFO)
    assert propuesta.bullets == [PARRAFO]
    assert "Groq" in propuesta.avisos[0]


def test_sin_clave_configurada_no_se_llama_al_proveedor():
    cliente = ClienteFalso(available=False)
    propuesta = bullets.suggest_split(cliente, PARRAFO)
    assert propuesta.bullets == [PARRAFO]
    assert cliente.peticiones == []
    assert propuesta.avisos


def test_un_texto_vacio_no_gasta_una_llamada():
    cliente = ClienteFalso()
    assert bullets.suggest_split(cliente, "   ").bullets == []
    assert cliente.peticiones == []


def test_un_texto_desmesurado_no_se_manda_recortado():
    cliente = ClienteFalso()
    texto = "x" * (bullets.MAX_CARACTERES_TEXTO + 1)
    propuesta = bullets.suggest_split(cliente, texto)
    assert propuesta.bullets == [texto]
    assert cliente.peticiones == []
    assert propuesta.avisos
