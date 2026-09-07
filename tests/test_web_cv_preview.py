"""HTTP tests for the printable HTML preview: that the sheet carries the
proposal's own content, that the two sections nobody selects (languages and
personal skills) come out whole, that a template's declared
[capacity_min, capacity_max] range is enforced rather than only warned
about, that anything left out for exceeding the maximum is still named on
screen, and that a new template is three files in a folder rather than a
code change."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from ancla.archive import repository as archivo
from ancla.profile import store
from ancla.profile.model import (
    AboutMe,
    Bilingual,
    CVStatus,
    Education,
    Experience,
    Proposal,
    SavedCV,
    SelectedAboutMe,
    SelectedExperience,
    Skill,
    SpokenLanguage,
)
from ancla.web import create_app
from ancla.web import draft as modulo_borrador

PLANTILLAS_HTML = Path(__file__).resolve().parent.parent / "html-templates"
PLANTILLA = "corporativa-clasica"

_EXPERIENCIAS = [
    ("exp-1", "Rol Uno · Empresa A", "Motivo A"),
    ("exp-2", "Rol Dos · Empresa B", "Motivo B"),
    ("exp-3", "Rol Tres · Empresa C", "Motivo C"),
    ("exp-4", "Rol Cuatro · Empresa D", "Motivo D"),
    ("exp-5", "Rol Cinco · Empresa E", "Motivo E"),
]

_IDIOMAS = [("en", "Inglés", "C1"), ("fr", "Francés", "B1"), ("de", "Alemán", "A2")]
_SKILLS_PERSONALES = [("equipo", "Trabajo en equipo"), ("empatia", "Empatía"), ("liderazgo", "Liderazgo")]


def _perfil_en_disco(root: Path) -> None:
    store.save_contact(
        root,
        "Ada Lovelace",
        Bilingual(es="Ingeniera de datos", en="Data engineer"),
        ["ada@example.com", "+34 600 000 000"],
    )
    for id_, titulo, _motivo in _EXPERIENCIAS:
        store.save_experience(
            root,
            Experience(
                id=id_,
                title=Bilingual(es=titulo, en=titulo),
                period_start="2023", period_end="",
                bullets=Bilingual(es=[f"Bullet de {id_}"], en=[f"Bullet of {id_}"]),
                stack="Python, SQL",
            ),
        )
    store.save_skill(root, Skill(id="python", name=Bilingual(es="Python", en="Python")))
    store.save_about_me(
        root, AboutMe(template=Bilingual(es="Trabajo con {GROUP_A_1}.", en="I work with {GROUP_A_1}."))
    )
    store.save_education(
        root,
        Education(
            id="grado",
            title=Bilingual(es="Grado en Informática", en="CS degree"),
            institution="Universidad de Ejemplo",
            period_start="2018", period_end="2022",
        ),
    )
    for id_, nombre in _SKILLS_PERSONALES:
        store.save_personal_skill(root, Skill(id=id_, name=Bilingual(es=nombre, en=nombre)))
    for id_, nombre, nivel in _IDIOMAS:
        store.save_language(
            root,
            SpokenLanguage(
                id=id_, name=Bilingual(es=nombre, en=nombre), level=Bilingual(es=nivel, en=nivel)
            ),
        )


def _propuesta(cuantas: int) -> Proposal:
    return Proposal(
        language="es",
        about_me=SelectedAboutMe(group_a=[], group_b=[], text="Sobre mí de la propuesta.", reason=""),
        skills=["python"],
        experiences=[
            SelectedExperience(id=id_, reason=motivo) for id_, _titulo, motivo in _EXPERIENCIAS[:cuantas]
        ],
    )


def _cliente(tmp_path: Path, n_experiencias: int, plantillas_root: Path = PLANTILLAS_HTML):
    root = tmp_path / "perfil"
    _perfil_en_disco(root)
    app = create_app(
        raiz_perfil=root,
        settings_path=tmp_path / "ajustes.json",
        html_templates_root=plantillas_root,
    )
    app.config["TESTING"] = True
    modulo_borrador.save_draft(
        root,
        modulo_borrador.Draft(
            vacante="Buscamos Python.", empresa="ACME", puesto="Backend",
            propuesta=_propuesta(n_experiencias),
        ),
    )
    return app.test_client()


def _vista_previa(cliente, **parametros) -> str:
    consulta = "&".join(f"{clave}={valor}" for clave, valor in {"plantilla_id": PLANTILLA, **parametros}.items())
    respuesta = cliente.get(f"/propuesta/vista-previa?{consulta}")
    assert respuesta.status_code == 200
    return respuesta.data.decode("utf-8")


# --------------------------------------------------------------------------
# The sheet shows the proposal
# --------------------------------------------------------------------------


def test_la_vista_previa_trae_el_contenido_de_la_propuesta(tmp_path: Path):
    html = _vista_previa(_cliente(tmp_path, n_experiencias=2))

    assert "Sobre mí de la propuesta." in html
    assert "Rol Uno · Empresa A" in html
    assert "Bullet de exp-1" in html
    assert "Ada Lovelace" in html.replace("</strong>", "")
    assert "Ingeniera de datos" in html
    assert "ada@example.com" in html
    assert "Grado en Informática" in html


def test_la_vista_previa_enlaza_la_hoja_de_estilos_de_la_plantilla(tmp_path: Path):
    html = _vista_previa(_cliente(tmp_path, n_experiencias=1))

    assert f"/plantillas-html/{PLANTILLA}.css" in html


def test_la_hoja_de_estilos_de_la_plantilla_se_sirve_como_css(tmp_path: Path):
    cliente = _cliente(tmp_path, n_experiencias=1)

    respuesta = cliente.get(f"/plantillas-html/{PLANTILLA}.css")

    assert respuesta.status_code == 200
    assert respuesta.mimetype == "text/css"
    assert "@page" in respuesta.data.decode("utf-8")


def test_una_plantilla_que_no_existe_no_sirve_ningun_estilo(tmp_path: Path):
    cliente = _cliente(tmp_path, n_experiencias=1)

    assert cliente.get("/plantillas-html/inventada.css").status_code == 404


# --------------------------------------------------------------------------
# Rule 7: languages and personal skills are never trimmed
# --------------------------------------------------------------------------


def test_los_idiomas_y_las_skills_personales_salen_completos(tmp_path: Path):
    html = _vista_previa(_cliente(tmp_path, n_experiencias=1))

    for _id, nombre, nivel in _IDIOMAS:
        assert f"{nombre} — {nivel}" in html
    for _id, nombre in _SKILLS_PERSONALES:
        assert nombre in html


# --------------------------------------------------------------------------
# Overflow past capacity_max: cut, but never silently
# --------------------------------------------------------------------------


def test_solo_entran_en_la_hoja_las_experiencias_dentro_de_la_capacidad_pedida(tmp_path: Path):
    """The bullet text is what's unique to the sheet itself (the excluded
    list below only names the title and the reason, never the bullets), so
    it's what tells apart "printed" from "merely mentioned as left out"."""
    cliente = _cliente(tmp_path, n_experiencias=5)

    html = _vista_previa(cliente, capacidad=3)

    assert "Bullet de exp-1" in html
    assert "Bullet de exp-2" in html
    assert "Bullet de exp-3" in html
    assert "Bullet de exp-4" not in html
    assert "Bullet de exp-5" not in html


def test_las_que_quedan_fuera_se_nombran_con_su_motivo(tmp_path: Path):
    """Rule 3: cutting an experience is now the user's own choice (drag to
    reorder), but the app still has to say which ones it cut and why they
    were selected in the first place — nothing disappears silently."""
    cliente = _cliente(tmp_path, n_experiencias=5)

    html = _vista_previa(cliente, capacidad=3)

    assert "Rol Cuatro · Empresa D" in html
    assert "Motivo D" in html
    assert "Rol Cinco · Empresa E" in html
    assert "Motivo E" in html


def test_sin_desbordamiento_no_hay_aviso_de_excluidas(tmp_path: Path):
    html = _vista_previa(_cliente(tmp_path, n_experiencias=2), capacidad=4)

    assert "Rol Uno · Empresa A" in html
    assert "Rol Dos · Empresa B" in html


def test_la_capacidad_pedida_no_puede_superar_el_maximo_de_la_plantilla(tmp_path: Path):
    """The design's own capacidad_experiencias_max (5) is a hard ceiling on
    the server, regardless of what the query string asks for — a
    hand-edited URL can't bring back the second page."""
    cliente = _cliente(tmp_path, n_experiencias=4)

    html = _vista_previa(cliente, capacidad=20)

    for _id, titulo, _motivo in _EXPERIENCIAS[:4]:
        assert titulo in html


def test_una_capacidad_ilegible_no_rompe_la_vista_previa(tmp_path: Path):
    html = _vista_previa(_cliente(tmp_path, n_experiencias=4), capacidad="cuatro")

    assert "Rol Uno · Empresa A" in html


# --------------------------------------------------------------------------
# Underflow below capacity_min: never padded, only flagged
# --------------------------------------------------------------------------


def test_por_debajo_del_minimo_se_avisa_sin_inventar_nada(tmp_path: Path):
    plantillas = tmp_path / "html-templates"
    plantillas.mkdir()
    (plantillas / "exigente.html").write_text(
        "<article class='cv'>{% for e in experiencias %}<p>{{ e.puesto }}</p>{% endfor %}</article>",
        encoding="utf-8",
    )
    (plantillas / "exigente.css").write_text("@page { size: A4; }", encoding="utf-8")
    (plantillas / "exigente.yaml").write_text(
        "nombre: Exigente\ncapacidad_experiencias_min: 3\ncapacidad_experiencias_max: 4\n",
        encoding="utf-8",
    )
    cliente = _cliente(tmp_path, n_experiencias=1, plantillas_root=plantillas)

    html = cliente.get("/propuesta/vista-previa?plantilla_id=exigente").data.decode("utf-8")

    assert "Rol Uno · Empresa A" in html
    assert "al menos 3" in html


# --------------------------------------------------------------------------
# The selector is clamped to the template's own range
# --------------------------------------------------------------------------


def test_el_campo_de_capacidad_no_admite_menos_del_minimo_ni_mas_del_maximo(tmp_path: Path):
    plantillas = tmp_path / "html-templates"
    plantillas.mkdir()
    (plantillas / "acotada.html").write_text("<article class='cv'></article>", encoding="utf-8")
    (plantillas / "acotada.css").write_text("@page { size: A4; }", encoding="utf-8")
    (plantillas / "acotada.yaml").write_text(
        "nombre: Acotada\ncapacidad_experiencias_min: 3\ncapacidad_experiencias_max: 4\n",
        encoding="utf-8",
    )
    cliente = _cliente(tmp_path, n_experiencias=1, plantillas_root=plantillas)

    html = cliente.get("/propuesta").data.decode("utf-8")

    assert 'data-capacidad-min="3"' in html
    assert 'data-capacidad-max="4"' in html
    assert 'id="capacidad_html"' in html
    assert 'min="3"' in html
    assert 'max="4"' in html


def test_una_plantilla_sin_maximo_declarado_no_limita_por_arriba(tmp_path: Path):
    """`capacity_max <= 0` means the sidecar simply didn't declare an upper
    bound — treated as unbounded rather than as zero experiences."""
    plantillas = tmp_path / "html-templates"
    plantillas.mkdir()
    (plantillas / "sin-tope.html").write_text(
        "<article class='cv'>{% for e in experiencias %}<p>{{ e.puesto }}</p>{% endfor %}</article>",
        encoding="utf-8",
    )
    (plantillas / "sin-tope.css").write_text("@page { size: A4; }", encoding="utf-8")
    (plantillas / "sin-tope.yaml").write_text("nombre: Sin tope\n", encoding="utf-8")
    cliente = _cliente(tmp_path, n_experiencias=4, plantillas_root=plantillas)

    html = cliente.get("/propuesta/vista-previa?plantilla_id=sin-tope").data.decode("utf-8")

    for _id, titulo, _motivo in _EXPERIENCIAS[:4]:
        assert titulo in html


# --------------------------------------------------------------------------
# PDF is the primary path, .docx no longer competes with it
# --------------------------------------------------------------------------


def test_el_boton_de_ver_el_cv_es_primario_y_el_de_docx_no(tmp_path: Path):
    html = _cliente(tmp_path, n_experiencias=1).get("/propuesta").data.decode("utf-8")

    inicio_docx = html.index("Descargar CV maquetado (.docx)")
    boton_docx = html.index("Descargar .docx", inicio_docx)
    etiqueta_boton_docx = html.rindex("<button", inicio_docx, boton_docx)

    assert 'class="boton boton-primario"' in html  # el de «Ver el CV (PDF)»
    assert "boton-primario" not in html[etiqueta_boton_docx:boton_docx]


# --------------------------------------------------------------------------
# A new template is files in a folder, not a code change
# --------------------------------------------------------------------------


def test_una_plantilla_nueva_solo_necesita_sus_ficheros(tmp_path: Path):
    plantillas = tmp_path / "html-templates"
    plantillas.mkdir()
    (plantillas / "sobria.html").write_text(
        "<article class='cv'><h1>{{ nombre }}</h1><p>{{ sobre_mi }}</p></article>", encoding="utf-8"
    )
    (plantillas / "sobria.css").write_text(".cv { color: #000; }", encoding="utf-8")
    (plantillas / "sobria.yaml").write_text(
        "nombre:\n  es: Sobria\n  en: Plain\ncapacidad_experiencias: 3\n", encoding="utf-8"
    )
    cliente = _cliente(tmp_path, n_experiencias=1, plantillas_root=plantillas)

    assert "Sobria" in cliente.get("/propuesta").data.decode("utf-8")
    respuesta = cliente.get("/propuesta/vista-previa?plantilla_id=sobria")
    assert respuesta.status_code == 200
    assert "Sobre mí de la propuesta." in respuesta.data.decode("utf-8")


def test_una_plantilla_sin_su_yaml_se_ignora_en_vez_de_romper_la_pantalla(tmp_path: Path):
    plantillas = tmp_path / "html-templates"
    plantillas.mkdir()
    (plantillas / "a-medias.html").write_text("<article>{{ nombre }}</article>", encoding="utf-8")
    cliente = _cliente(tmp_path, n_experiencias=1, plantillas_root=plantillas)

    respuesta = cliente.get("/propuesta")

    assert respuesta.status_code == 200
    assert "a-medias" not in respuesta.data.decode("utf-8")


def test_sin_plantillas_html_la_pantalla_lo_dice_y_no_ofrece_vista_previa(tmp_path: Path):
    cliente = _cliente(tmp_path, n_experiencias=1, plantillas_root=tmp_path / "vacio")

    html = cliente.get("/propuesta").data.decode("utf-8")

    assert "html-templates" in html
    assert "/propuesta/vista-previa" not in html


# --------------------------------------------------------------------------
# A saved CV is as printable as the draft one
# --------------------------------------------------------------------------


def test_un_cv_guardado_tambien_se_puede_ver_maquetado(tmp_path: Path):
    root = tmp_path / "perfil"
    _perfil_en_disco(root)
    app = create_app(
        raiz_perfil=root,
        settings_path=tmp_path / "ajustes.json",
        html_templates_root=PLANTILLAS_HTML,
    )
    app.config["TESTING"] = True
    cv = SavedCV(
        id="acme-backend-2026-09-06",
        date=date(2026, 9, 6),
        company="ACME",
        position="Backend",
        posting="Buscamos Python.",
        proposal=_propuesta(2),
        status=CVStatus.DRAFT,
    )
    archivo.save(root, cv)
    cliente = app.test_client()

    assert f"/cvs/{cv.id}/vista-previa" in cliente.get(f"/cvs/{cv.id}").data.decode("utf-8")
    respuesta = cliente.get(f"/cvs/{cv.id}/vista-previa?plantilla_id={PLANTILLA}")
    assert respuesta.status_code == 200
    assert "Rol Uno · Empresa A" in respuesta.data.decode("utf-8")


# --------------------------------------------------------------------------
# Corporativa Clásica fills the page whether it holds 3, 4 or 5 experiences
# (actual fill is measured on a printed PDF, not asserted here — see
# `bitacora/llenar-la-hoja.md`). What a unit test can pin down is the markup
# contract the CSS depends on: a spacer between every pair of consecutive
# entries, none before the first or after the last, and a scale class that
# names the exact count so `corporativa-clasica.css` can size that case's
# text without guessing it from the DOM.
# --------------------------------------------------------------------------


def test_hay_un_espaciador_entre_cada_par_de_experiencias_consecutivas(tmp_path: Path):
    for cuantas in (3, 4, 5):
        html = _vista_previa(_cliente(tmp_path, n_experiencias=cuantas), capacidad=cuantas)

        assert html.count('class="cv-espaciador"') == cuantas - 1


def test_una_sola_experiencia_no_lleva_ningun_espaciador(tmp_path: Path):
    html = _vista_previa(_cliente(tmp_path, n_experiencias=1))

    assert "cv-espaciador" not in html


def test_la_columna_principal_lleva_la_clase_de_escala_de_su_propio_numero_de_experiencias(tmp_path: Path):
    for cuantas in (3, 4, 5):
        html = _vista_previa(_cliente(tmp_path, n_experiencias=cuantas), capacidad=cuantas)

        assert f"cv-escala-{cuantas}" in html
        for otras in (3, 4, 5):
            if otras != cuantas:
                assert f"cv-escala-{otras}" not in html


def test_no_se_puede_bajar_del_minimo_que_declara_la_plantilla(tmp_path: Path):
    """Corporativa Clásica holds three experiences at least: below that the
    sheet is mostly empty however much the type is scaled up. The server
    clamps it, so editing the query string cannot get past it either."""
    cliente = _cliente(tmp_path, n_experiencias=5)

    html = _vista_previa(cliente, capacidad=1)

    assert "Bullet de exp-1" in html
    assert "Bullet de exp-2" in html
    assert "Bullet de exp-3" in html
    assert "Bullet de exp-4" not in html
