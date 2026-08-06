"""Cliente genérico para cualquier proveedor "compatible con OpenAI".

Groq, OpenAI, Cerebras, Mistral, OpenRouter, Together, un Ollama local... todos
hablan el mismo formato de API de chat completions, solo cambia la URL base,
la clave y el nombre del modelo. En vez de escribir un módulo por proveedor
(como `groq.py`), este cubre a todos los que ya hablan ese idioma con las tres
credenciales que el propio usuario rellena en Ajustes.

**Anthropic (Claude) no entra por aquí**: su API tiene una forma distinta
(Messages API, no chat completions), así que necesitaría su propio módulo
como `groq.py`, no este genérico.

La clave es siempre del usuario y vive solo en su máquina, igual que en
`groq.py` — nada de esto se sube al repositorio.
"""
from __future__ import annotations

from flask_babel import gettext as _

from ancla.ia.cliente import ErrorIA

TIMEOUT_SEGUNDOS = 120

# Sin saber a qué proveedor apunta el usuario no hay un límite de tokens por
# minuto verificado como el de Groq (ver groq.py) — este valor es solo un
# techo razonable para no pedir una respuesta desproporcionada, no una cifra
# calibrada contra ninguna API concreta.
MAX_TOKENS_RESPUESTA = 4000


class ClienteCompatibleOpenAI:
    """Implementa `ia.cliente.ClienteIA` contra cualquier endpoint que hable
    el formato de chat completions de OpenAI.

    No guarda estado entre llamadas: cada adaptación es independiente.
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
        # Temperatura baja a propósito: la tarea es elegir de un catálogo
        # cerrado y justificarlo, no redactar — mismo criterio que en Groq.
        self.temperatura = temperatura

    def disponible(self) -> bool:
        """True si hay URL, clave y modelo configurados. No comprueba que
        sean válidos: eso solo se sabe al llamar."""
        return bool(self.url_base and self.clave and self.modelo)

    def completar(self, sistema: str, usuario: str) -> str:
        if not self.disponible():
            raise ErrorIA(
                _(
                    "Todavía no has configurado la URL base, la clave y el modelo de "
                    "tu proveedor. Ve a Ajustes y rellena los tres."
                )
            )
        respuesta = self._pedir(sistema, usuario)
        if not respuesta.strip():
            raise ErrorIA(
                _("El proveedor ha devuelto una respuesta vacía. Vuelve a generar la propuesta.")
            )
        return respuesta

    # ----------------------------------------------------------------------

    def _pedir(self, sistema: str, usuario: str) -> str:
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
            raise ErrorIA(self._explicar(exc)) from exc
        try:
            return completado.choices[0].message.content or ""
        except (AttributeError, IndexError, TypeError) as exc:
            raise ErrorIA(
                _(
                    "El proveedor ha devuelto una respuesta con un formato inesperado. "
                    "Vuelve a generar la propuesta."
                )
            ) from exc

    def _sdk(self):
        """Importa el SDK aquí y no arriba: la app tiene que poder arrancar y
        enseñar la pantalla de Ajustes aunque falte la dependencia."""
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ErrorIA(
                _("Falta la librería «openai». Instálala con: pip install -r requirements.txt")
            ) from exc
        return OpenAI(api_key=self.clave, base_url=self.url_base, timeout=TIMEOUT_SEGUNDOS)

    @staticmethod
    def _explicar(exc: Exception) -> str:
        """Traduce el fallo del SDK a algo que el usuario pueda accionar.

        Se mira el texto y no la clase del error a propósito, igual que en
        `groq.py`: aquí además el SDK es el mismo para proveedores distintos,
        así que la clase concreta de excepción dice todavía menos.
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
