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
from ancla.profile.importer import MAX_CARACTERES_CV, analyze_cv, detect_language
from ancla.profile.model import (
    PERIOD_ONGOING,
    Bilingual,
    Education,
    Experience,
    Profile,
    Skill,
    SpokenLanguage,
)


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
    resultado = analyze_cv(ClienteFalso(_respuesta()), "ML Developer. Pipeline completo.", perfil)
    assert resultado.skills == []
    assert "1 elemento(s)" in resultado.avisos[0]


def test_una_skill_que_ya_esta_en_el_perfil_solo_en_ingles_tampoco_se_repite():
    """The name can match in either language — the CV being imported now
    might be in whichever language the profile was missing."""
    perfil = Profile(skills=[Skill(id="python", name=Bilingual(es="", en="Python"))])
    resultado = analyze_cv(ClienteFalso(_respuesta()), "texto", perfil)
    assert resultado.skills == []


def test_una_experiencia_ya_en_el_perfil_no_se_repite_pero_las_skills_nuevas_si():
    """Full scenario: two CVs for the same role, the second with a couple of
    new skills. The experience is not duplicated; the new part is added."""
    perfil = Profile(
        skills=[Skill(id="python", name=Bilingual(es="Python", en="Python"))],
        experiences=[
            Experience(
                id="ml-developer",
                title=Bilingual(es="ML Developer", en="ML Developer"),
                period_start="2026", period_end="ongoing",
                bullets=Bilingual(es=["Pipeline completo"], en=["Full pipeline"]),
                stack="Python, Optuna",
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


def test_el_consejo_del_proveedor_llega_al_usuario_tal_cual():
    """A provider's message already opens with what to do; putting a cause
    in front of it ("could not analyse the CV: ...") buries the only part
    the user can act on."""
    consejo = "Espera un minuto y vuelve a intentarlo: tu plan gratuito está al tope."
    resultado = analyze_cv(ClienteFalso(AIError(consejo)), "texto", Profile())

    assert resultado.avisos == [consejo]


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


class _ClienteConPresupuesto(ClienteFalso):
    """Like a provider that understands `ai.client.complete_with_budget`'s
    hint, unlike the plain `ClienteFalso` above (which mirrors Anthropic's
    and the generic OpenAI-compatible client's fixed two-argument shape)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_tokens_recibido: int | None = None

    def complete(self, sistema: str, usuario: str, max_tokens: int | None = None) -> str:
        self.max_tokens_recibido = max_tokens
        return super().complete(sistema, usuario)


def test_declara_un_presupuesto_que_crece_con_el_texto_del_cv():
    """Unlike the selection engine or the "About me" gaps, this module's
    response genuinely scales with what it sends — the model copies fields
    out of the CV — so a longer text has to declare more room, not a fixed
    number."""
    import ancla.profile.importer as modulo_importador

    corto = _ClienteConPresupuesto(_respuesta())
    analyze_cv(corto, "Experiencia en analisis de datos con Python.", Profile())

    largo = _ClienteConPresupuesto(_respuesta())
    analyze_cv(largo, "Python. " * 500, Profile())

    assert corto.max_tokens_recibido == modulo_importador.MIN_TOKENS_RESPUESTA
    assert largo.max_tokens_recibido > corto.max_tokens_recibido


def test_un_cliente_que_no_entiende_el_presupuesto_se_llama_igual():
    resultado = analyze_cv(
        ClienteFalso(_respuesta()), "Experiencia en analisis de datos con Python.", Profile()
    )
    assert resultado.experiencias


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


# --------------------------------------------------------------------------
# Education
#
# Real case that prompted this: the importer was built when the profile had
# no education, and it never caught up — five CVs analysed, zero entries.
# --------------------------------------------------------------------------


def test_el_prompt_pide_educacion():
    """The category has to be asked for, not hoped for: the model was told
    to structure the CV into four categories and education was not one."""
    cliente = ClienteFalso(_respuesta())
    analyze_cv(cliente, "texto", Profile())
    sistema, _usuario = cliente.llamadas[0]
    assert "educacion" in sistema.lower() or "educación" in sistema.lower()
    assert "CUATRO categorías" not in sistema


def test_propone_educacion_del_texto():
    respuesta = _respuesta(
        educacion=[
            {
                "titulo": {"es": "Grado en Ingeniería Informática", "en": "BSc in Computer Engineering"},
                "centro": "UEMC",
                "periodo": "2021 - 2025",
            }
        ]
    )
    resultado = analyze_cv(ClienteFalso(respuesta), "texto", Profile())

    assert len(resultado.educacion) == 1
    educacion = resultado.educacion[0]
    assert educacion.title["es"] == "Grado en Ingeniería Informática"
    assert educacion.institution == "UEMC"
    assert educacion.period_start == "2021"
    assert educacion.period_end == "2025"
    # Never mixed into the other four catalogs.
    assert resultado.skills_personales == []
    assert all(e.title["es"] != educacion.title["es"] for e in resultado.experiencias)


def test_un_periodo_de_educacion_abierto_acaba_en_el_marcador():
    """"2023 - actualidad" is stored as the `ongoing` marker, not as the
    Spanish word, so a CV generated in English does not say "actualidad"."""
    respuesta = _respuesta(
        educacion=[
            {
                "titulo": {"es": "Máster en IA", "en": "MSc in AI"},
                "centro": "UEMC",
                "periodo": "2023 - actualidad",
            }
        ]
    )
    resultado = analyze_cv(ClienteFalso(respuesta), "texto", Profile())
    assert resultado.educacion[0].period_start == "2023"
    assert resultado.educacion[0].period_end == PERIOD_ONGOING


def test_una_educacion_que_ya_esta_en_el_perfil_no_se_vuelve_a_proponer():
    perfil = Profile(
        education=[
            Education(
                id="grado",
                title=Bilingual(es="Grado en Ingeniería Informática", en="BSc in Computer Engineering"),
                institution="UEMC",
                period_start="2021",
                period_end="2025",
            )
        ]
    )
    respuesta = _respuesta(
        educacion=[
            {
                "titulo": {"es": "Grado en Ingeniería Informática", "en": "BSc in Computer Engineering"},
                "centro": "UEMC",
                "periodo": "2021 - 2025",
            }
        ]
    )
    resultado = analyze_cv(ClienteFalso(respuesta), "ML Developer. Pipeline completo.", perfil)
    assert resultado.educacion == []
    assert "1 elemento(s)" in resultado.avisos[0]


def test_una_educacion_sin_titulo_se_descarta():
    respuesta = _respuesta(
        educacion=[{"titulo": {"es": "", "en": ""}, "centro": "UEMC", "periodo": "2021 - 2025"}]
    )
    resultado = analyze_cv(ClienteFalso(respuesta), "texto", Profile())
    assert resultado.educacion == []


def test_el_id_de_una_educacion_no_choca_con_el_perfil():
    perfil = Profile(
        education=[
            Education(
                id="grado-en-ingenieria-informatica",
                title=Bilingual(es="Grado en Ingeniería Informática (Rumanía)", en="BSc (Romania)"),
                institution="Otra",
                period_start="2018",
                period_end="2021",
            )
        ]
    )
    respuesta = _respuesta(
        educacion=[
            {
                "titulo": {"es": "Grado en Ingeniería Informática", "en": "BSc in Computer Engineering"},
                "centro": "UEMC",
                "periodo": "2021 - 2025",
            }
        ]
    )
    resultado = analyze_cv(ClienteFalso(respuesta), "texto", perfil)
    assert resultado.educacion[0].id != "grado-en-ingenieria-informatica"


def test_el_centro_no_se_traduce_aunque_el_modelo_lo_devuelva_bilingue():
    """Rule 10 asks for a single text, but a slip must not lose the field."""
    respuesta = _respuesta(
        educacion=[
            {
                "titulo": {"es": "Máster en IA", "en": "MSc in AI"},
                "centro": {"es": "UEMC", "en": "UEMC"},
                "periodo": {"es": "2023 - 2024", "en": "2023 - 2024"},
            }
        ]
    )
    resultado = analyze_cv(ClienteFalso(respuesta), "texto", Profile())
    assert resultado.educacion[0].institution == "UEMC"
    assert resultado.educacion[0].period_start == "2023"


def test_una_educacion_sola_cuenta_como_algo_encontrado():
    respuesta = json.dumps(
        {
            "experiencias": [],
            "skills": [],
            "educacion": [
                {
                    "titulo": {"es": "Máster en IA", "en": "MSc in AI"},
                    "centro": "UEMC",
                    "periodo": "2023 - 2024",
                }
            ],
        }
    )
    resultado = analyze_cv(ClienteFalso(respuesta), "texto", Profile())
    assert resultado.avisos == []
    assert len(resultado.educacion) == 1


def test_sin_educacion_en_la_respuesta_no_revienta():
    resultado = analyze_cv(ClienteFalso(_respuesta()), "texto", Profile())
    assert resultado.educacion == []


# --------------------------------------------------------------------------
# One language per call
# --------------------------------------------------------------------------


def _respuesta_un_idioma() -> str:
    return json.dumps(
        {
            "experiencias": [
                {
                    "titulo": "Desarrollador de ML",
                    "periodo": "2026 - actualidad",
                    "bullets": ["Pipeline completo"],
                    "stack": "Python, Optuna",
                    "keywords": ["machine learning"],
                }
            ],
            "skills": [{"nombre": "Python", "categoria": "lenguaje", "keywords": ["python"]}],
            "idiomas": [{"nombre": "Inglés", "nivel": "C1", "keywords": ["english"]}],
            "educacion": [{"titulo": "Grado", "centro": "UEMC", "periodo": "2023 - 2027"}],
        },
        ensure_ascii=False,
    )


def test_solo_rellena_el_idioma_pedido():
    """Half the answer is half the output tokens, and the output is what
    fills the per-minute quota."""
    resultado = analyze_cv(ClienteFalso(_respuesta_un_idioma()), "texto", Profile(), "es")

    assert resultado.experiencias[0].title["es"] == "Desarrollador de ML"
    assert resultado.experiencias[0].title["en"] == ""
    assert resultado.experiencias[0].bullets["en"] == []
    assert resultado.skills[0].name["en"] == ""
    assert resultado.idiomas[0].level["en"] == ""
    assert resultado.educacion[0].title["en"] == ""


def test_importar_en_ingles_deja_vacio_el_espanol():
    resultado = analyze_cv(ClienteFalso(_respuesta_un_idioma()), "text", Profile(), "en")

    assert resultado.skills[0].name["en"] == "Python"
    assert resultado.skills[0].name["es"] == ""


def test_el_prompt_pide_el_idioma_del_cv():
    cliente = ClienteFalso(_respuesta_un_idioma())
    analyze_cv(cliente, "text", Profile(), "en")

    sistema = cliente.llamadas[0][0]
    assert "inglés" in sistema
    assert '"titulo": {"es"' not in sistema


def test_un_par_es_en_devuelto_igualmente_no_se_tira():
    """The pair has already been paid for by the time it arrives; dropping
    half of an answer that is right would be worse than the prompt slip."""
    respuesta = json.dumps(
        {"skills": [{"nombre": {"es": "Python", "en": "Python"}, "categoria": "l", "keywords": []}]}
    )
    resultado = analyze_cv(ClienteFalso(respuesta), "texto", Profile(), "es")

    assert resultado.skills[0].name["en"] == "Python"


def test_un_cv_demasiado_largo_avisa_de_lo_que_no_se_ha_leido():
    """The cut used to be silent, and a CV analysed halfway looked like a
    model that had missed half a career."""
    largo = "Experiencia en desarrollo. " * 1000
    resultado = analyze_cv(ClienteFalso(_respuesta_un_idioma()), largo, Profile(), "es")

    assert any("caracteres" in aviso for aviso in resultado.avisos)


def test_un_cv_por_debajo_del_limite_llega_entero():
    texto = "Experiencia en desarrollo.\n" * 50  # well under MAX_CARACTERES_CV
    assert len(texto) < MAX_CARACTERES_CV
    cliente = ClienteFalso(_respuesta_un_idioma())

    resultado = analyze_cv(cliente, texto, Profile(), "es")

    _, usuario = cliente.llamadas[0]
    assert usuario == texto.strip()
    assert not any("caracteres" in aviso for aviso in resultado.avisos)
    assert resultado.restante == ""


def test_el_recorte_no_parte_una_palabra_por_la_mitad():
    """Cutting on a line break instead of an exact character count keeps the
    text sent to the model readable, instead of severing the last line mid
    word right at the edge of the budget."""
    linea = "Coordino un equipo multidisciplinar de desarrollo de software.\n"
    texto = linea * (MAX_CARACTERES_CV // len(linea) + 5)
    cliente = ClienteFalso(_respuesta_un_idioma())

    analyze_cv(cliente, texto, Profile(), "es")

    _, usuario = cliente.llamadas[0]
    enviado = usuario.rsplit("\n[...texto recortado...]", 1)[0]
    assert enviado.endswith("software.")


def test_detecta_el_idioma_del_cv():
    assert detect_language("Experiencia en desarrollo de software para la empresa") == "es"
    assert detect_language("Experience in software development for the company") == "en"


def test_sin_palabras_reconocibles_se_queda_en_espanol():
    """A guess, not a decision: the user can correct it before the call, and
    the app's own language is the safer default."""
    assert detect_language("Python Docker AWS PostgreSQL") == "es"


def _cv_largo_con_secciones(*titulos: str) -> str:
    """A CV over `MAX_CARACTERES_CV` whose sections are evenly sized, so the
    last heading that fits is neither the first nor the last of them."""
    relleno = "Linea de contenido de la seccion, con la longitud de una de verdad\n"
    por_seccion = MAX_CARACTERES_CV // (len(titulos) - 1) // len(relleno) + 1
    return "".join(f"{titulo}\n" + relleno * por_seccion for titulo in titulos)


def test_un_cv_largo_se_corta_donde_empieza_una_seccion():
    """Cutting on any line can split Experience in half and leave Education
    out entirely, with nothing in the truncated text to hint at it."""
    texto = _cv_largo_con_secciones("EXPERIENCIA", "EDUCACIÓN", "IDIOMAS")
    cliente = ClienteFalso(_respuesta_un_idioma())

    resultado = analyze_cv(cliente, texto, Profile(), "es")

    _, usuario = cliente.llamadas[0]
    enviado = usuario.rsplit("\n[...texto recortado...]", 1)[0]
    assert enviado.endswith("de verdad")
    assert "EDUCACIÓN" not in enviado
    assert any("EDUCACIÓN" in aviso for aviso in resultado.avisos)
    # The leftover starts exactly where the warning said to cut, so a
    # second call over it never repeats what the first one already read.
    assert resultado.restante.startswith("EDUCACIÓN")
    assert "IDIOMAS" in resultado.restante


def test_un_cv_largo_en_ingles_se_corta_igual_que_uno_en_espanol():
    texto = _cv_largo_con_secciones("WORK EXPERIENCE", "EDUCATION", "LANGUAGES")
    cliente = ClienteFalso(_respuesta_un_idioma())

    resultado = analyze_cv(cliente, texto, Profile(), "en")

    _, usuario = cliente.llamadas[0]
    assert "EDUCATION" not in usuario
    assert any("EDUCATION" in aviso for aviso in resultado.avisos)


def test_un_cv_largo_sin_secciones_sigue_cortando_por_linea():
    """A CV pasted as one loose paragraph has no boundary to cut on, and
    breaking on that is worse than the plainer warning."""
    linea = "Coordino un equipo multidisciplinar de desarrollo de software.\n"
    texto = linea * (MAX_CARACTERES_CV // len(linea) + 5)
    cliente = ClienteFalso(_respuesta_un_idioma())

    resultado = analyze_cv(cliente, texto, Profile(), "es")

    _, usuario = cliente.llamadas[0]
    enviado = usuario.rsplit("\n[...texto recortado...]", 1)[0]
    assert enviado.endswith("software.")
    assert any("caracteres" in aviso for aviso in resultado.avisos)
    assert resultado.restante != ""


# --------------------------------------------------------------------------
# Contact and "About me" — same semantic criterion as the five categories
# above: nothing here should depend on a literal header appearing in the
# text, the CV can bury both under the name with no section title at all.
# --------------------------------------------------------------------------


def _respuesta_con_contacto_y_sobre_mi(**cambios) -> str:
    datos = {
        "experiencias": [], "skills": [], "skills_personales": [], "idiomas": [],
        "educacion": [],
        "contacto": {
            "nombre": "Ana Ejemplo",
            "titular": "Ingeniera de Datos",
            "lineas": ["ana@ejemplo.com", "+34 600 000 000", "Madrid, España"],
        },
        "sobre_mi": "Ingeniera con pasión por los datos y el aprendizaje automático.",
    }
    datos.update(cambios)
    return json.dumps(datos, ensure_ascii=False)


def test_propone_contacto_y_sobre_mi():
    resultado = analyze_cv(ClienteFalso(_respuesta_con_contacto_y_sobre_mi()), "texto", Profile())

    assert resultado.contacto is not None
    assert resultado.contacto.name == "Ana Ejemplo"
    assert resultado.contacto.headline["es"] == "Ingeniera de Datos"
    assert resultado.contacto.headline["en"] == ""  # single-language import
    assert resultado.contacto.lines == ["ana@ejemplo.com", "+34 600 000 000", "Madrid, España"]

    assert resultado.sobre_mi is not None
    assert resultado.sobre_mi.template["es"] == (
        "Ingeniera con pasión por los datos y el aprendizaje automático."
    )
    assert resultado.sobre_mi.template["en"] == ""


def test_el_sobre_mi_llega_como_texto_plano_sin_huecos():
    """The importer never places {GROUP_A_*}/{GROUP_B_*} itself — that is
    `gaps.py`'s job, called by the web layer once this text is back."""
    resultado = analyze_cv(ClienteFalso(_respuesta_con_contacto_y_sobre_mi()), "texto", Profile())
    assert "{GROUP_A_1}" not in resultado.sobre_mi.template["es"]
    assert "{GROUP_B_1}" not in resultado.sobre_mi.template["es"]


def test_sin_contacto_ni_sobre_mi_en_la_respuesta_no_revienta():
    resultado = analyze_cv(ClienteFalso(_respuesta()), "texto", Profile())
    assert resultado.contacto is None
    assert resultado.sobre_mi is None


def test_un_contacto_vacio_se_descarta_no_se_propone():
    respuesta = _respuesta_con_contacto_y_sobre_mi(
        contacto={"nombre": "", "titular": "", "lineas": []}
    )
    resultado = analyze_cv(ClienteFalso(respuesta), "texto", Profile())
    assert resultado.contacto is None


def test_un_sobre_mi_vacio_se_descarta_no_se_propone():
    respuesta = _respuesta_con_contacto_y_sobre_mi(sobre_mi="")
    resultado = analyze_cv(ClienteFalso(respuesta), "texto", Profile())
    assert resultado.sobre_mi is None


def test_solo_contacto_cuenta_como_algo_encontrado():
    """A CV where only the contact block was recognisable must not warn
    that nothing was found — same guarantee as `test_una_educacion_sola_
    cuenta_como_algo_encontrado`, extended to the two new categories."""
    respuesta = _respuesta_con_contacto_y_sobre_mi(sobre_mi="")
    resultado = analyze_cv(ClienteFalso(respuesta), "texto", Profile())
    assert resultado.avisos == []
    assert resultado.contacto is not None


def test_el_prompt_pide_contacto_y_sobre_mi():
    cliente = ClienteFalso(_respuesta())
    analyze_cv(cliente, "texto", Profile())
    sistema, _usuario = cliente.llamadas[0]
    assert "contacto" in sistema.lower()
    assert "sobre mí" in sistema.lower()


def test_el_nombre_de_contacto_no_se_traduce_aunque_el_modelo_lo_devuelva_bilingue():
    """`nombre` and `lineas` follow the same non-bilingual rule as
    `Profile.name`/`Profile.contact`: a name or a phone number reads the
    same in any language, so a model that answers with an {es, en} pair
    anyway still collapses to one value, like `stack` and `centro` do."""
    respuesta = _respuesta_con_contacto_y_sobre_mi(
        contacto={
            "nombre": {"es": "Ana Ejemplo", "en": "Ana Ejemplo"},
            "titular": "Ingeniera de Datos",
            "lineas": ["ana@ejemplo.com"],
        }
    )
    resultado = analyze_cv(ClienteFalso(respuesta), "texto", Profile())
    assert resultado.contacto.name == "Ana Ejemplo"


def _espaciado_como_canva(texto: str) -> str:
    """`texto` as `pypdf` extracts some Canva PDFs: a space between every
    letter and two between words."""
    return "\n".join(
        "  ".join(" ".join(palabra) for palabra in linea.split(" "))
        for linea in texto.splitlines()
    ) + "\n"


def test_un_cv_con_letras_separadas_se_corta_antes_del_sobre_mi_no_dentro():
    """Letter-spacing nearly doubles a CV's length, so it is the kind of
    text most likely to need cutting. If its headings were not recognised,
    the only cut left would be the blind line one, which can leave the
    "About me" heading on one side and its paragraph on the other."""
    experiencia = "Desarrollo de servicios de datos para clientes del sector\n"
    sobre_mi = "Ingeniero de datos con varios años construyendo tuberías\n"
    lineas_experiencia = int(MAX_CARACTERES_CV * 0.7) // len(_espaciado_como_canva(experiencia))
    texto = _espaciado_como_canva(
        "Experiencia\n" + experiencia * lineas_experiencia + "Sobre mí\n" + sobre_mi * 20
    )
    encabezado = _espaciado_como_canva("Sobre mí").strip()
    assert texto.index(encabezado) < MAX_CARACTERES_CV < len(texto)
    cliente = ClienteFalso(_respuesta_un_idioma())

    resultado = analyze_cv(cliente, texto, Profile(), "es")

    _, usuario = cliente.llamadas[0]
    assert encabezado not in usuario
    assert resultado.restante.startswith(encabezado)
    assert resultado.restante.count(_espaciado_como_canva(sobre_mi).strip()) == 20
    assert any(encabezado in aviso for aviso in resultado.avisos)


# --------------------------------------------------------------------------
# Experiences imported as one paragraph of prose
# --------------------------------------------------------------------------


class ClienteEncolado:
    """One answer per call, in order: splitting bullets is a second call over
    the same CV, so a client that repeats one answer forever cannot tell the
    two apart."""

    def __init__(self, *respuestas: str):
        self.respuestas = list(respuestas)
        self.llamadas: list[tuple[str, str]] = []

    def complete(self, sistema: str, usuario: str) -> str:
        self.llamadas.append((sistema, usuario))
        return self.respuestas.pop(0) if self.respuestas else "{}"

    def available(self) -> bool:
        return True


_PARRAFO = (
    "Diseñé el pipeline de datos que alimenta el modelo de riesgo del equipo. "
    "Automaticé el despliegue con Docker y GitHub Actions, reduciendo a la mitad "
    "el tiempo de publicación. Formé a dos compañeros nuevos en el stack de datos."
)


def _cv_con_un_parrafo(bullets: list[str]) -> str:
    return json.dumps(
        {"experiencias": [{"titulo": "Ingeniero de datos", "periodo": "2023", "bullets": bullets}]}
    )


def _corte(*fragmentos: str) -> str:
    return json.dumps({"fragmentos": list(fragmentos)})


def test_una_experiencia_escrita_como_parrafo_se_divide_en_bullets():
    cliente = ClienteEncolado(
        _cv_con_un_parrafo([_PARRAFO]),
        _corte("Diseñé el pipeline", "Automaticé el despliegue", "Formé a dos"),
    )

    resultado = analyze_cv(cliente, "texto de un CV", Profile(), "es")

    bullets = resultado.experiencias[0].bullets["es"]
    assert len(bullets) == 3
    assert "".join(bullets).replace(" ", "") == _PARRAFO.replace(" ", "")
    assert resultado.experiencias[0].bullets["en"] == []


def test_unos_bullets_ya_escritos_no_gastan_una_segunda_llamada():
    cliente = ClienteEncolado(_cv_con_un_parrafo(["Diseñé el pipeline.", "Automaticé el despliegue."]))

    analyze_cv(cliente, "texto de un CV", Profile(), "es")

    assert len(cliente.llamadas) == 1


def test_un_corte_que_no_se_localiza_deja_el_parrafo_como_un_solo_bullet():
    cliente = ClienteEncolado(
        _cv_con_un_parrafo([_PARRAFO]),
        _corte("Diseñé el pipeline", "Lideré la migración a Kubernetes"),
    )

    resultado = analyze_cv(cliente, "texto de un CV", Profile(), "es")

    assert resultado.experiencias[0].bullets["es"] == [_PARRAFO]


def test_un_fallo_al_dividir_no_tumba_la_importacion():
    class ClienteQueFallaAlDividir(ClienteEncolado):
        def complete(self, sistema, usuario):
            if self.llamadas:
                raise AIError("cuota agotada")
            return super().complete(sistema, usuario)

    cliente = ClienteQueFallaAlDividir(_cv_con_un_parrafo([_PARRAFO]))

    resultado = analyze_cv(cliente, "texto de un CV", Profile(), "es")

    assert resultado.experiencias[0].bullets["es"] == [_PARRAFO]


# --------------------------------------------------------------------------
# The user's own prose has to come back as written
# --------------------------------------------------------------------------

# Shape of a real import where the model rewrote the bullets: the CV says
# "he diseñado y mantenido", the answer said "Diseñé y mantuve".
_CV_EN_PRIMERA_PERSONA = """\
Ingeniera de Datos Senior — Transportes Levante
2021 - Actualidad
En este puesto he diseñado y mantenido la plataforma de datos de la empresa sobre AWS. \
He migrado más de 40 procesos ETL desde scripts cron a Airflow.

Sobre mí
Soy ingeniera de datos con seis años de experiencia construyendo plataformas analíticas."""


def _cv_importado(bullets: list[str], sobre_mi: str = "") -> str:
    return json.dumps(
        {
            "experiencias": [
                {"titulo": "Ingeniera de Datos Senior", "periodo": "2021 - Actualidad", "bullets": bullets}
            ],
            "sobre_mi": sobre_mi,
        },
        ensure_ascii=False,
    )


def test_unos_bullets_reescritos_por_el_modelo_se_avisan_con_el_nombre_de_la_experiencia():
    reescritos = ["Diseñé y mantuve la plataforma de datos de la empresa sobre AWS."]
    cliente = ClienteFalso(_cv_importado(reescritos))

    resultado = analyze_cv(cliente, _CV_EN_PRIMERA_PERSONA, Profile(), "es")

    assert any("«Ingeniera de Datos Senior»" in aviso for aviso in resultado.avisos)
    # Warned, not dropped: the review screen is where the user fixes it.
    assert resultado.experiencias[0].bullets["es"] == reescritos


def test_unos_bullets_copiados_tal_cual_no_avisan_aunque_el_pdf_los_parta_en_lineas():
    cv = _CV_EN_PRIMERA_PERSONA.replace("plataforma de datos", "plata-\nforma de datos")
    copiados = [
        "En este puesto he diseñado y mantenido la plataforma de datos de la empresa sobre AWS.",
        "He migrado más de 40 procesos ETL desde scripts cron a Airflow.",
    ]

    resultado = analyze_cv(ClienteFalso(_cv_importado(copiados)), cv, Profile(), "es")

    assert resultado.avisos == []


def test_un_sobre_mi_reescrito_por_el_modelo_se_avisa():
    literal = ["He migrado más de 40 procesos ETL desde scripts cron a Airflow."]
    cliente = ClienteFalso(
        _cv_importado(literal, sobre_mi="Ingeniera de datos con seis años construyendo plataformas.")
    )

    resultado = analyze_cv(cliente, _CV_EN_PRIMERA_PERSONA, Profile(), "es")

    assert len(resultado.avisos) == 1
    assert "«Sobre mí»" in resultado.avisos[0]


def test_los_bullets_que_corta_el_divisor_nunca_avisan_de_reescritura():
    """The splitter only cuts the user's text, so what it returns is literal
    by construction and must never trip the rewrite check."""
    cliente = ClienteEncolado(
        _cv_con_un_parrafo([_PARRAFO]),
        _corte("Diseñé el pipeline", "Automaticé el despliegue", "Formé a dos"),
    )

    resultado = analyze_cv(cliente, "Ingeniero de datos\n" + _PARRAFO, Profile(), "es")

    assert len(resultado.experiencias[0].bullets["es"]) == 3
    assert resultado.avisos == []


def test_el_prompt_pide_copiar_los_bullets_sin_partir_la_prosa():
    """What actually kept imported bullets literal against the real API: the
    main prompt used to split prose itself, and rewrote each piece while at
    it. Splitting belongs to `profile/bullets.py`, which cannot rewrite."""
    sistema, _usuario = _una_llamada(_CV_EN_PRIMERA_PERSONA)

    assert "se copian TAL CUAL" in sistema
    assert "devuelve el párrafo ENTERO como un único bullet" in sistema


def _una_llamada(texto: str) -> tuple[str, str]:
    cliente = ClienteFalso(_cv_importado([]))
    analyze_cv(cliente, texto, Profile(), "es")
    return cliente.llamadas[0]
