"""Tests de la extracción de empresa y puesto.

Es una heurística sobre texto que pega gente real desde portales distintos, así
que el listón es doble: acertar en los formatos habituales y, sobre todo, **no
inventarse un dato cuando no lo ve claro**. Un campo vacío se corrige en dos
segundos; un CV archivado con la empresa equivocada, no.
"""
from __future__ import annotations

from cv_adaptativo.vacante.analisis import extraer_datos


def test_etiquetas_explicitas_en_español():
    datos = extraer_datos("Empresa: Nubelia\nPuesto: Ingeniero de Datos\n\nBuscamos...")
    assert datos.empresa == "Nubelia"
    assert datos.puesto == "Ingeniero de Datos"


def test_etiquetas_explicitas_en_ingles():
    datos = extraer_datos("Company: Nubelia\nJob title: Data Engineer")
    assert datos.empresa == "Nubelia"
    assert datos.puesto == "Data Engineer"


def test_etiquetas_en_negrita_de_markdown():
    datos = extraer_datos("**Empresa:** Nubelia\n**Cargo:** Backend Developer")
    assert datos.empresa == "Nubelia"
    assert datos.puesto == "Backend Developer"


def test_cabecera_tipica_de_portal():
    datos = extraer_datos(
        "Backend Developer\nNubelia\nMadrid, España · Remoto\n\nSobre el puesto..."
    )
    assert datos.puesto == "Backend Developer"
    assert datos.empresa == "Nubelia"


def test_no_confunde_una_ubicacion_con_la_empresa():
    datos = extraer_datos("Ingeniero de Software\nMadrid, España\nPublicado hace 2 días")
    assert datos.puesto == "Ingeniero de Software"
    assert datos.empresa == ""


def test_no_confunde_la_modalidad_con_la_empresa():
    datos = extraer_datos("Data Engineer\nRemoto · Jornada completa")
    assert datos.puesto == "Data Engineer"
    assert datos.empresa == ""


def test_empresa_en_una_frase_de_bienvenida():
    datos = extraer_datos("Únete a Nubelia y ayúdanos a construir la nueva plataforma.")
    assert datos.empresa == "Nubelia"


def test_empresa_en_una_frase_de_busqueda():
    datos = extraer_datos("Nubelia busca un ingeniero de datos para su equipo.")
    assert datos.empresa == "Nubelia"


def test_no_toma_una_frase_entera_como_puesto():
    datos = extraer_datos("Nubelia busca un ingeniero de datos para su equipo.")
    assert datos.puesto == ""


def test_recorta_los_adornos_del_portal():
    datos = extraer_datos("Puesto: Backend Developer (m/f/d)\nEmpresa: Nubelia · Madrid")
    assert datos.puesto == "Backend Developer"
    assert datos.empresa == "Nubelia"


def test_acepta_una_razon_social_con_coma():
    assert extraer_datos("Empresa: Nubelia, S.L.").empresa == "Nubelia, S.L."


def test_el_filtro_de_ruido_tambien_descarta_puestos():
    # Coste conocido y aceptado: el mismo filtro que evita archivar un CV a
    # nombre de "Jornada completa" se lleva por delante un puesto legítimo que
    # lleve la modalidad pegada. Preferimos vacío a un dato sucio; queda fijado
    # aquí para que el día que se cambie sea una decisión, no un accidente.
    assert extraer_datos("Puesto: Desarrollador backend remoto").puesto == ""
    # Entre paréntesis sí se recorta, que es como suele venir.
    assert (
        extraer_datos("Puesto: Desarrollador backend (remoto)").puesto
        == "Desarrollador backend"
    )


def test_texto_sin_pistas_no_devuelve_nada():
    datos = extraer_datos(
        "Se valorará experiencia previa y ganas de aprender en un entorno dinámico."
    )
    assert datos.empresa == ""
    assert datos.puesto == ""


def test_texto_vacio_no_revienta():
    datos = extraer_datos("")
    assert datos.empresa == ""
    assert datos.puesto == ""


def test_ignora_lo_que_hay_muy_por_debajo_de_la_cabecera():
    texto = "\n".join(["Descripción de la oferta"] + ["relleno"] * 60 + ["Empresa: Tardía"])
    assert extraer_datos(texto).empresa == ""
