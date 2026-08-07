"""Generic client for any "OpenAI-compatible" provider.

Groq, OpenAI, Cerebras, Mistral, OpenRouter, Together, a local Ollama...
they all speak the same chat completions API format, only the base URL, the
key, and the model name change. Instead of writing one module per provider
(like `groq.py`), this one covers every provider that already speaks that
language, using the three credentials the user themselves fills in under
Settings.

**Anthropic (Claude) does not go through here**: its API has a different
shape (Messages API, not chat completions), so it needs its own module like
`groq.py`, not this generic one.

The key always belongs to the user and lives only on their machine, same as
in `groq.py` — none of this is ever pushed to the repository.
"""
from __future__ import annotations

from flask_babel import gettext as _

from ancla.ai.client import AIError

TIMEOUT_SEGUNDOS = 120

# With no way to know which provider the user is pointing at, there is no
# verified per-minute token limit like Groq's (see groq.py) — this value is
# just a reasonable ceiling to avoid asking for a disproportionate
# response, not a figure calibrated against any specific API.
MAX_TOKENS_RESPUESTA = 4000


class OpenAICompatibleClient:
    """Implements `ia.cliente.ClienteIA` against any endpoint that speaks
    OpenAI's chat completions format.

    Holds no state between calls: each adaptation is independent.
    """

    def __init__(
        self,
        clave: str = "",
        url_base: str = "",
        modelo: str = "",
        temperatura: float = 0.2,
    ) -> None:
        self.clave = (clave or "").strip()
        self.url_base = (url_base or "").strip()
        self.modelo = (modelo or "").strip()
        # Deliberately low temperature: the task is choosing from a closed
        # catalog and justifying it, not composing prose — same reasoning as Groq.
        self.temperatura = temperatura

    def available(self) -> bool:
        """True if a base URL, key, and model are all configured. Does not
        check that they are valid: that is only known once a call is made."""
        return bool(self.url_base and self.clave and self.modelo)

    def complete(self, sistema: str, usuario: str) -> str:
        if not self.available():
            raise AIError(
                _(
                    "Todavía no has configurado la URL base, la clave y el modelo de "
                    "tu proveedor. Ve a Ajustes y rellena los tres."
                )
            )
        respuesta = self._request(sistema, usuario)
        if not respuesta.strip():
            raise AIError(
                _("El proveedor ha devuelto una respuesta vacía. Vuelve a generar la propuesta.")
            )
        return respuesta

    # ----------------------------------------------------------------------

    def _request(self, sistema: str, usuario: str) -> str:
        cliente = self._sdk()
        try:
            completado = cliente.chat.completions.create(
                model=self.modelo,
                temperature=self.temperatura,
                max_tokens=MAX_TOKENS_RESPUESTA,
                messages=[
                    {"role": "system", "content": sistema},
                    {"role": "user", "content": usuario},
                ],
            )
        except Exception as exc:
            raise AIError(self._explain(exc)) from exc
        try:
            return completado.choices[0].message.content or ""
        except (AttributeError, IndexError, TypeError) as exc:
            raise AIError(
                _(
                    "El proveedor ha devuelto una respuesta con un formato inesperado. "
                    "Vuelve a generar la propuesta."
                )
            ) from exc

    def _sdk(self):
        """Imports the SDK here, not at the top: the app has to be able to
        start and show the Settings screen even if this dependency is missing."""
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise AIError(
                _("Falta la librería «openai». Instálala con: pip install -r requirements.txt")
            ) from exc
        return OpenAI(api_key=self.clave, base_url=self.url_base, timeout=TIMEOUT_SEGUNDOS)

    @staticmethod
    def _explain(exc: Exception) -> str:
        """Translates the SDK's failure into something the user can act on.

        Deliberately inspects the error's text, not its class, same as in
        `groq.py`: here the SDK is additionally shared across different
        providers, so the specific exception class says even less.
        """
        codigo = getattr(exc, "status_code", None)
        texto = str(exc).lower()

        if codigo in (401, 403) or "api key" in texto or "unauthorized" in texto:
            return _(
                "Tu clave de API no es válida o ha caducado. Revísala en Ajustes."
            )
        if codigo == 404 or ("model" in texto and "not found" in texto):
            return _(
                "El modelo configurado no existe en este proveedor, o la URL base "
                "de Ajustes está mal. Revisa ambos."
            )
        if codigo == 429 or "rate limit" in texto or "quota" in texto:
            return _(
                "Has agotado la cuota de tu proveedor por ahora. Espera un rato y "
                "vuelve a intentarlo."
            )
        if "timeout" in texto or "timed out" in texto:
            return _(
                "El proveedor ha tardado demasiado en responder. Vuelve a generar la propuesta."
            )
        if "connect" in texto or "network" in texto or "dns" in texto:
            return _(
                "No se ha podido contactar con la URL base configurada. Comprueba que "
                "esté bien escrita y tu conexión a internet."
            )
        return _("El proveedor ha devuelto un error: %(error)s", error=exc)
