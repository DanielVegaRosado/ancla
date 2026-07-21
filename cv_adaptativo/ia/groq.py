"""Cliente de Groq, el proveedor por defecto.

Se eligió por su nivel gratuito, no por ser el mejor: el onboarding tiene que
poder decir "crea una cuenta gratis y pega la clave". Si hubiera que pagar
antes de probar nada, no probaría nadie.

**La clave es siempre del usuario y vive solo en su máquina.** En este
repositorio no hay ni puede haber credenciales de nadie: es público. Se lee de
los ajustes locales o de la variable de entorno `GROQ_API_KEY`, nunca de un
fichero versionado.

Cambiar de proveedor es escribir otro módulo como este y cumplir el `Protocol`
de `ia.cliente`. El motor no sabe quién le responde, y así debe seguir.
"""
from __future__ import annotations

from cv_adaptativo.ia.cliente import ErrorIA

MODELO_POR_DEFECTO = "openai/gpt-oss-120b"

# Una adaptación es una sola llamada, y el catálogo del perfil entero viaja en
# ella: conviene un margen amplio.
TIMEOUT_SEGUNDOS = 120

URL_CONSEGUIR_CLAVE = "https://console.groq.com/keys"

# Los fallos que el usuario puede arreglar por su cuenta se cuentan en claro, y
# se dice qué hacer. Los demás no se disfrazan de otra cosa.
_AYUDA_CLAVE = (
    "Tu clave de Groq no es válida o ha caducado. Revísala en Ajustes; puedes "
    f"generar una gratis en {URL_CONSEGUIR_CLAVE}."
)
_AYUDA_CUOTA = (
    "Has agotado la cuota gratuita de Groq por ahora. Espera un rato y vuelve a "
    "intentarlo, o usa otra clave."
)
_AYUDA_RED = (
    "No se ha podido contactar con Groq. Comprueba tu conexión a internet y "
    "vuelve a intentarlo."
)


class ClienteGroq:
    """Implementa `ia.cliente.ClienteIA` sobre la API de Groq.

    No guarda estado entre llamadas: cada adaptación es independiente y no hay
    conversación que mantener.
    """

    def __init__(
        self,
        clave: str = "",
        modelo: str = MODELO_POR_DEFECTO,
        temperatura: float = 0.2,
    ) -> None:
        self.clave = (clave or "").strip()
        self.modelo = modelo or MODELO_POR_DEFECTO
        # Temperatura baja a propósito: la tarea es elegir de un catálogo
        # cerrado y justificarlo, no redactar. La creatividad aquí solo puede
        # empeorar el resultado.
        self.temperatura = temperatura

    def disponible(self) -> bool:
        """True si hay clave configurada. No comprueba que sea válida."""
        return bool(self.clave)

    def completar(self, sistema: str, usuario: str) -> str:
        if not self.disponible():
            raise ErrorIA(
                "Todavía no has configurado tu clave de Groq. Ve a Ajustes y "
                f"pégala; puedes conseguir una gratis en {URL_CONSEGUIR_CLAVE}."
            )
        respuesta = self._pedir(sistema, usuario)
        if not respuesta.strip():
            raise ErrorIA(
                "Groq ha devuelto una respuesta vacía. Vuelve a generar la propuesta."
            )
        return respuesta

    # ----------------------------------------------------------------------

    def _pedir(self, sistema: str, usuario: str) -> str:
        cliente = self._sdk()
        try:
            completado = cliente.chat.completions.create(
                model=self.modelo,
                temperature=self.temperatura,
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
                "Groq ha devuelto una respuesta con un formato inesperado. "
                "Vuelve a generar la propuesta."
            ) from exc

    def _sdk(self):
        """Importa el SDK aquí y no arriba: la app tiene que poder arrancar y
        enseñar la pantalla de Ajustes aunque falte la dependencia."""
        try:
            from groq import Groq
        except ImportError as exc:
            raise ErrorIA(
                "Falta la librería «groq». Instálala con: pip install -r requirements.txt"
            ) from exc
        return Groq(api_key=self.clave, timeout=TIMEOUT_SEGUNDOS)

    @staticmethod
    def _explicar(exc: Exception) -> str:
        """Traduce el fallo del SDK a algo que el usuario pueda accionar.

        Se mira el texto y no la clase del error a propósito: el SDK cambia sus
        jerarquías entre versiones, y quedarse sin diagnóstico por eso sería
        peor que este apaño.
        """
        codigo = getattr(exc, "status_code", None)
        texto = str(exc).lower()

        if codigo in (401, 403) or "api key" in texto or "unauthorized" in texto:
            return _AYUDA_CLAVE
        if codigo == 429 or "rate limit" in texto or "quota" in texto:
            return _AYUDA_CUOTA
        if codigo == 404 or ("model" in texto and "not found" in texto):
            return (
                f"El modelo «{MODELO_POR_DEFECTO}» ya no está disponible en Groq. "
                "Elige otro en Ajustes."
            )
        if "timeout" in texto or "timed out" in texto:
            return (
                "Groq ha tardado demasiado en responder. Vuelve a generar la propuesta."
            )
        if "connect" in texto or "network" in texto or "dns" in texto:
            return _AYUDA_RED
        return f"Groq ha devuelto un error: {exc}"
