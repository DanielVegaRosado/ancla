"""Tests for the CV archive, the Groq client, and support."""
from __future__ import annotations

from datetime import date, time
from pathlib import Path

import pytest

from ancla.archive import repository, serialization
from ancla.ai.client import AIError
from ancla.ai.groq import GroqClient
from ancla.profile.errors import ProfileError
from ancla.profile.model import (
    CVStatus,
    Proposal,
    SavedCV,
    SelectedAboutMe,
    SelectedExperience,
)
from ancla.support import messages


def _cv(id: str = "2026-07-24_acme_data-engineer", **cambios) -> SavedCV:
    base = dict(
        id=id,
        date=date(2026, 7, 24),
        company="ACME",
        position="Data Engineer",
        posting="Buscamos alguien con Python y SQL.",
        proposal=Proposal(
            language="es",
            about_me=SelectedAboutMe(
                group_a=["machine learning", "LLMs", "datos"],
                group_b=["Python", "SQL", "Java"],
                text="Estudiante con conocimientos en machine learning...",
                reason="La vacante prioriza datos.",
            ),
            skills=["python", "sql"],
            skills_reason="Son los dos requisitos explícitos.",
            experiences=[SelectedExperience(id="ml-telco", reason="Encaja.")],
            gaps=["Kubernetes"],
        ),
    )
    return SavedCV(**{**base, **cambios})


# --------------------------------------------------------------------------
# Archive
# --------------------------------------------------------------------------


def test_guardar_y_leer_conserva_la_propuesta(tmp_path: Path):
    repository.save(tmp_path, _cv())
    recuperado = repository.list_all(tmp_path)[0]

    assert recuperado.company == "ACME"
    assert recuperado.date == date(2026, 7, 24)
    assert recuperado.proposal.skills == ["python", "sql"]
    assert recuperado.proposal.experiences[0].reason == "Encaja."
    assert recuperado.proposal.gaps == ["Kubernetes"]


def test_guardar_y_leer_conserva_la_hora(tmp_path: Path):
    repository.save(tmp_path, _cv(time=time(14, 32, 5)))
    recuperado = repository.list_all(tmp_path)[0]
    assert recuperado.time == time(14, 32, 5)


def test_un_cv_sin_hora_guardada_no_es_un_error():
    """CVs saved before this field existed have no `time` in the file: they
    still have to be readable, not break on."""
    datos_sin_hora = {
        "date": "2026-07-22",
        "company": "Marvell",
        "position": "Software Engineer",
        "status": "draft",
        "attachment": "",
        "notes": "",
        "posting": "texto",
        "proposal": {
            "language": "es",
            "about_me": {"group_a": [], "group_b": [], "text": "x", "reason": ""},
            "skills": [],
            "skills_reason": "",
            "experiences": [],
            "gaps": [],
        },
    }
    cv = serialization.parse_cv(datos_sin_hora, "2026-07-22_marvell_software-engineer")
    assert cv.time is None
    assert cv.company == "Marvell"


def test_una_hora_ilegible_se_ignora_en_vez_de_reventar():
    """If someone hand-edits the YAML and writes `time: 14:32:05` unquoted,
    PyYAML (YAML 1.1) can read it as a sexagesimal number, not as text."""
    assert serialization._parse_time(52325) is None
    assert serialization._parse_time("no es una hora") is None
    assert serialization._parse_time("") is None
    assert serialization._parse_time(None) is None


def test_el_archivo_guarda_ids_no_textos_del_perfil(tmp_path: Path):
    """The underlying rule: fixing the profile fixes CVs already saved."""
    repository.save(tmp_path, _cv())
    escrito = (tmp_path / "cvs" / "2026-07-24_acme_data-engineer.yaml").read_text("utf-8")

    assert "python" in escrito
    assert "ml-telco" in escrito
    # The experience's title lives in the profile, not here.
    assert "ML Developer" not in escrito


def test_listar_devuelve_del_mas_reciente_al_mas_antiguo(tmp_path: Path):
    repository.save(tmp_path, _cv(id="2026-07-01_uno", date=date(2026, 7, 1)))
    repository.save(tmp_path, _cv(id="2026-07-30_dos", date=date(2026, 7, 30)))

    assert [cv.id for cv in repository.list_all(tmp_path)] == [
        "2026-07-30_dos",
        "2026-07-01_uno",
    ]


def test_listar_sin_carpeta_no_es_un_error(tmp_path: Path):
    assert repository.list_all(tmp_path) == []


def test_un_cv_roto_no_tumba_la_lista(tmp_path: Path):
    """One row of a list is lost, not a whole CV: it is skipped and the rest continues."""
    repository.save(tmp_path, _cv())
    (tmp_path / "cvs" / "roto.yaml").write_text("esto: [no cierra", encoding="utf-8")

    assert len(repository.list_all(tmp_path)) == 1


def test_buscar_por_empresa_ignora_mayusculas_y_acentos(tmp_path: Path):
    repository.save(tmp_path, _cv(company="Telefónica"))

    assert len(repository.find_by_company(tmp_path, "TELEFONICA")) == 1
    assert repository.find_by_company(tmp_path, "otra") == []
    assert repository.find_by_company(tmp_path, "") == []


def test_cambiar_estado_no_toca_el_resto(tmp_path: Path):
    repository.save(tmp_path, _cv())
    repository.change_status(tmp_path, _cv().id, CVStatus.INTERVIEW)

    recuperado = repository.list_all(tmp_path)[0]
    assert recuperado.status is CVStatus.INTERVIEW
    assert recuperado.proposal.skills == ["python", "sql"]


def test_adjuntar_copia_el_archivo_sea_del_formato_que_sea(tmp_path: Path):
    repository.save(tmp_path, _cv())
    origen = tmp_path / "CV_final.docx"
    origen.write_bytes(b"contenido")

    destino = repository.attach(tmp_path, _cv().id, origen)

    assert destino.exists() and destino.suffix == ".docx"
    assert origen.exists(), "el original del usuario no se mueve ni se borra"
    assert repository.list_all(tmp_path)[0].attachment == destino.name


def test_un_id_con_travesia_de_rutas_no_escribe_fuera_del_perfil(tmp_path: Path):
    with pytest.raises(ProfileError):
        repository.save(tmp_path, _cv(id="../../fuera"))


def test_nuevo_id_no_pisa_uno_existente(tmp_path: Path):
    primero = repository.new_id(tmp_path, date(2026, 7, 24), "ACME", "Data Engineer")
    repository.save(tmp_path, _cv(id=primero))
    segundo = repository.new_id(tmp_path, date(2026, 7, 24), "ACME", "Data Engineer")

    assert primero == "2026-07-24_acme_data-engineer"
    assert segundo != primero


def test_nuevo_id_aguanta_una_empresa_sin_nombre(tmp_path: Path):
    assert repository.new_id(tmp_path, date(2026, 7, 24), "", "") == (
        "2026-07-24_sin-empresa"
    )


# --------------------------------------------------------------------------
# Groq client
# --------------------------------------------------------------------------


def test_sin_clave_no_esta_disponible_y_lo_dice_en_castellano():
    cliente = GroqClient(clave="")
    assert not cliente.available()

    with pytest.raises(AIError) as fallo:
        cliente.complete("sistema", "usuario")
    assert "Ajustes" in str(fallo.value)


def test_los_fallos_del_proveedor_se_traducen_a_algo_accionable():
    explicar = GroqClient._explain

    assert "clave" in explicar(Exception("Invalid API Key provided")).lower()
    assert "cuota" in explicar(Exception("rate limit exceeded")).lower()
    assert "conexi" in explicar(Exception("failed to connect")).lower()
    # What is not recognised is not dressed up as something else: shown as-is.
    assert "vaya cosa rara" in explicar(Exception("vaya cosa rara"))


def test_la_llamada_al_sdk_lleva_max_tokens_y_reasoning_effort_bajo(monkeypatch):
    """Checked live against the real API (not here, this never touches the
    network): without `reasoning_effort`, the model spent 79% of
    `max_tokens` "reasoning" and ran out of room to finish the JSON. This
    test only pins that both parameters genuinely reach the SDK call, so no
    one drops them by accident while touching this file."""
    import ancla.ai.groq as modulo_groq

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

    monkeypatch.setattr(GroqClient, "_sdk", lambda self: _SdkFalso())

    GroqClient(clave="gsk_prueba").complete("sistema", "usuario")

    assert len(llamadas) == 1
    assert llamadas[0]["max_tokens"] == modulo_groq.MAX_TOKENS_RESPUESTA
    assert llamadas[0]["reasoning_effort"] == modulo_groq.REASONING_EFFORT == "low"


def test_una_peticion_demasiado_grande_no_se_confunde_con_cuota_agotada():
    """Real case reproduced against the Groq API: the error comes with
    "code": "rate_limit_exceeded" (underscore), which must not be confused
    with "rate limit" (space) for quota exhausted by request count — they
    are different problems and the message has to say which one it is."""
    explicar = GroqClient._explain
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
# Support
# --------------------------------------------------------------------------


def test_el_mensaje_se_guarda_siempre_en_local(tmp_path: Path):
    ruta = messages.save_message(tmp_path, "No arranca", "Se queda en blanco.")

    assert ruta.exists()
    contenido = ruta.read_text("utf-8")
    assert "No arranca" in contenido and "Se queda en blanco." in contenido


def test_el_diagnostico_no_incluye_nada_del_perfil():
    """A CV can never end up in a public issue for reporting a broken button."""
    diagnostico = messages.collect(proveedor="groq", modelo="gpt-oss-120b")
    campos = set(vars(diagnostico))

    assert campos == {"version", "sistema", "python", "proveedor", "modelo", "error"}
    assert "clave" not in diagnostico.as_text().lower()


def test_las_dos_salidas_llevan_el_mensaje_y_ningun_secreto():
    incidencia = messages.issue_url("Fallo", "El botón no responde")
    correo = messages.email_url("Fallo", "El botón no responde")

    assert incidencia.startswith(messages.REPOSITORIO + "/issues/new?")
    assert correo.startswith("mailto:")
    for url in (incidencia, correo):
        assert "bot%C3%B3n" in url or "bot%C3%B3n".lower() in url.lower()
        assert "api_key" not in url.lower() and "password" not in url.lower()


def test_un_mensaje_larguisimo_se_recorta_avisando():
    cuerpo = messages.issue_url("Fallo", "a" * 20000)

    assert len(cuerpo) < 20000
    assert "recortado" in cuerpo or "recort" in cuerpo


def test_el_tipo_por_defecto_es_sugerencia():
    """The project receiving feedback well starts with the default value:
    it invites writing in without first having to have a bug."""
    assert messages.TIPO_POR_DEFECTO == "sugerencia"


def test_el_titulo_lleva_la_etiqueta_del_tipo(tmp_path: Path):
    incidencia = messages.issue_url("Duplicar experiencia", "x", tipo="sugerencia")
    correo = messages.email_url("No arranca", "x", tipo="problema")
    assert "Sugerencia" in incidencia
    assert "Problema" in correo


def test_sin_asunto_el_titulo_es_solo_la_etiqueta():
    """Does not ask to make up a subject: without one, the title is just
    the type's label, and that is still a valid issue title."""
    incidencia = messages.issue_url("", "x", tipo="sugerencia")
    assert "Sugerencia" in incidencia


def test_un_tipo_desconocido_cae_al_por_defecto_sin_reventar():
    """Same as `_a_estado` in the CV archive: an unexpected value is not an
    error, it is treated as the normal case."""
    incidencia = messages.issue_url("x", "y", tipo="algo-que-no-existe")
    assert "Sugerencia" in incidencia


def test_guardar_mensaje_persiste_el_tipo_elegido(tmp_path: Path):
    ruta = messages.save_message(tmp_path, "x", "y", tipo="problema")
    contenido = ruta.read_text("utf-8")
    assert "tipo: problema" in contenido
