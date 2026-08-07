"""Groq client, the default provider.

Chosen for its free tier, not for being the best: onboarding needs to be
able to say "create a free account and paste the key". If paying was
required before trying anything, no one would try it.

**The key always belongs to the user and lives only on their machine.**
This repository has, and can have, no one's credentials: it is public. Read
from local settings or from the `GROQ_API_KEY` environment variable, never
from a versioned file.

Switching providers means writing another module like this one that
satisfies `ia.cliente`'s `Protocol`. The engine does not know who is
answering it, and that must stay true.
"""
from __future__ import annotations

from flask_babel import gettext as _

from ancla.ai.client import AIError

MODELO_POR_DEFECTO = "openai/gpt-oss-120b"

# One adaptation is one call, and the whole profile catalog travels in it:
# a generous margin is worth having.
TIMEOUT_SEGUNDOS = 120

# `gpt-oss-120b` is a "reasoning" model: before writing the final answer it
# spends part of its token budget "thinking". Without `max_tokens`, the
# provider applies its own default limit, and a request that asks for a lot
# of detail (the importer can return several complete bilingual
# experiences) can exhaust it mid-thought and come back with empty or
# half-cut content — no error at all, just incomplete JSON.
#
# The value has a real ceiling, checked against the API: Groq's free tier
# caps at 8000 tokens per minute IN TOTAL (input + output), so `max_tokens`
# cannot be set loosely — it has to leave room for the prompt and the text
# passed alongside it. 4000 leaves plenty of margin for the rest in the
# app's two calls (adapting, and analysing a CV) without risking Groq
# rejecting the whole request for asking for more tokens than remain.
MAX_TOKENS_RESPUESTA = 4000

# Checked against the real API with Daniel's CV, three times in a row:
# without this, the model spent 79% of the `max_tokens` budget "reasoning"
# (3178 of 4000) and ran out of room for the JSON before finishing it
# (`finish_reason: length`). With `"low"`, it spends ~200 and finishes
# naturally (`finish_reason: stop`) all three times, with more content and
# fewer total tokens. The task is choosing from a closed catalog and
# extracting what is already written, not reasoning through a problem —
# same reasoning as the low temperature further down.
REASONING_EFFORT = "low"

URL_CONSEGUIR_CLAVE = "https://console.groq.com/keys"

# Failures the user can fix on their own are named plainly, with what to do
# about them. The rest are not dressed up as something else.
#
# The texts are inline in each `_(...)` call inside `_explicar` (not a
# module-level constant): pybabel only extracts literals passed directly to
# `_()`, not variables — a constant here would silently fall outside the
# translation catalog. Different from quota exhausted by accumulated
# requests (code 429): 413 means this specific request is too large for the
# per-minute limit on its own — retrying the same job posting, CV, or
# profile without trimming it will fail the same way again. Groq returns it
# with `"code": "rate_limit_exceeded"` (underscore: not to be confused with
# 429's "rate limit", which has a space).


class GroqClient:
    """Implements `ia.cliente.ClienteIA` over the Groq API.

    Holds no state between calls: each adaptation is independent and there
    is no conversation to maintain.
    """

    def __init__(
        self,
        clave: str = "",
        modelo: str = MODELO_POR_DEFECTO,
        temperatura: float = 0.2,
    ) -> None:
        self.clave = (clave or "").strip()
        self.modelo = modelo or MODELO_POR_DEFECTO
        # Deliberately low temperature: the task is choosing from a closed
        # catalog and justifying it, not composing prose. Creativity here
        # can only make the result worse.
        self.temperatura = temperatura

    def available(self) -> bool:
        """True if a key is configured. Does not check that it is valid."""
        return bool(self.clave)

    def complete(self, sistema: str, usuario: str) -> str:
        if not self.available():
            raise AIError(
                _(
                    "Todavía no has configurado tu clave de Groq. Ve a Ajustes y "
                    "pégala; puedes conseguir una gratis en %(url)s.",
                    url=URL_CONSEGUIR_CLAVE,
                )
            )
        respuesta = self._request(sistema, usuario)
        if not respuesta.strip():
            raise AIError(
                _("Groq ha devuelto una respuesta vacía. Vuelve a generar la propuesta.")
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
                reasoning_effort=REASONING_EFFORT,
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
                    "Groq ha devuelto una respuesta con un formato inesperado. "
                    "Vuelve a generar la propuesta."
                )
            ) from exc

    def _sdk(self):
        """Imports the SDK here, not at the top: the app has to be able to
        start and show the Settings screen even if this dependency is missing."""
        try:
            from groq import Groq
        except ImportError as exc:
            raise AIError(
                _("Falta la librería «groq». Instálala con: pip install -r requirements.txt")
            ) from exc
        return Groq(api_key=self.clave, timeout=TIMEOUT_SEGUNDOS)

    @staticmethod
    def _explain(exc: Exception) -> str:
        """Translates the SDK's failure into something the user can act on.

        Deliberately inspects the error's text, not its class: the SDK's
        exception hierarchy changes between versions, and losing the
        diagnosis over that would be worse than this workaround.
        """
        codigo = getattr(exc, "status_code", None)
        texto = str(exc).lower()

        if codigo in (401, 403) or "api key" in texto or "unauthorized" in texto:
            return _(
                "Tu clave de Groq no es válida o ha caducado. Revísala en Ajustes, "
                "puedes generar una gratis en %(url)s.",
                url=URL_CONSEGUIR_CLAVE,
            )
        if codigo == 413 or "tokens per minute" in texto or "request too large" in texto:
            return _(
                "Esta petición es demasiado grande para el límite de tokens por "
                "minuto de tu plan gratuito de Groq. Si es un CV, una vacante o un "
                "perfil muy largos, prueba con un texto más corto."
            )
        if codigo == 429 or "rate limit" in texto or "quota" in texto:
            return _(
                "Has agotado la cuota gratuita de Groq por ahora. Espera un rato y "
                "vuelve a intentarlo, o usa otra clave."
            )
        if codigo == 404 or ("model" in texto and "not found" in texto):
            return _(
                "El modelo «%(modelo)s» ya no está disponible en Groq. "
                "Elige otro en Ajustes.",
                modelo=MODELO_POR_DEFECTO,
            )
        if "timeout" in texto or "timed out" in texto:
            return _(
                "Groq ha tardado demasiado en responder. Vuelve a generar la propuesta."
            )
        if "connect" in texto or "network" in texto or "dns" in texto:
            return _(
                "No se ha podido contactar con Groq. Comprueba tu conexión a "
                "internet y vuelve a intentarlo."
            )
        return _("Groq ha devuelto un error: %(error)s", error=exc)
