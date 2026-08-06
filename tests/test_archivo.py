"""Tests del archivo de CVs, del cliente de Groq y del soporte."""
from __future__ import annotations

from datetime import date, time
from pathlib import Path

import pytest

from ancla.archivo import repositorio, serializacion
from ancla.ia.cliente import ErrorIA
from ancla.ia.groq import ClienteGroq
from ancla.perfil.errores import ErrorPerfil
from ancla.perfil.modelo import (
    CVGuardado,
    EstadoCV,
    ExperienciaSeleccionada,
    Propuesta,
    SeleccionSobreMi,
)
from ancla.soporte import mensajes


def _cv(id: str = "2026-07-24_acme_data-engineer", **cambios) -> CVGuardado:
    base = dict(
        id=id,
        fecha=date(2026, 7, 24),
        empresa="ACME",
        puesto="Data Engineer",
        vacante="Buscamos alguien con Python y SQL.",
        propuesta=Propuesta(
            idioma="es",
            sobre_mi=SeleccionSobreMi(
                grupo_a=["machine learning", "LLMs", "datos"],
                grupo_b=["Python", "SQL", "Java"],
                texto="Estudiante con conocimientos en machine learning...",
                motivo="La vacante prioriza datos.",
            ),
            skills=["python", "sql"],
            motivo_skills="Son los dos requisitos explícitos.",
            experiencias=[ExperienciaSeleccionada(id="ml-telco", motivo="Encaja.")],
            huecos=["Kubernetes"],
        ),
    )
    return CVGuardado(**{**base, **cambios})


# --------------------------------------------------------------------------
# Archivo
# --------------------------------------------------------------------------


def test_guardar_y_leer_conserva_la_propuesta(tmp_path: Path):
    repositorio.guardar(tmp_path, _cv())
    recuperado = repositorio.listar(tmp_path)[0]

    assert recuperado.empresa == "ACME"
    assert recuperado.fecha == date(2026, 7, 24)
    assert recuperado.propuesta.skills == ["python", "sql"]
    assert recuperado.propuesta.experiencias[0].motivo == "Encaja."
    assert recuperado.propuesta.huecos == ["Kubernetes"]


def test_guardar_y_leer_conserva_la_hora(tmp_path: Path):
    repositorio.guardar(tmp_path, _cv(hora=time(14, 32, 5)))
    recuperado = repositorio.listar(tmp_path)[0]
    assert recuperado.hora == time(14, 32, 5)


def test_un_cv_sin_hora_guardada_no_es_un_error():
    """Los CV guardados antes de que existiera este campo no tienen `hora` en
    el fichero: hay que seguir leyéndolos, no romper con ellos."""
    datos_sin_hora = {
        "fecha": "2026-07-22",
        "empresa": "Marvell",
        "puesto": "Software Engineer",
        "estado": "borrador",
        "adjunto": "",
        "notas": "",
        "vacante": "texto",
        "propuesta": {
            "idioma": "es",
            "sobre_mi": {"grupo_a": [], "grupo_b": [], "texto": "x", "motivo": ""},
            "skills": [],
            "motivo_skills": "",
            "experiencias": [],
            "huecos": [],
        },
    }
    cv = serializacion.a_cv(datos_sin_hora, "2026-07-22_marvell_software-engineer")
    assert cv.hora is None
    assert cv.empresa == "Marvell"


def test_una_hora_ilegible_se_ignora_en_vez_de_reventar():
    """Si alguien edita el YAML a mano y dice «hora: 14:32:05» sin comillas,
    PyYAML (YAML 1.1) puede leerlo como número sexagesimal, no como texto."""
    assert serializacion._a_hora(52325) is None
    assert serializacion._a_hora("no es una hora") is None
    assert serializacion._a_hora("") is None
    assert serializacion._a_hora(None) is None


def test_el_archivo_guarda_ids_no_textos_del_perfil(tmp_path: Path):
    """La regla de fondo: corregir el perfil corrige los CV ya guardados."""
    repositorio.guardar(tmp_path, _cv())
    escrito = (tmp_path / "cvs" / "2026-07-24_acme_data-engineer.yaml").read_text("utf-8")

    assert "python" in escrito
    assert "ml-telco" in escrito
    # El título de la experiencia vive en el perfil, no aquí.
    assert "ML Developer" not in escrito


def test_listar_devuelve_del_mas_reciente_al_mas_antiguo(tmp_path: Path):
    repositorio.guardar(tmp_path, _cv(id="2026-07-01_uno", fecha=date(2026, 7, 1)))
    repositorio.guardar(tmp_path, _cv(id="2026-07-30_dos", fecha=date(2026, 7, 30)))

    assert [cv.id for cv in repositorio.listar(tmp_path)] == [
        "2026-07-30_dos",
        "2026-07-01_uno",
    ]


def test_listar_sin_carpeta_no_es_un_error(tmp_path: Path):
    assert repositorio.listar(tmp_path) == []


def test_un_cv_roto_no_tumba_la_lista(tmp_path: Path):
    """Se pierde una fila de una lista, no un CV entero: se omite y se sigue."""
    repositorio.guardar(tmp_path, _cv())
    (tmp_path / "cvs" / "roto.yaml").write_text("esto: [no cierra", encoding="utf-8")

    assert len(repositorio.listar(tmp_path)) == 1


def test_buscar_por_empresa_ignora_mayusculas_y_acentos(tmp_path: Path):
    repositorio.guardar(tmp_path, _cv(empresa="Telefónica"))

    assert len(repositorio.buscar_por_empresa(tmp_path, "TELEFONICA")) == 1
    assert repositorio.buscar_por_empresa(tmp_path, "otra") == []
    assert repositorio.buscar_por_empresa(tmp_path, "") == []


def test_cambiar_estado_no_toca_el_resto(tmp_path: Path):
    repositorio.guardar(tmp_path, _cv())
    repositorio.cambiar_estado(tmp_path, _cv().id, EstadoCV.ENTREVISTA)

    recuperado = repositorio.listar(tmp_path)[0]
    assert recuperado.estado is EstadoCV.ENTREVISTA
    assert recuperado.propuesta.skills == ["python", "sql"]


def test_adjuntar_copia_el_archivo_sea_del_formato_que_sea(tmp_path: Path):
    repositorio.guardar(tmp_path, _cv())
    origen = tmp_path / "CV_final.docx"
    origen.write_bytes(b"contenido")

    destino = repositorio.adjuntar(tmp_path, _cv().id, origen)

    assert destino.exists() and destino.suffix == ".docx"
    assert origen.exists(), "el original del usuario no se mueve ni se borra"
    assert repositorio.listar(tmp_path)[0].adjunto == destino.name


def test_un_id_con_travesia_de_rutas_no_escribe_fuera_del_perfil(tmp_path: Path):
    with pytest.raises(ErrorPerfil):
        repositorio.guardar(tmp_path, _cv(id="../../fuera"))


def test_nuevo_id_no_pisa_uno_existente(tmp_path: Path):
    primero = repositorio.nuevo_id(tmp_path, date(2026, 7, 24), "ACME", "Data Engineer")
    repositorio.guardar(tmp_path, _cv(id=primero))
    segundo = repositorio.nuevo_id(tmp_path, date(2026, 7, 24), "ACME", "Data Engineer")

    assert primero == "2026-07-24_acme_data-engineer"
    assert segundo != primero


def test_nuevo_id_aguanta_una_empresa_sin_nombre(tmp_path: Path):
    assert repositorio.nuevo_id(tmp_path, date(2026, 7, 24), "", "") == (
        "2026-07-24_sin-empresa"
    )


# --------------------------------------------------------------------------
# Cliente de Groq
# --------------------------------------------------------------------------


def test_sin_clave_no_esta_disponible_y_lo_dice_en_castellano():
    cliente = ClienteGroq(clave="")
    assert not cliente.disponible()

    with pytest.raises(ErrorIA) as fallo:
        cliente.completar("sistema", "usuario")
    assert "Ajustes" in str(fallo.value)


def test_los_fallos_del_proveedor_se_traducen_a_algo_accionable():
    explicar = ClienteGroq._explicar

    assert "clave" in explicar(Exception("Invalid API Key provided")).lower()
    assert "cuota" in explicar(Exception("rate limit exceeded")).lower()
    assert "conexi" in explicar(Exception("failed to connect")).lower()
    # Lo que no se reconoce no se disfraza: se enseña tal cual.
    assert "vaya cosa rara" in explicar(Exception("vaya cosa rara"))


def test_la_llamada_al_sdk_lleva_max_tokens_y_reasoning_effort_bajo(monkeypatch):
    """Verificado en vivo contra la API real (no aquí, que no toca la red):
    sin `reasoning_effort`, el modelo gastaba el 79% de `max_tokens`
    "razonando" y se quedaba sin espacio para terminar el JSON. Este test
    solo fija que los dos parámetros llegan de verdad a la llamada del SDK,
    para que nadie los quite sin darse cuenta al tocar este fichero."""
    import ancla.ia.groq as modulo_groq

    llamadas = []

    class _Mensaje:
        content = "contenido de prueba"

    class _Eleccion:
        message = _Mensaje()

    class _Completado:
        choices = [_Eleccion()]

    class _Completions:
        def create(self, **kwargs):
            llamadas.append(kwargs)
            return _Completado()

    class _Chat:
        completions = _Completions()

    class _SdkFalso:
        chat = _Chat()

    monkeypatch.setattr(ClienteGroq, "_sdk", lambda self: _SdkFalso())

    ClienteGroq(clave="gsk_prueba").completar("sistema", "usuario")

    assert len(llamadas) == 1
    assert llamadas[0]["max_tokens"] == modulo_groq.MAX_TOKENS_RESPUESTA
    assert llamadas[0]["reasoning_effort"] == modulo_groq.REASONING_EFFORT == "low"


def test_una_peticion_demasiado_grande_no_se_confunde_con_cuota_agotada():
    """Caso real reproducido contra la API de Groq: el error viene con
    "code": "rate_limit_exceeded" (guion bajo), que no debe confundirse con
    el "rate limit" (con espacio) de la cuota agotada por número de
    peticiones — son problemas distintos y el mensaje tiene que decir cuál es."""
    explicar = ClienteGroq._explicar
    error_real = Exception(
        "Error code: 413 - {'error': {'message': 'Request too large for model "
        "`openai/gpt-oss-120b` ... on tokens per minute (TPM): Limit 8000, "
        "Requested 8751, please reduce your message size', 'type': 'tokens', "
        "'code': 'rate_limit_exceeded'}}"
    )
    mensaje = explicar(error_real)
    assert "demasiado grande" in mensaje.lower()
    assert "cuota" not in mensaje.lower()


# --------------------------------------------------------------------------
# Soporte
# --------------------------------------------------------------------------


def test_el_mensaje_se_guarda_siempre_en_local(tmp_path: Path):
    ruta = mensajes.guardar_mensaje(tmp_path, "No arranca", "Se queda en blanco.")

    assert ruta.exists()
    contenido = ruta.read_text("utf-8")
    assert "No arranca" in contenido and "Se queda en blanco." in contenido


def test_el_diagnostico_no_incluye_nada_del_perfil():
    """Un CV no puede acabar en una incidencia pública por reportar un botón roto."""
    diagnostico = mensajes.recoger(proveedor="groq", modelo="gpt-oss-120b")
    campos = set(vars(diagnostico))

    assert campos == {"version", "sistema", "python", "proveedor", "modelo", "error"}
    assert "clave" not in diagnostico.como_texto().lower()


def test_las_dos_salidas_llevan_el_mensaje_y_ningun_secreto():
    incidencia = mensajes.url_incidencia("Fallo", "El botón no responde")
    correo = mensajes.url_correo("Fallo", "El botón no responde")

    assert incidencia.startswith(mensajes.REPOSITORIO + "/issues/new?")
    assert correo.startswith("mailto:")
    for url in (incidencia, correo):
        assert "bot%C3%B3n" in url or "bot%C3%B3n".lower() in url.lower()
        assert "api_key" not in url.lower() and "password" not in url.lower()


def test_un_mensaje_larguisimo_se_recorta_avisando():
    cuerpo = mensajes.url_incidencia("Fallo", "a" * 20000)

    assert len(cuerpo) < 20000
    assert "recortado" in cuerpo or "recort" in cuerpo


def test_el_tipo_por_defecto_es_sugerencia():
    """Que el proyecto reciba bien el feedback empieza en el valor por
    defecto: invita a escribir sin tener que tener un bug primero."""
    assert mensajes.TIPO_POR_DEFECTO == "sugerencia"


def test_el_titulo_lleva_la_etiqueta_del_tipo(tmp_path: Path):
    incidencia = mensajes.url_incidencia("Duplicar experiencia", "x", tipo="sugerencia")
    correo = mensajes.url_correo("No arranca", "x", tipo="problema")
    assert "Sugerencia" in incidencia
    assert "Problema" in correo


def test_sin_asunto_el_titulo_es_solo_la_etiqueta():
    """No pide inventar un asunto: sin él, el título es solo la etiqueta del
    tipo, y sigue siendo un título válido para la incidencia."""
    incidencia = mensajes.url_incidencia("", "x", tipo="sugerencia")
    assert "Sugerencia" in incidencia


def test_un_tipo_desconocido_cae_al_por_defecto_sin_reventar():
    """Igual que `_a_estado` en el archivo de CVs: un valor inesperado no es
    un error, se trata como el caso normal."""
    incidencia = mensajes.url_incidencia("x", "y", tipo="algo-que-no-existe")
    assert "Sugerencia" in incidencia


def test_guardar_mensaje_persiste_el_tipo_elegido(tmp_path: Path):
    ruta = mensajes.guardar_mensaje(tmp_path, "x", "y", tipo="problema")
    contenido = ruta.read_text("utf-8")
    assert "tipo: problema" in contenido
