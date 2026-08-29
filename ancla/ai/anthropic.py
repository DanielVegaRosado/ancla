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
# Anthropic has no free tier: a brand new key with no credit bought
# fails on the very first call, and the API says so with a 400 rather
# than with an authentication error — which is why the key looks fine
# and the failure does not.
URL_COMPRAR_CREDITO = "https://console.anthropic.com/settings/billing"


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
                    "Ve a Ajustes y rellena la clave y el modelo de Anthropic: hacen "
                    "falta los dos. La clave se genera en %(url)s, y Anthropic cobra "
                    "por uso, así que la cuenta necesita saldo antes de la primera "
                    "propuesta.",
                    url=URL_CONSEGUIR_CLAVE,
                )
            )
        respuesta = self._request(sistema, usuario)
        if not respuesta.strip():
            raise AIError(
                _("Vuelve a generar la propuesta: Anthropic ha devuelto una respuesta vacía.")
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
                    "Revisa el texto de la vacante o del CV y vuelve a intentarlo: "
                    "Anthropic ha rechazado esta petición por motivos de seguridad."
                )
            )
        texto = next((bloque.text for bloque in respuesta.content if bloque.type == "text"), "")
        if not texto:
            raise AIError(
                _(
                    "Vuelve a generar la propuesta: Anthropic ha devuelto una respuesta sin texto."
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
        """Translates the SDK's failure into something the user can act on.

        Unlike groq.py and openai_compatible.py, this one does inspect the
        error's class: Anthropic's SDK is a single one, well documented,
        with typed exceptions — there is no handful of providers behind the
        same SDK silently changing shape. The one exception is running out
        of credit, which arrives as a plain 400 like any other bad request
        and can only be told apart by its text.

        Each message opens with what to do, not with what broke: whoever
        reads it is trying to get the app working, and the cause on its own
        is not something they can act on.
        """
        import anthropic

        if "credit balance" in str(exc).lower():
            return _(
                "Compra crédito en tu cuenta de Anthropic para poder usarla: %(url)s. "
                "Anthropic no tiene plan gratuito, así que una clave recién creada no "
                "funciona hasta que la cuenta tiene saldo. Si prefieres no pagar, "
                "cambia el proveedor a Groq en Ajustes: ese sí es gratis.",
                url=URL_COMPRAR_CREDITO,
            )
        if isinstance(exc, anthropic.AuthenticationError):
            return _(
                "Genera una clave nueva en %(url)s y pégala en Ajustes: la que hay "
                "puesta no le vale a Anthropic.",
                url=URL_CONSEGUIR_CLAVE,
            )
        if isinstance(exc, anthropic.PermissionDeniedError):
            return _(
                "Esta clave de Anthropic no tiene permiso para lo que hace la app. "
                "Genera otra desde tu propia cuenta en %(url)s y pégala en Ajustes.",
                url=URL_CONSEGUIR_CLAVE,
            )
        if isinstance(exc, anthropic.NotFoundError):
            return _(
                "Corrige el modelo en Ajustes: «%(modelo)s» no existe en Anthropic. "
                "Cópialo tal cual de la documentación de Anthropic, sin espacios ni "
                "el nombre comercial (por ejemplo «claude-haiku-4-5», no «Claude»).",
                modelo=self.modelo,
            )
        if isinstance(exc, anthropic.RateLimitError):
            return _(
                "Espera un rato y vuelve a intentarlo: has llegado al límite de "
                "peticiones de tu cuenta de Anthropic."
            )
        if isinstance(exc, anthropic.APITimeoutError):
            return _("Vuelve a generar la propuesta: Anthropic ha tardado demasiado en responder.")
        if isinstance(exc, anthropic.APIConnectionError):
            return _(
                "Comprueba tu conexión a internet y vuelve a intentarlo: no se ha "
                "podido contactar con Anthropic."
            )
        return _("Anthropic ha devuelto un error: %(error)s", error=exc)
