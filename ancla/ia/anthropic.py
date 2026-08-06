"""Cliente de Anthropic (Claude).

A diferencia de Groq y de los proveedores que cuelgan de
`ia/openai_compatible.py`, Claude no habla el formato de chat completions de
OpenAI — usa su propia Messages API, con el mensaje de sistema como parámetro
aparte en vez de un mensaje más. Por eso necesita su propio módulo, tal y
como ya anticipaba `ia/groq.py`: "cambiar de proveedor es escribir otro
módulo como este y cumplir el Protocol de ia.cliente".

La clave es siempre del usuario y vive solo en su máquina, igual que en los
demás clientes de `ia/`.
"""
from __future__ import annotations

from flask_babel import gettext as _

from ancla.ia.cliente import ErrorIA

TIMEOUT_SEGUNDOS = 120

# Igual que en groq.py: una adaptación es una sola llamada con el catálogo
# del perfil entero dentro, así que conviene margen amplio en la respuesta.
MAX_TOKENS_RESPUESTA = 4000

URL_CONSEGUIR_CLAVE = "https://console.anthropic.com/settings/keys"


class ClienteAnthropic:
    """Implementa `ia.cliente.ClienteIA` sobre la Messages API de Anthropic.

    No guarda estado entre llamadas: cada adaptación es independiente.
    """

    def __init__(self, clave: str = "", modelo: str = "", temperatura: float = 0.2) -> None:
        self.clave = (clave or "").strip()
        self.modelo = (modelo or "").strip()
        # Temperatura baja a propósito: la tarea es elegir de un catálogo
        # cerrado y justificarlo, no redactar — mismo criterio que en Groq.
        self.temperatura = temperatura

    def disponible(self) -> bool:
        """True si hay clave y modelo configurados. No comprueba que sean
        válidos: eso solo se sabe al llamar."""
        return bool(self.clave and self.modelo)

    def completar(self, sistema: str, usuario: str) -> str:
        if not self.disponible():
            raise ErrorIA(
                _(
                    "Todavía no has configurado tu clave y tu modelo de Anthropic. Ve a "
                    "Ajustes y rellena los dos; puedes conseguir una clave en %(url)s.",
                    url=URL_CONSEGUIR_CLAVE,
                )
            )
        respuesta = self._pedir(sistema, usuario)
        if not respuesta.strip():
            raise ErrorIA(
                _("Anthropic ha devuelto una respuesta vacía. Vuelve a generar la propuesta.")
            )
        return respuesta

    # ----------------------------------------------------------------------

    def _pedir(self, sistema: str, usuario: str) -> str:
        cliente = self._sdk()
        try:
            respuesta = cliente.messages.create(
                model=self.modelo,
                max_tokens=MAX_TOKENS_RESPUESTA,
                temperature=self.temperatura,
                system=sistema,
                messages=[{"role": "user", "content": usuario}],
            )
        except Exception as exc:
            raise ErrorIA(self._explicar(exc)) from exc

        if respuesta.stop_reason == "refusal":
            raise ErrorIA(
                _(
                    "Anthropic ha rechazado esta petición por motivos de seguridad. "
                    "Revisa el texto de la vacante o del CV e inténtalo de nuevo."
                )
            )
        texto = next((bloque.text for bloque in respuesta.content if bloque.type == "text"), "")
        if not texto:
            raise ErrorIA(
                _(
                    "Anthropic ha devuelto una respuesta sin texto. Vuelve a generar la propuesta."
                )
            )
        return texto

    def _sdk(self):
        """Importa el SDK aquí y no arriba: la app tiene que poder arrancar y
        enseñar la pantalla de Ajustes aunque falte la dependencia."""
        try:
            import anthropic
        except ImportError as exc:
            raise ErrorIA(
                _("Falta la librería «anthropic». Instálala con: pip install -r requirements.txt")
            ) from exc
        return anthropic.Anthropic(api_key=self.clave, timeout=TIMEOUT_SEGUNDOS)

    def _explicar(self, exc: Exception) -> str:
        """A diferencia de groq.py y openai_compatible.py, aquí sí se mira la
        clase del error: el SDK de Anthropic es uno solo, bien documentado y
        con excepciones tipadas — no hay varios proveedores detrás del mismo
        SDK cambiando de forma sin avisar."""
        import anthropic

        if isinstance(exc, anthropic.AuthenticationError):
            return _("Tu clave de Anthropic no es válida o ha caducado. Revísala en Ajustes.")
        if isinstance(exc, anthropic.NotFoundError):
            return _("El modelo configurado no existe en Anthropic. Revísalo en Ajustes.")
        if isinstance(exc, anthropic.RateLimitError):
            return _(
                "Has agotado la cuota de Anthropic por ahora. Espera un rato y vuelve a "
                "intentarlo."
            )
        if isinstance(exc, anthropic.APIConnectionError):
            return _("No se ha podido contactar con Anthropic. Comprueba tu conexión a internet.")
        return _("Anthropic ha devuelto un error: %(error)s", error=exc)
