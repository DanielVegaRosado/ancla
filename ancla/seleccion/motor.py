"""El núcleo: elegir qué mostrar del perfil para una vacante concreta.

Esta es la pieza que distingue al producto. No redacta un CV: **selecciona**
entre hechos que el usuario ya ha verificado, los ordena por relevancia y
explica por qué ha elegido cada uno.

Reglas duras, heredadas de la skill personal `/cv-adaptativo`:

1. Nunca proponer una experiencia o skill que no exista en el perfil. Si la
   vacante pide algo que el usuario no tiene, va a `huecos`, no al CV.
2. Nunca reescribir los bullets del usuario: se muestran tal cual los escribió.
3. Toda elección lleva motivo. Sin motivo, el usuario no puede juzgar la
   propuesta, y juzgarla es justo lo que le pedimos que haga.

Cómo se sostienen esas reglas aquí: el modelo solo devuelve *ids* del perfil y
motivos, y este módulo descarta todo id que no exista. La 2 sale gratis porque
`Propuesta` guarda referencias y no texto — el motor nunca llega a tocar un
bullet. La única excepción es el "Sobre mí", donde sí se compone texto, y ahí
los huecos solo se rellenan con nombres de skills que ya están en el perfil.

Una sola llamada al modelo por adaptación. Todo lo demás es determinista, y si
el modelo se queda corto se completa desde el perfil, nunca inventando.
"""
from __future__ import annotations

import json
from typing import Any

from flask_babel import gettext as _

from ancla.ia.cliente import ClienteIA, ErrorIA
from ancla.perfil.modelo import (
    N_EXPERIENCIAS,
    N_GRUPO_SOBRE_MI,
    N_SKILLS,
    Bilingue,
    Experiencia,
    ExperienciaSeleccionada,
    Idioma,
    Perfil,
    Propuesta,
    SeleccionSobreMi,
    Skill,
)
from ancla.seleccion.prompt import construir_mensajes
from ancla.texto import a_texto, bloque_json, normalizar

# Textos que ve el usuario cuando el modelo se deja algo a medias. Se dicen en
# claro en vez de disimularlos: la propuesta está para revisarla, no para
# firmarla a ciegas.
MOTIVO_AUSENTE = "El modelo no explicó esta elección, revísala antes de usarla."
AVISO_SOBRE_MI_INCOMPLETO = (
    "Tu perfil no tiene suficientes skills para rellenar el «Sobre mí». Hacen "
    f"falta {N_GRUPO_SOBRE_MI} por grupo. El texto se queda con sus huecos a la "
    "vista hasta que añadas más."
)


def adaptar(
    perfil: Perfil,
    vacante: str,
    idioma: Idioma,
    cliente: ClienteIA,
    n_experiencias: int = N_EXPERIENCIAS,
    n_skills: int = N_SKILLS,
) -> Propuesta:
    """Adapta el perfil a la vacante. Una sola llamada al modelo.

    Si el perfil tiene menos elementos de los pedidos, devuelve los que haya:
    completar el hueco inventando es exactamente lo que no hace este producto.

    Lanza `ErrorIA` si el proveedor falla, y `ValueError` si el perfil está
    vacío o no tiene plantilla de "Sobre mí".
    """
    if perfil.esta_vacio():
        raise ValueError(
            _("Tu perfil está vacío: añade experiencias y skills antes de adaptar el CV.")
        )
    if perfil.sobre_mi is None:
        raise ValueError(
            _("Tu perfil no tiene plantilla de «Sobre mí»: créala antes de adaptar el CV.")
        )
    if not vacante.strip():
        raise ValueError(_("Pega el texto de la vacante antes de generar la propuesta."))

    sistema, usuario = construir_mensajes(
        perfil, vacante, idioma, n_experiencias, n_skills
    )
    datos = _interpretar(cliente.completar(sistema, usuario))

    skills, motivo_skills = _elegir_skills(datos, perfil, vacante, n_skills)
    return Propuesta(
        idioma=idioma,
        sobre_mi=_componer_sobre_mi(datos, perfil, skills, idioma),
        skills=skills,
        experiencias=_elegir_experiencias(datos, perfil, vacante, n_experiencias),
        motivo_skills=motivo_skills,
        huecos=_depurar_huecos(datos, perfil),
    )


# --------------------------------------------------------------------------
# Respuesta del modelo
# --------------------------------------------------------------------------


def _interpretar(respuesta: str) -> dict[str, Any]:
    """Saca el objeto JSON de la respuesta, venga como venga.

    No se reintenta: una adaptación es una llamada. Si la respuesta no se
    entiende, el usuario vuelve a darle a generar sabiendo lo que cuesta.
    """
    bloque = bloque_json(respuesta or "")
    if bloque is None:
        raise ErrorIA(
            _(
                "El modelo no ha devuelto una respuesta que se pueda interpretar. "
                "Vuelve a generar la propuesta."
            )
        )
    try:
        datos = json.loads(bloque)
    except json.JSONDecodeError as exc:
        raise ErrorIA(
            _(
                "El modelo ha devuelto una respuesta mal formada. "
                "Vuelve a generar la propuesta."
            )
        ) from exc
    if not isinstance(datos, dict):
        raise ErrorIA(
            _(
                "El modelo ha devuelto algo que no es una propuesta. "
                "Vuelve a generar la propuesta."
            )
        )
    return datos


def _lista(valor: Any) -> list[Any]:
    return valor if isinstance(valor, list) else []


# --------------------------------------------------------------------------
# Selección: lo que el modelo eligió, filtrado contra el perfil
# --------------------------------------------------------------------------


def _elegir_experiencias(
    datos: dict[str, Any], perfil: Perfil, vacante: str, cuantas: int
) -> list[ExperienciaSeleccionada]:
    elegidas: list[ExperienciaSeleccionada] = []
    vistas: set[str] = set()

    for elemento in _lista(datos.get("experiencias")):
        if len(elegidas) >= cuantas:
            break
        id_exp, motivo = _id_y_motivo(elemento)
        # Aquí muere cualquier experiencia inventada: si no está en el perfil,
        # no llega al CV.
        if not id_exp or id_exp in vistas or perfil.experiencia(id_exp) is None:
            continue
        vistas.add(id_exp)
        elegidas.append(
            ExperienciaSeleccionada(id=id_exp, motivo=motivo or MOTIVO_AUSENTE)
        )

    for exp in _por_relevancia(perfil.experiencias, vacante):
        if len(elegidas) >= cuantas:
            break
        if exp.id in vistas:
            continue
        vistas.add(exp.id)
        elegidas.append(
            ExperienciaSeleccionada(id=exp.id, motivo=_motivo_de_relleno(exp, vacante))
        )
    return elegidas


def _elegir_skills(
    datos: dict[str, Any], perfil: Perfil, vacante: str, cuantas: int
) -> tuple[list[str], str]:
    elegidas: list[str] = []
    for elemento in _lista(datos.get("skills")):
        if len(elegidas) >= cuantas:
            break
        id_skill, _ = _id_y_motivo(elemento)
        if not id_skill or id_skill in elegidas or perfil.skill(id_skill) is None:
            continue
        elegidas.append(id_skill)

    motivo = a_texto(datos.get("motivo_skills")) or MOTIVO_AUSENTE
    completadas = [
        skill.id
        for skill in _por_relevancia(perfil.skills, vacante)
        if skill.id not in elegidas
    ][: max(0, cuantas - len(elegidas))]
    if completadas:
        motivo += (
            " El modelo devolvió menos skills de las que caben, así que el sistema ha"
            " completado la lista con las del perfil que más coinciden con la vacante;"
            " revisa las últimas."
        )
    elegidas.extend(completadas)
    return elegidas, motivo


def _id_y_motivo(elemento: Any) -> tuple[str, str]:
    """Acepta tanto `"id"` como `{"id": ..., "motivo": ...}`."""
    if isinstance(elemento, str):
        return elemento.strip(), ""
    if isinstance(elemento, dict):
        return a_texto(elemento.get("id")), a_texto(elemento.get("motivo"))
    return "", ""


def _por_relevancia(elementos: list[Any], vacante: str) -> list[Any]:
    """Orden determinista por coincidencia de keywords con la vacante.

    Solo se usa para completar lo que el modelo no eligió. No pretende ser
    listo: pretende ser explicable y no gastar otra llamada.
    """
    texto = normalizar(vacante)
    ordenados = sorted(
        enumerate(elementos),
        key=lambda par: (-len(_coincidencias(par[1], texto)), par[0]),
    )
    return [elemento for _, elemento in ordenados]


def _coincidencias(
    elemento: Experiencia | Skill, vacante_normalizada: str
) -> list[str]:
    return [
        palabra
        for palabra in elemento.keywords
        if normalizar(palabra) and normalizar(palabra) in vacante_normalizada
    ]


def _motivo_de_relleno(elemento: Experiencia | Skill, vacante: str) -> str:
    coincidencias = _coincidencias(elemento, normalizar(vacante))
    if coincidencias:
        return (
            "Elegida por el sistema, no por el modelo: coincide con la vacante en "
            + ", ".join(coincidencias[:3])
            + "."
        )
    return (
        "Elegida por el sistema para completar la sección; no se le ha encontrado "
        "coincidencia clara con la vacante. Cámbiala si no encaja."
    )


# --------------------------------------------------------------------------
# Sobre mí: la única parte donde el sistema compone texto
# --------------------------------------------------------------------------


def _componer_sobre_mi(
    datos: dict[str, Any], perfil: Perfil, skills: list[str], idioma: Idioma
) -> SeleccionSobreMi:
    bruto = datos.get("sobre_mi")
    bruto = bruto if isinstance(bruto, dict) else {}

    # Primero se apuntan las dos propuestas del modelo y solo después se
    # completan. Al revés, el relleno del grupo A podría quedarse una skill
    # que el modelo había pedido expresamente para el grupo B.
    reparto = _RepartoSobreMi(perfil, skills)
    propuestas_a = reparto.propuestas(bruto.get("grupo_a"))
    propuestas_b = reparto.propuestas(bruto.get("grupo_b"))
    grupo_a = _nombres(reparto.completar(propuestas_a), idioma)
    grupo_b = _nombres(reparto.completar(propuestas_b), idioma)

    motivo = a_texto(bruto.get("motivo")) or MOTIVO_AUSENTE
    if len(grupo_a) == N_GRUPO_SOBRE_MI and len(grupo_b) == N_GRUPO_SOBRE_MI:
        texto = perfil.sobre_mi.render(grupo_a, grupo_b, idioma)
    else:
        # Sin skills suficientes no hay nada honesto que poner en los huecos,
        # así que se deja la plantilla tal cual y se dice por qué.
        texto = perfil.sobre_mi.plantilla[idioma]
        motivo = f"{motivo} {AVISO_SOBRE_MI_INCOMPLETO}"
    return SeleccionSobreMi(
        grupo_a=grupo_a, grupo_b=grupo_b, texto=texto, motivo=motivo
    )


class _RepartoSobreMi:
    """Reparte skills entre los dos grupos del "Sobre mí" sin repetir ninguna.

    Tiene estado —qué skills lleva ya colocadas— y lo guarda dentro a
    propósito. Antes ese `set` viajaba de parámetro en parámetro: funcionaba,
    pero escondía que el orden de las llamadas importa, que es justo lo que
    alguien reordena sin querer dentro de seis meses.
    """

    def __init__(self, perfil: Perfil, skills: list[str]) -> None:
        self._perfil = perfil
        self._usadas: set[str] = set()
        # Para completar se tira primero de las skills que ya se van a enseñar
        # en el CV: el "Sobre mí" tiene que ser coherente con la lista de
        # debajo. Después, del resto del perfil.
        seleccionadas = [perfil.skill(id_skill) for id_skill in skills]
        self._reserva = [s for s in seleccionadas if s is not None] + perfil.skills

    def propuestas(self, valores: Any) -> list[Skill]:
        """Las skills que propuso el modelo y existen de verdad en el perfil.

        Lo que no resuelve contra una skill real, se cae: es la regla 1
        aplicada a la única sección donde el sistema compone texto.
        """
        return self._tomar([], (a_texto(valor) for valor in _lista(valores)))

    def completar(self, elegidas: list[Skill]) -> list[Skill]:
        """Rellena el grupo desde la reserva, sin tocar la lista que recibe."""
        return self._tomar(elegidas, (skill.id for skill in self._reserva))

    def _tomar(self, elegidas: list[Skill], candidatos) -> list[Skill]:
        grupo = list(elegidas)
        for candidato in candidatos:
            if len(grupo) >= N_GRUPO_SOBRE_MI:
                break
            skill = _skill_por_nombre(candidato, self._perfil)
            if skill is None or skill.id in self._usadas:
                continue
            self._usadas.add(skill.id)
            grupo.append(skill)
        return grupo


def _nombres(skills: list[Skill], idioma: Idioma) -> list[str]:
    """El nombre en el idioma del CV, no el que escribió el modelo.

    Si pide "Machine learning" para un CV en español y la skill del perfil se
    llama "Aprendizaje automático", va la del perfil.
    """
    return [skill.nombre[idioma] for skill in skills]


def _skill_por_nombre(valor: str, perfil: Perfil) -> Skill | None:
    """Busca una skill por id o por su nombre en cualquiera de los dos idiomas."""
    if not valor:
        return None
    por_id = perfil.skill(valor)
    if por_id is not None:
        return por_id
    buscado = normalizar(valor)
    return next(
        (
            skill
            for skill in perfil.skills
            if buscado
            in (normalizar(skill.nombre["es"]), normalizar(skill.nombre["en"]))
        ),
        None,
    )


# --------------------------------------------------------------------------
# Huecos: lo que la vacante pide y el perfil no tiene
# --------------------------------------------------------------------------


def _depurar_huecos(datos: dict[str, Any], perfil: Perfil) -> list[str]:
    """Limpia la lista de huecos y quita los que sí están en el perfil.

    Un hueco que resulta ser algo que el usuario tiene es ruido: le hace dudar
    de una propuesta que era correcta.
    """
    huecos: list[str] = []
    vistos: set[str] = set()
    for valor in _lista(datos.get("huecos")):
        hueco = a_texto(valor)
        clave = normalizar(hueco)
        if not clave or clave in vistos or _hueco_cubierto(hueco, perfil):
            continue
        vistos.add(clave)
        huecos.append(hueco)
    return huecos


def _hueco_cubierto(hueco: str, perfil: Perfil) -> bool:
    """True si el hueco reportado ya está cubierto por algo del perfil —
    skills técnicas, skills personales o idiomas — aunque esté redactado con
    otras palabras.

    El modelo nunca ve `skills_personales` ni `idiomas` (no se le envían: es
    lo que garantiza que nunca puedan colarse en "Sobre mí" ni en las skills
    técnicas), así que casi siempre los reportará como hueco. Este filtro es
    lo único que puede evitarlo, y por eso es más laxo que `_skill_por_nombre`
    (que exige coincidencia exacta y sirve para *identificar* una skill al
    construir el "Sobre mí"): un hueco se redacta en prosa —«nivel avanzado de
    inglés»—, casi nunca como el nombre exacto de una skill, así que exigir
    coincidencia exacta aquí dejaría pasar casi todos los falsos positivos.
    """
    clave = normalizar(hueco)
    if not clave:
        return False
    candidatos = (*perfil.skills, *perfil.skills_personales, *perfil.idiomas)
    return any(_nombre_o_keyword_en(clave, item.nombre, item.keywords) for item in candidatos)


def _nombre_o_keyword_en(clave: str, nombre: Bilingue[str], keywords: list[str]) -> bool:
    nombres = (normalizar(nombre["es"]), normalizar(nombre["en"]))
    if any(n and (n in clave or clave in n) for n in nombres):
        return True
    return any(kw.strip() and normalizar(kw) in clave for kw in keywords)
