"""Tests for company and position extraction.

It is a heuristic over text that real people paste in from different job
boards, so the bar is twofold: getting the usual formats right and, above
all, **never inventing a value when it isn't clear**. An empty field is
fixed in two seconds; a CV archived under the wrong company is not.
"""
from __future__ import annotations

from ancla.posting.analysis import extract_data


def test_etiquetas_explicitas_en_español():
    datos = extract_data("Empresa: Nubelia\nPuesto: Ingeniero de Datos\n\nBuscamos...")
    assert datos.company == "Nubelia"
    assert datos.position == "Ingeniero de Datos"


def test_etiquetas_explicitas_en_ingles():
    datos = extract_data("Company: Nubelia\nJob title: Data Engineer")
    assert datos.company == "Nubelia"
    assert datos.position == "Data Engineer"


def test_etiquetas_en_negrita_de_markdown():
    datos = extract_data("**Empresa:** Nubelia\n**Cargo:** Backend Developer")
    assert datos.company == "Nubelia"
    assert datos.position == "Backend Developer"


def test_cabecera_tipica_de_portal():
    datos = extract_data(
        "Backend Developer\nNubelia\nMadrid, España · Remoto\n\nSobre el puesto..."
    )
    assert datos.position == "Backend Developer"
    assert datos.company == "Nubelia"


def test_no_confunde_una_ubicacion_con_la_empresa():
    datos = extract_data("Ingeniero de Software\nMadrid, España\nPublicado hace 2 días")
    assert datos.position == "Ingeniero de Software"
    assert datos.company == ""


def test_no_confunde_la_modalidad_con_la_empresa():
    datos = extract_data("Data Engineer\nRemoto · Jornada completa")
    assert datos.position == "Data Engineer"
    assert datos.company == ""


def test_empresa_en_una_frase_de_bienvenida():
    datos = extract_data("Únete a Nubelia y ayúdanos a construir la nueva plataforma.")
    assert datos.company == "Nubelia"


def test_empresa_en_una_frase_de_busqueda():
    datos = extract_data("Nubelia busca un ingeniero de datos para su equipo.")
    assert datos.company == "Nubelia"


def test_no_toma_una_frase_entera_como_puesto():
    datos = extract_data("Nubelia busca un ingeniero de datos para su equipo.")
    assert datos.position == ""


def test_recorta_los_adornos_del_portal():
    datos = extract_data("Puesto: Backend Developer (m/f/d)\nEmpresa: Nubelia · Madrid")
    assert datos.position == "Backend Developer"
    assert datos.company == "Nubelia"


def test_acepta_una_razon_social_con_coma():
    assert extract_data("Empresa: Nubelia, S.L.").company == "Nubelia, S.L."


def test_el_filtro_de_ruido_tambien_descarta_puestos():
    # Known, accepted cost: the same filter that stops a CV from being
    # archived under "Full time" also strips a legitimate position that has
    # the work mode stuck to it. We prefer empty over a dirty value; pinned
    # down here so that changing it one day is a decision, not an accident.
    assert extract_data("Puesto: Desarrollador backend remoto").position == ""
    # Inside parentheses it does get trimmed, which is how it usually comes.
    assert (
        extract_data("Puesto: Desarrollador backend (remoto)").position
        == "Desarrollador backend"
    )


def test_texto_sin_pistas_no_devuelve_nada():
    datos = extract_data(
        "Se valorará experiencia previa y ganas de aprender en un entorno dinámico."
    )
    assert datos.company == ""
    assert datos.position == ""


def test_texto_vacio_no_revienta():
    datos = extract_data("")
    assert datos.company == ""
    assert datos.position == ""


def test_ignora_lo_que_hay_muy_por_debajo_de_la_cabecera():
    texto = "\n".join(["Descripción de la oferta"] + ["relleno"] * 60 + ["Empresa: Tardía"])
    assert extract_data(texto).company == ""
