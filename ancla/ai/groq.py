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
# The budget is reserved per call rather than fixed, because Groq decides
# whether to accept a request by comparing what it estimates the call will
# cost — the prompt plus whatever is reserved here — against what is left
# of the free tier's 8000 tokens per minute. A ceiling reserved for every
# call makes short requests compete for room they were never going to use.
#
# The figures come from the real API with two-page CVs: the response never
# took more than one token per character of the text sent, so the factor
# below leaves 40% on top of the worst measured case, plus the model's own
# reasoning budget, which is spent out of this same reservation. Reserving
# too little is the dangerous direction — the model stops mid-JSON and the
# caller gets nothing usable — so the floor is deliberately generous and
# the ceiling is what the whole per-minute allowance can afford alongside a
# long prompt.
TOKENS_RESPUESTA_POR_CARACTER = 1.4
MIN_TOKENS_RESPUESTA = 1500
MAX_TOKENS_RESPUESTA = 4000

# Being rejected for exceeding the tokens-per-minute allowance is
# temporary: it refills continuously, and the response says how many
# seconds are missing, which the SDK waits before trying again. Set here
# instead of left to the SDK's default because each wait is only as long as
# that response asks for (a dozen seconds), while refilling the whole
# allowance takes up to a minute — two attempts can still fall short, and
# giving up looks to the user like the CV was lost.
REINTENTOS = 3

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
# The texts are inline in each `_(...)` call inside `_explain` (not a
# module-level constant): pybabel only extracts literals passed directly to
# `_()`, not variables — a constant here would silently fall outside the
# translation catalog.
#
# Two Groq failures look alike and are not the same, so they are told apart
# by status code before any text is matched: both mention "tokens per
# minute". A 429 means the allowance is spent right now and waiting fixes
# it — telling that user to shorten their CV is false advice, the text was
# never the problem. A 413 means this single request does not fit in the
# whole per-minute allowance even on an empty budget, and there waiting
# changes nothing.


def _reserved_tokens(usuario: str) -> int:
    """Room to reserve for the response, from the size of the text sent.

    Only the user text counts: the system prompt is instructions, and what
    the model has to write back is proportional to the material it is given
    — the CV to read, or the catalog to choose from.
    """
    escalado = int(len(usuario) * TOKENS_RESPUESTA_POR_CARACTER)
    return max(MIN_TOKENS_RESPUESTA, min(MAX_TOKENS_RESPUESTA, escalado))


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
                max_tokens=_reserved_tokens(usuario),
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
        return Groq(api_key=self.clave, timeout=TIMEOUT_SEGUNDOS, max_retries=REINTENTOS)

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
        if codigo == 429 or "rate limit" in texto or "quota" in texto:
            return _(
                "Espera un minuto y vuelve a intentarlo: tu plan gratuito de Groq "
                "admite un número limitado de palabras por minuto y ahora mismo "
                "está al tope. No tienes que acortar tu CV ni la vacante, solo "
                "esperar. No se ha guardado nada, así que puedes repetir la misma "
                "operación tal cual."
            )
        if codigo == 413 or "request too large" in texto or "tokens per minute" in texto:
            return _(
                "Acorta el texto y vuelve a intentarlo, o pega solo la parte que "
                "importa: esta petición es demasiado grande para lo que tu plan "
                "gratuito de Groq admite por minuto, así que esperar no la deja "
                "pasar."
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
