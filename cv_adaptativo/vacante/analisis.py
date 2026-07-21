"""Extracción de datos de la vacante pegada por el usuario.

Solo lo determinista y barato: empresa y puesto, para nombrar el CV en el
archivo y poder avisar de que ya existe uno de esa empresa antes de gastar una
llamada al modelo. El análisis de requisitos de verdad lo hace el motor, dentro
de esa única llamada.

Se busca en tres pasadas, de más a menos fiable, y se para en la primera que
acierta: etiqueta explícita ("Empresa:"), frase hecha ("Únete a X", "X busca"),
y por último la cabecera que pegan los portales (primera línea el puesto,
segunda la empresa). En cuanto la confianza baja de ahí, se devuelve cadena
vacía: un dato inventado en el nombre del archivo es peor que un campo vacío
que el usuario rellena en dos segundos.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from cv_adaptativo.texto import normalizar

# Las cabeceras están arriba; más abajo empieza la descripción y todo lo que se
# encuentre ahí es ruido.
LINEAS_CABECERA = 40
MAX_CARACTERES_CAMPO = 80

_ETIQUETAS_EMPRESA = (
    r"empresa|compa[ñn][ií]a|organizaci[oó]n|entidad|company|employer|hiring company"
)
_ETIQUETAS_PUESTO = (
    r"puesto|cargo|posici[oó]n|vacante|oferta|t[ií]tulo del puesto"
    r"|position|role|job title|job"
)

# Palabras que delatan un título de puesto. No es una taxonomía: es lo que
# aparece de hecho en las ofertas que la gente pega.
_PALABRAS_DE_PUESTO = (
    "desarrollador", "desarrolladora", "programador", "programadora", "ingenier",
    "analista", "cientific", "arquitect", "tecnic", "consultor", "becari",
    "practicas", "especialista", "responsable", "jefe", "director", "gestor",
    "administrador", "investigador", "disenador",
    "developer", "engineer", "scientist", "analyst", "architect", "intern",
    "internship", "manager", "designer", "specialist", "consultant", "lead",
    "trainee", "researcher", "devops", "sre", "backend", "frontend", "fullstack",
    "full stack", "data", "qa", "tester",
)

# Una cabecera es un título, no una frase. Si la línea dice que alguien busca a
# alguien, es prosa y no el nombre del puesto.
_MARCAS_DE_FRASE = (
    "busca", "buscamos", "estamos", "ofrecemos", "requisitos",
    "we are", "is hiring", "hiring for", "join us",
)

# Modalidad, jornada y demás adornos del portal: nunca son la empresa.
_RUIDO = (
    "remoto", "remote", "hibrido", "hybrid", "presencial", "on-site", "onsite",
    "jornada", "full-time", "part-time", "tiempo completo", "media jornada",
    "salario", "salary", "contrato", "publicado", "solicitar", "apply",
    "hace ", " ago", "candidatos", "applicants",
)

_SUFIJOS_EMPRESA = r"s\.?l\.?u?\.?|s\.?a\.?|inc|ltd|llc|gmbh|b\.?v\.?|corp|group|ag|plc"

# Un nombre de empresa: hasta cuatro palabras que empiezan por mayúscula. Las
# frases de abajo se toman las mayúsculas en serio, así que nada de IGNORECASE
# global (anularía las clases [A-Z]): los disparadores van con `(?i:...)`.
_NOMBRE = r"(?P<nombre>[A-ZÁÉÍÓÚÑ][\w&.\-]*(?:\s+[A-ZÁÉÍÓÚÑ0-9][\w&.\-]*){0,3})"

_FRASES_EMPRESA = (
    rf"(?i:[uú]nete a|join)\s+{_NOMBRE}",
    rf"^\s*{_NOMBRE}\s+(?i:busca|est[aá] buscando|selecciona|ampl[ií]a)\b",
    rf"(?i:\ben)\s+{_NOMBRE}\s+(?i:buscamos|estamos buscando)\b",
    rf"^\s*(?i:sobre|acerca de|about(?: us at)?)\s+{_NOMBRE}\s*$",
)


@dataclass(frozen=True)
class DatosVacante:
    empresa: str = ""
    puesto: str = ""


def extraer_datos(vacante: str) -> DatosVacante:
    """Intenta adivinar empresa y puesto del texto pegado.

    Es una heurística: devuelve cadenas vacías si no lo ve claro, y la web
    deja que el usuario los corrija siempre. Nunca bloquea el flujo.
    """
    texto = vacante or ""
    lineas = [_sin_markdown(linea) for linea in texto.splitlines()]
    lineas = [linea for linea in lineas if linea][:LINEAS_CABECERA]

    empresa = _por_etiqueta(lineas, _ETIQUETAS_EMPRESA) or _por_frase_hecha(lineas)
    puesto = _por_etiqueta(lineas, _ETIQUETAS_PUESTO)

    if not puesto and lineas and _parece_puesto(lineas[0]):
        puesto = _limpiar(lineas[0])
        # Cabecera típica de portal: el puesto y justo debajo la empresa.
        if not empresa and len(lineas) > 1:
            empresa = _empresa_de_cabecera(lineas[1])

    return DatosVacante(empresa=empresa, puesto=puesto)


def _por_etiqueta(lineas: list[str], etiquetas: str) -> str:
    patron = re.compile(rf"^\s*(?:{etiquetas})\s*[:：\-–—]\s*(.+)$", re.IGNORECASE)
    for linea in lineas:
        encontrado = patron.match(linea)
        if not encontrado:
            continue
        valor = _limpiar(encontrado.group(1))
        if valor:
            return valor
    return ""


def _por_frase_hecha(lineas: list[str]) -> str:
    cabecera = "\n".join(lineas)
    for patron in _FRASES_EMPRESA:
        encontrado = re.search(patron, cabecera, re.MULTILINE)
        if not encontrado:
            continue
        nombre = _limpiar(encontrado.group("nombre"))
        if nombre and _parece_nombre_propio(nombre):
            return nombre
    return ""


def _empresa_de_cabecera(linea: str) -> str:
    """La segunda línea de la cabecera, si de verdad parece una empresa."""
    candidato = _limpiar(linea)
    if not candidato or _parece_puesto(candidato) or not _parece_nombre_propio(candidato):
        return ""
    return candidato


def _parece_puesto(linea: str) -> bool:
    bruto = _sin_markdown(linea)
    if bruto.endswith((".", "!", "?", ":", ";")):
        return False
    if any(marca in normalizar(bruto) for marca in _MARCAS_DE_FRASE):
        return False
    candidato = _limpiar(linea)
    if not candidato or len(candidato.split()) > 12:
        return False
    normalizado = normalizar(candidato)
    return any(palabra in normalizado for palabra in _PALABRAS_DE_PUESTO)


def _parece_nombre_propio(valor: str) -> bool:
    """Descarta frases, ubicaciones y adornos del portal."""
    if not valor[0].isupper() or len(valor.split()) > 5:
        return False
    if "," in valor:
        # "Acme, S.L." vale; "Madrid, España" no.
        cola = valor.rsplit(",", 1)[1].strip()
        if not re.fullmatch(_SUFIJOS_EMPRESA, normalizar(cola)):
            return False
    return True


def _limpiar(valor: str) -> str:
    """Deja el campo listo para enseñarlo, o vacío si no vale la pena."""
    texto = _sin_markdown(valor)
    # Los portales encadenan campos con · o |: el primero es el que importa.
    texto = re.split(r"[·|•]", texto)[0]
    texto = re.sub(
        r"\((?:[mfhxdwv]\s*/[^)]*|remoto|remote|h[íi]brido|hybrid|presencial"
        r"|on-?site|full[\s-]?time|part[\s-]?time)\)",
        "",
        texto,
        flags=re.IGNORECASE,
    )
    texto = re.sub(r"\s+", " ", texto).strip(" \t\"'“”«»-–—…").strip()
    # El punto final sobra, salvo cuando es parte de la razón social ("S.L.").
    if not re.search(r"(?:\b\w\.){2,}$", texto):
        texto = texto.rstrip(".,;:").strip()

    if not texto or len(texto) > MAX_CARACTERES_CAMPO:
        return ""
    # El filtro de ruido se aplica también al puesto, no solo a la empresa. Es
    # a propósito, y tiene un coste conocido: "Desarrollador backend remoto"
    # devuelve puesto vacío. Se acepta porque el campo se corrige en la web en
    # dos segundos, y porque el mismo filtro es lo que evita archivar un CV a
    # nombre de "Jornada completa". Si algún día molesta, la salida es separar
    # dos listas de ruido (una por campo), no relajar esta.
    normalizado = normalizar(texto)
    if any(ruido in normalizado for ruido in _RUIDO):
        return ""
    return texto


def _sin_markdown(linea: str) -> str:
    sin_viñeta = re.sub(r"^\s*(?:[-*+•]|\d+[.)])\s+", "", linea)
    return re.sub(r"[*_#`]", "", sin_viñeta).strip()
