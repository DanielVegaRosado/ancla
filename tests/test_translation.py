"""Tests for translating profile entries into the language they are missing.

Same approach as `test_importer.py`: a fake AI client, no network. What is
checked is not that the translation reads well — that is the model's job and
the user's judgement — but the three guarantees this module has to hold no
matter what comes back: the language the user wrote is never touched, an
empty field stays empty, and one batch is one call.
"""
from __future__ import annotations

import json

from ancla.profile import translation
from ancla.profile.model import (
    AboutMe,
    Bilingual,
    Education,
    Experience,
    Skill,
    SpokenLanguage,
)


class ClienteFalso:
    def __init__(self, respuesta: str | Exception = "{}", available: bool = True):
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


def _experiencia(**cambios) -> Experience:
    base = dict(
        id="ml-dev",
        title=Bilingual(es="Desarrollador de ML", en=""),
        period_start="2026", period_end="",
        bullets=Bilingual(es=["Pipeline completo"], en=[]),
        stack="Python",
        keywords=["ml"],
    )
    return Experience(**{**base, **cambios})


def _skill(**cambios) -> Skill:
    base = dict(
        id="python", name=Bilingual(es="Python", en=""), category="lenguaje", keywords=["py"]
    )
    return Skill(**{**base, **cambios})


def test_rellena_el_idioma_que_falta():
    cliente = ClienteFalso(json.dumps({"0": {"name": "Python"}}))

    resultado = translation.translate(cliente, [_skill()], "en")

    assert resultado.entries[0].name["en"] == "Python"
    assert resultado.avisos == []


def test_no_toca_el_idioma_original():
    """The one deliberate exception to "never rewrite the user" is filling
    the empty side, and it is enforced here rather than asked of the model:
    even an answer that rewrites the Spanish cannot reach the profile."""
    cliente = ClienteFalso(
        json.dumps({"0": {"title": "ML Developer", "bullets": ["Full pipeline"]}})
    )

    resultado = translation.translate(cliente, [_experiencia()], "en")

    assert resultado.entries[0].title["es"] == "Desarrollador de ML"
    assert resultado.entries[0].bullets["es"] == ["Pipeline completo"]
    assert resultado.entries[0].title["en"] == "ML Developer"


def test_un_campo_vacio_sigue_vacio():
    """Nothing is invented to fill a gap the original does not have."""
    sin_nivel = SpokenLanguage(
        id="ingles", name=Bilingual(es="Inglés", en=""), level=Bilingual(es="", en=""),
        keywords=["english"],
    )
    cliente = ClienteFalso(json.dumps({"0": {"name": "English", "level": "C1 Advanced"}}))

    resultado = translation.translate(cliente, [sin_nivel], "en")

    assert resultado.entries[0].level["en"] == ""
    assert resultado.entries[0].name["en"] == "English"


def test_todo_el_lote_en_una_sola_llamada():
    """Twelve entries one by one would be twelve waits on the per-minute
    quota, which is the whole reason the batch exists."""
    cliente = ClienteFalso(
        json.dumps({str(i): {"name": f"Skill {i}"} for i in range(5)})
    )

    translation.translate(cliente, [_skill(id=f"s{i}") for i in range(5)], "en")

    assert len(cliente.llamadas) == 1


def test_no_llama_si_no_falta_nada():
    completa = _skill(name=Bilingual(es="Python", en="Python"))
    cliente = ClienteFalso()

    resultado = translation.translate(cliente, [completa], "en")

    assert cliente.llamadas == []
    assert resultado.entries == [completa]


def test_un_fallo_del_proveedor_devuelve_las_entradas_intactas():
    entradas = [_skill()]
    cliente = ClienteFalso(RuntimeError("sin cuota"))

    resultado = translation.translate(cliente, entradas, "en")

    assert resultado.entries == entradas
    assert resultado.avisos


def test_una_respuesta_ilegible_no_rompe_nada():
    resultado = translation.translate(ClienteFalso("lo siento, no puedo"), [_skill()], "en")

    assert resultado.entries[0].name["en"] == ""
    assert resultado.avisos


def test_una_lista_devuelta_como_texto_se_descarta():
    """A bullet list that comes back as a single string would silently
    change the entry's shape, so it is dropped instead."""
    cliente = ClienteFalso(json.dumps({"0": {"title": "ML Developer", "bullets": "Full pipeline"}}))

    resultado = translation.translate(cliente, [_experiencia()], "en")

    assert resultado.entries[0].bullets["en"] == []
    assert resultado.entries[0].title["en"] == "ML Developer"


def test_pendientes_nombra_lo_que_saldria_en_blanco():
    entradas = [_skill(), _skill(id="sql", name=Bilingual(es="SQL", en="SQL"))]

    pendientes = translation.pending(entradas, "en")

    assert [entrada.id for entrada in pendientes] == ["python"]
    assert translation.pending(entradas, "es") == []


def test_una_educacion_solo_en_ingles_se_traduce_al_espanol():
    educacion = Education(
        id="bsc",
        title=Bilingual(es="", en="BSc in Computer Engineering"),
        institution="UEMC", period_start="2023", period_end="2027",
    )
    cliente = ClienteFalso(json.dumps({"0": {"title": "Grado en Ingeniería Informática"}}))

    resultado = translation.translate(cliente, [educacion], "es")

    assert resultado.entries[0].title["es"] == "Grado en Ingeniería Informática"
    assert resultado.entries[0].title["en"] == "BSc in Computer Engineering"


# --------------------------------------------------------------------------
# El «Sobre mí»
# --------------------------------------------------------------------------


def _sobre_mi(es: str, en: str = "") -> AboutMe:
    return AboutMe(template=Bilingual(es=es, en=en))


def test_el_sobre_mi_se_traduce_conservando_sus_huecos():
    original = _sobre_mi("Desarrollador de {GROUP_A_1} con {GROUP_B_1}.")
    respuesta = json.dumps({"0": {"template": "{GROUP_A_1} developer working with {GROUP_B_1}."}})

    resultado = translation.translate(ClienteFalso(respuesta), [original], "en")

    assert resultado.entries[0].template["en"] == "{GROUP_A_1} developer working with {GROUP_B_1}."
    assert resultado.entries[0].template["es"] == original.template["es"]


def test_una_traduccion_que_pierde_un_hueco_se_descarta():
    """Un hueco perdido deja ese idioma renderizando mal, y nada río abajo
    puede detectarlo: mejor sin traducir que traducido y roto."""
    original = _sobre_mi("Desarrollador de {GROUP_A_1} con {GROUP_B_1}.")
    respuesta = json.dumps({"0": {"template": "Developer working with {GROUP_B_1}."}})

    resultado = translation.translate(ClienteFalso(respuesta), [original], "en")

    assert resultado.entries[0].template["en"] == ""
    assert resultado.avisos
