"""Anthropic (Claude) client.

Unlike Groq and the providers that hang off `ia/openai_compatible.py`,
Claude does not speak OpenAI's chat completions format — it uses its own
Messages API, with the system message as a separate parameter rather than
another message. That is why it needs its own module, exactly as
`ia/groq.py` already anticipated: "switching providers means writing
another module like this one that satisfies ia.cliente's Protocol".

The key always belongs to the user and lives only on their machine, same as
the rest of the `ia/` clients.
"""
from __future__ import annotations

from flask_babel import gettext as _

from ancla.ai.client import AIError

TIMEOUT_SEGUNDOS = 120

# Same as groq.py: one adaptation is a single call carrying the whole
# profile catalog, so a generous response margin is worth having.
MAX_TOKENS_RESPUESTA = 4000

URL_CONSEGUIR_CLAVE = "https://console.anthropic.com/settings/keys"


class AnthropicClient:
    """Implements `ia.cliente.ClienteIA` over Anthropic's Messages API.

    Holds no state between calls: each adaptation is independent.
    """

    def __init__(self, clave: str = "", modelo: str = "", temperatura: float = 0.2) -> None:
        self.clave = (clave or "").strip()
        self.modelo = (modelo or "").strip()
        # Deliberately low temperature: the task is choosing from a closed
        # catalog and justifying it, not composing prose — same reasoning as Groq.
        self.temperatura = temperatura

    def available(self) -> bool:
        """True if both a key and a model are configured. Does not check
        that they are valid: that is only known once a call is made."""
        return bool(self.clave and self.modelo)

    def complete(self, sistema: str, usuario: str) -> str:
        if not self.available():
            raise AIError(
                _(
                    "Todavía no has configurado tu clave y tu modelo de Anthropic. Ve a "
                    "Ajustes y rellena los dos; puedes conseguir una clave en %(url)s.",
                    url=URL_CONSEGUIR_CLAVE,
                )
            )
        respuesta = self._request(sistema, usuario)
        if not respuesta.strip():
            raise AIError(
                _("Anthropic ha devuelto una respuesta vacía. Vuelve a generar la propuesta.")
            )
        return respuesta

    # ----------------------------------------------------------------------

    def _request(self, sistema: str, usuario: str) -> str:
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
            raise AIError(self._explain(exc)) from exc

        if respuesta.stop_reason == "refusal":
            raise AIError(
                _(
                    "Anthropic ha rechazado esta petición por motivos de seguridad. "
                    "Revisa el texto de la vacante o del CV e inténtalo de nuevo."
                )
            )
        texto = next((bloque.text for bloque in respuesta.content if bloque.type == "text"), "")
        if not texto:
            raise AIError(
                _(
                    "Anthropic ha devuelto una respuesta sin texto. Vuelve a generar la propuesta."
                )
            )
        return texto

    def _sdk(self):
        """Imports the SDK here, not at the top: the app has to be able to
        start and show the Settings screen even if this dependency is missing."""
        try:
            import anthropic
        except ImportError as exc:
            raise AIError(
                _("Falta la librería «anthropic». Instálala con: pip install -r requirements.txt")
            ) from exc
        return anthropic.Anthropic(api_key=self.clave, timeout=TIMEOUT_SEGUNDOS)

    def _explain(self, exc: Exception) -> str:
        """Unlike groq.py and openai_compatible.py, this one does inspect
        the error's class: Anthropic's SDK is a single one, well documented,
        with typed exceptions — there is no handful of providers behind the
        same SDK silently changing shape."""
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
