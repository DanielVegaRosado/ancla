"""Tests for the "About me" gap-suggestion feature.

What's checked here isn't whether the model gets it right — that's its own
concern — but the two guarantees that back the rule against rewriting the
user: the text can only change by substituting a fragment that was
**literally** present in what they wrote, and the same gap lands on the same
semantic spot in Spanish and English, since both are filled with the same
skill.
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
    texto = Bilingual(es=es, en=en)
    return AboutMe(template=texto, plain_text=texto)


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
# Literal substitution
# --------------------------------------------------------------------------


def test_los_seis_huecos_quedan_en_el_mismo_sitio_en_los_dos_idiomas():
    """`AboutMe.render` fills `{GROUP_A_1}` with the same skill in Spanish and
    English, so if the gaps don't mark the same idea, the English CV ends up
    talking about something else."""
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


def test_un_idioma_sin_escribir_no_avisa_de_huecos_sin_colocar():
    """An empty language has nowhere to place a fragment — that's not the
    same as the model failing on real text, so it doesn't warn."""
    propuesta = gaps.suggest_gaps(
        ClienteFalso(_respuesta_un_idioma()), _sobre_mi(en=""), []
    )

    assert propuesta.avisos == []
    assert propuesta.about_me.template["en"] == ""
    assert "{GROUP_A_1}" in propuesta.about_me.template["es"]


def _respuesta_un_idioma() -> str:
    """As the model would return it when only one language is requested: a
    single fragment per gap, not the `{"es": ..., "en": ...}` pair."""
    return json.dumps(
        {
            "GROUP_A_1": "aprendizaje automático",
            "GROUP_A_2": "backend",
            "GROUP_A_3": "análisis de datos",
            "GROUP_B_1": "Python",
            "GROUP_B_2": "Docker",
            "GROUP_B_3": "PostgreSQL",
        }
    )


def test_solo_espanol_coloca_los_huecos_en_espanol_y_deja_el_ingles_vacio():
    propuesta = gaps.suggest_gaps(
        ClienteFalso(_respuesta_un_idioma()), _sobre_mi(en=""), []
    )

    assert propuesta.avisos == []
    assert propuesta.about_me.template["en"] == ""
    assert propuesta.about_me.template["es"] == (
        "Desarrollador centrado en {GROUP_A_1} y en {GROUP_A_2}, "
        "con experiencia en {GROUP_A_3} usando {GROUP_B_1}, {GROUP_B_2} y {GROUP_B_3}."
    )


def test_solo_ingles_coloca_los_huecos_en_ingles_y_deja_el_espanol_vacio():
    respuesta = json.dumps(
        {
            "GROUP_A_1": "machine learning",
            "GROUP_A_2": "backend",
            "GROUP_A_3": "data analysis",
            "GROUP_B_1": "Python",
            "GROUP_B_2": "Docker",
            "GROUP_B_3": "PostgreSQL",
        }
    )
    propuesta = gaps.suggest_gaps(ClienteFalso(respuesta), _sobre_mi(es=""), [])

    assert propuesta.avisos == []
    assert propuesta.about_me.template["es"] == ""
    assert propuesta.about_me.template["en"] == (
        "Developer focused on {GROUP_A_1} and {GROUP_A_2}, "
        "with experience in {GROUP_A_3} using {GROUP_B_1}, {GROUP_B_2} and {GROUP_B_3}."
    )


def test_un_solo_idioma_no_envia_el_texto_del_idioma_vacio_ni_la_regla_de_pareja():
    cliente = ClienteFalso(_respuesta_un_idioma())
    gaps.suggest_gaps(cliente, _sobre_mi(en=""), [])

    peticion = cliente.peticiones[0]
    assert SOBRE_MI_ES in peticion
    assert "Sobre mí (EN)" not in peticion

    sistema = gaps._system_prompt(("es",), _sobre_mi(en="").gaps())
    assert "en español y en inglés" not in sistema
    assert "MISMA idea" not in sistema
    assert '"es": ""' not in sistema
    assert '"GROUP_A_1": ""' in sistema


def test_con_los_dos_idiomas_la_peticion_y_el_esquema_no_cambian():
    """Bilingual behavior stays untouched: same request, same pairing rule,
    same JSON schema with `{"es": ..., "en": ...}` per gap."""
    cliente = ClienteFalso(_respuesta_completa())
    gaps.suggest_gaps(cliente, _sobre_mi(), [])

    peticion = cliente.peticiones[0]
    assert "Sobre mí (ES)" in peticion
    assert "Sobre mí (EN)" in peticion

    sistema = gaps._system_prompt(("es", "en"), _sobre_mi().gaps())
    assert "en español y en inglés" in sistema
    assert "MISMA idea" in sistema
    assert '"GROUP_A_1": {\n    "es": "",\n    "en": ""\n  }' in sistema


def test_un_fragmento_que_no_esta_literal_se_descarta_sin_avisar():
    """The guarantee behind rule 2: the model can't insert its own text, only
    point at pieces of the user's text. A rewritten fragment («machine
    learning» where the user wrote «aprendizaje automático») finds nowhere to
    fit, so nothing gets touched."""
    respuesta = json.loads(_respuesta_completa())
    respuesta["GROUP_A_1"]["es"] = "machine learning aplicado"
    propuesta = gaps.suggest_gaps(ClienteFalso(json.dumps(respuesta)), _sobre_mi(), [])

    texto_es = propuesta.about_me.template["es"]
    assert "aprendizaje automático" in texto_es
    assert "{GROUP_A_1}" not in texto_es
    assert "machine learning aplicado" not in texto_es
    # The user never sees gaps, so there is nothing to tell them: that skill
    # is just not inserted there. The rest is placed regardless.
    assert propuesta.avisos == []
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
    """Manual marking and the AI suggestion edit the same field: what the
    user already decided wins over whatever the model proposes."""
    texto, sin_colocar = gaps.place(
        "trabajo con {GROUP_B_1} y Docker", {"{GROUP_B_1}": "Docker"}
    )

    assert texto == "trabajo con {GROUP_B_1} y Docker"
    assert sin_colocar == []


def test_una_palabra_partida_por_guion_de_fin_de_linea_se_coloca_con_el_trozo_original():
    """The model, when copying «back-\\nend» from a justified paragraph, returns
    it as «back‑end» (no line break, with U+2011). That's only used to locate
    it: what actually gets substituted is the piece exactly as the user wrote
    it, and the rest of the text doesn't change a single character."""
    texto = "Trabajo en desarrollo back-\nend. Programo en Python."
    fragmento_del_modelo = "desarrollo back\u2011end"

    resultado, sin_colocar = gaps.place(texto, {"{GROUP_A_1}": fragmento_del_modelo})

    assert sin_colocar == []
    assert resultado == texto.replace("desarrollo back-\nend", "{GROUP_A_1}")
    assert "\u2011" not in resultado


def test_se_toleran_saltos_de_linea_espacios_y_guiones_distintos():
    texto = "Experto en machine\n  learning y en full-stack."

    resultado, sin_colocar = gaps.place(
        texto,
        {"{GROUP_A_1}": "machine learning", "{GROUP_A_2}": "full\u2013stack"},
    )

    assert sin_colocar == []
    assert resultado == "Experto en {GROUP_A_1} y en {GROUP_A_2}."


def test_la_palabra_partida_sin_guion_en_el_fragmento_tambien_se_encuentra():
    texto = "Centrado en aprendi-\nzaje automático."

    resultado, sin_colocar = gaps.place(texto, {"{GROUP_A_1}": "aprendizaje automático"})

    assert sin_colocar == []
    assert resultado == "Centrado en {GROUP_A_1}."


def test_la_tolerancia_no_alcanza_a_mayusculas_ni_tildes():
    """Relaxing that could send the gap to other words of the user's, not the
    same ones written differently."""
    texto, sin_colocar = gaps.place(
        "Análisis de datos", {"{GROUP_A_1}": "analisis de datos", "{GROUP_A_2}": "ANÁLISIS"}
    )

    assert texto == "Análisis de datos"
    assert sin_colocar == ["{GROUP_A_1}", "{GROUP_A_2}"]


def test_una_coincidencia_exacta_manda_sobre_una_aproximada_anterior():
    """Text that was already placed correctly keeps landing in the same spot."""
    texto, _ = gaps.place("back-\nend y luego back-end", {"{GROUP_A_1}": "back-end"})

    assert texto == "back-\nend y luego {GROUP_A_1}"


def test_la_tolerancia_tampoco_solapa_huecos_ni_repite():
    texto, sin_colocar = gaps.place(
        "trabajo en back-\nend",
        {"{GROUP_A_1}": "back\u2011end", "{GROUP_A_2}": "backend"},
    )

    assert texto == "trabajo en {GROUP_A_1}"
    assert sin_colocar == ["{GROUP_A_2}"]


def test_un_fragmento_con_texto_propio_sigue_sin_colocarse():
    texto, sin_colocar = gaps.place(
        "Desarrollo back-\nend.", {"{GROUP_A_1}": "desarrollo backend moderno"}
    )

    assert texto == "Desarrollo back-\nend."
    assert sin_colocar == ["{GROUP_A_1}"]


def test_suggest_gaps_coloca_el_hueco_del_diagnostico_de_extremo_a_extremo():
    respuesta = json.loads(_respuesta_completa())
    respuesta["GROUP_A_2"] = {"es": "back\u2011end", "en": "back\u2011end"}
    es = SOBRE_MI_ES.replace("backend", "back-\nend")
    en = SOBRE_MI_EN.replace("backend", "back-\nend")

    propuesta = gaps.suggest_gaps(ClienteFalso(json.dumps(respuesta)), _sobre_mi(es, en), [])

    assert propuesta.avisos == []
    assert "{GROUP_A_2}" in propuesta.about_me.template["es"]
    assert "{GROUP_A_2}" in propuesta.about_me.template["en"]


# --------------------------------------------------------------------------
# What reaches the model
# --------------------------------------------------------------------------


def test_al_modelo_le_llegan_los_dos_idiomas_en_una_sola_llamada():
    """One call per language would cost double and, more importantly, would
    stop guaranteeing that a gap marks the same idea in both."""
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
# None of this can break the screen
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


# --------------------------------------------------------------------------
# Worked example in the prompt
# --------------------------------------------------------------------------


def test_el_prompt_trae_un_ejemplo_resuelto_con_los_seis_huecos():
    sistema = gaps._system_prompt(("es", "en"), _sobre_mi().gaps())
    assert "Ejemplo" in sistema
    assert '"es": "arquitectura cloud"' in sistema
    assert '"en": "cloud architecture"' in sistema
    for hueco in _sobre_mi().gaps():
        assert f'"{hueco.strip("{}")}"' in sistema


def test_con_un_solo_idioma_el_ejemplo_tiene_la_forma_de_un_solo_idioma():
    sistema = gaps._system_prompt(("en",), _sobre_mi().gaps())
    assert '"GROUP_A_3": "cloud architecture"' in sistema
    assert "arquitectura cloud" not in sistema


def test_cada_fragmento_del_ejemplo_esta_literal_en_su_texto():
    """An example whose fragments do not match its own text would teach the
    model exactly what the literal rule forbids."""
    for idioma, texto in gaps._EJEMPLO_TEXTO.items():
        _colocado, sin_colocar = gaps.place(
            texto, {h: p[idioma] for h, p in gaps._EJEMPLO_RESPUESTA.items()}
        )
        assert sin_colocar == []


# --------------------------------------------------------------------------
# derive_template: plain text in, template out
# --------------------------------------------------------------------------

TEXTO = Bilingual(es=SOBRE_MI_ES, en=SOBRE_MI_EN)


def test_derivar_desde_texto_plano_coloca_los_huecos_y_conserva_el_texto():
    propuesta = gaps.derive_template(ClienteFalso(_respuesta_completa()), TEXTO, None, [])

    assert propuesta.about_me.plain_text == TEXTO
    assert "{GROUP_A_1}" in propuesta.about_me.template["es"]
    assert "{GROUP_B_3}" in propuesta.about_me.template["en"]
    assert "aprendizaje automático" not in propuesta.about_me.template["es"]
    assert propuesta.avisos == []


def test_guardar_el_mismo_texto_no_vuelve_a_llamar_a_la_ia():
    anterior = gaps.derive_template(ClienteFalso(_respuesta_completa()), TEXTO, None, []).about_me
    cliente = ClienteFalso(_respuesta_completa())

    propuesta = gaps.derive_template(cliente, TEXTO, anterior, [])

    assert cliente.peticiones == []
    assert propuesta.about_me is anterior


def test_cambiar_el_texto_vuelve_a_derivar():
    anterior = gaps.derive_template(ClienteFalso(_respuesta_completa()), TEXTO, None, []).about_me
    cliente = ClienteFalso(_respuesta_completa())
    nuevo = Bilingual(es=SOBRE_MI_ES + " Me gusta enseñar.", en=SOBRE_MI_EN)

    propuesta = gaps.derive_template(cliente, nuevo, anterior, [])

    assert len(cliente.peticiones) == 1
    assert propuesta.about_me.plain_text == nuevo
    assert propuesta.about_me.template["es"].endswith("Me gusta enseñar.")


def test_sin_cliente_se_guarda_el_texto_tal_cual_y_se_reintenta_despues():
    sin_ia = gaps.derive_template(None, TEXTO, None, [])
    assert sin_ia.about_me.template == TEXTO
    assert sin_ia.avisos
    assert not any("{" in aviso for aviso in sin_ia.avisos)

    # Same text, provider now configured: the template never got its gaps,
    # so this save is the one that places them.
    cliente = ClienteFalso(_respuesta_completa())
    propuesta = gaps.derive_template(cliente, TEXTO, sin_ia.about_me, [])
    assert len(cliente.peticiones) == 1
    assert "{GROUP_A_1}" in propuesta.about_me.template["es"]


def test_un_texto_vacio_no_llama_ni_avisa():
    cliente = ClienteFalso(_respuesta_completa())
    vacio = Bilingual(es="", en="")
    propuesta = gaps.derive_template(cliente, vacio, None, [])
    assert cliente.peticiones == []
    assert propuesta.avisos == []
    assert propuesta.about_me.template == vacio


def test_un_perfil_antiguo_guardado_sin_cambios_conserva_su_plantilla():
    """A profile saved before `plain_text` existed shows its template with
    the gaps turned into ellipses. Saving that unchanged must keep the
    template the user built by hand, not re-derive from the ellipses."""
    plantilla = Bilingual(
        es="Experto en {GROUP_A_1} con {GROUP_B_1}.", en="Expert in {GROUP_A_1} with {GROUP_B_1}."
    )
    antiguo = AboutMe(
        template=plantilla,
        plain_text=Bilingual(es="Experto en … con ….", en="Expert in … with …."),
    )
    cliente = ClienteFalso(_respuesta_completa())

    propuesta = gaps.derive_template(cliente, antiguo.plain_text, antiguo, [])

    assert cliente.peticiones == []
    assert propuesta.about_me.template == plantilla
