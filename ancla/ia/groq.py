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

from flask_babel import gettext as _

from ancla.ia.cliente import ErrorIA

MODELO_POR_DEFECTO = "openai/gpt-oss-120b"

# Una adaptación es una sola llamada, y el catálogo del perfil entero viaja en
# ella: conviene un margen amplio.
TIMEOUT_SEGUNDOS = 120

# `gpt-oss-120b` es un modelo "razonador": antes de escribir la respuesta
# final gasta parte de su presupuesto de tokens "pensando". Sin `max_tokens`,
# el proveedor aplica su propio límite por defecto, y una petición que pide
# mucho detalle (el importador puede devolver varias experiencias bilingües
# completas) puede agotarlo a media reflexión y volver con el contenido
# vacío o cortado a medias — sin ningún error, solo un JSON incompleto.
#
# El valor tiene un techo real y verificado contra la API: el nivel gratuito
# de Groq limita a 8000 tokens por minuto EN TOTAL (entrada + salida), así
# que `max_tokens` no puede ir suelto — tiene que dejar sitio al prompt y al
# texto que se le pase. 4000 deja margen de sobra para el resto en las dos
# llamadas que hace la app (adaptar y analizar un CV) sin arriesgarse a que
# Groq rechace la petición entera por pedir más tokens de los que quedan.
MAX_TOKENS_RESPUESTA = 4000

# Verificado contra la API real con el CV de Daniel, tres veces seguidas: sin
# esto, el modelo gastaba el 79% del presupuesto de `max_tokens` "razonando"
# (3178 de 4000) y se quedaba sin espacio para el JSON antes de terminarlo
# (`finish_reason: length`). Con `"low"`, gasta ~200 y termina de forma
# natural (`finish_reason: stop`) las tres veces, con más contenido y menos
# tokens totales. La tarea es elegir de un catálogo cerrado y extraer lo que
# ya está escrito, no razonar sobre un problema — mismo criterio que la
# temperatura baja de más abajo.
REASONING_EFFORT = "low"

URL_CONSEGUIR_CLAVE = "https://console.groq.com/keys"

# Los fallos que el usuario puede arreglar por su cuenta se cuentan en claro, y
# se dice qué hacer. Los demás no se disfrazan de otra cosa.
#
# Los textos van inline en cada `_(...)` de `_explicar` (no en una constante
# de módulo): pybabel solo extrae literales pasados directamente a `_()`, no
# variables — una constante aquí quedaría fuera del catálogo de traducción
# sin avisar. Distinto de la cuota agotada por peticiones acumuladas
# (código 429): el 413 es esta petición en concreto siendo demasiado grande
# para el límite por minuto de una sola vez — reintentar la misma vacante, CV
# o perfil sin recortarlos vuelve a fallar igual. Groq lo devuelve con
# `"code": "rate_limit_exceeded"` (con guion bajo: no confundir con el
# "rate limit" del 429, que lleva espacio).


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
                _(
                    "Todavía no has configurado tu clave de Groq. Ve a Ajustes y "
                    "pégala; puedes conseguir una gratis en %(url)s.",
                    url=URL_CONSEGUIR_CLAVE,
                )
            )
        respuesta = self._pedir(sistema, usuario)
        if not respuesta.strip():
            raise ErrorIA(
                _("Groq ha devuelto una respuesta vacía. Vuelve a generar la propuesta.")
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
                reasoning_effort=REASONING_EFFORT,
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
                    "Groq ha devuelto una respuesta con un formato inesperado. "
                    "Vuelve a generar la propuesta."
                )
            ) from exc

    def _sdk(self):
        """Importa el SDK aquí y no arriba: la app tiene que poder arrancar y
        enseñar la pantalla de Ajustes aunque falte la dependencia."""
        try:
            from groq import Groq
        except ImportError as exc:
            raise ErrorIA(
                _("Falta la librería «groq». Instálala con: pip install -r requirements.txt")
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
