"""Guards the templates against the model drifting away from them.

Jinja resolves an attribute that does not exist to Undefined and renders it
as an empty string, so a field renamed in `model.py` and forgotten in a
template fails silently: the form shows the value as empty and, since
saving writes back whatever the box holds, the stored value is wiped. That
is how `experiencia.estado` survived the rename to `status`, and how
`{GRUPO_A_1}` survived in the "About me" help — same rename, same silence.

Reading a name off the model is deliberate: hardcoding the list here would
drift exactly like the templates did.
"""
from __future__ import annotations

import re
from dataclasses import fields
from pathlib import Path

from ancla.profile import model

TEMPLATES = Path(__file__).resolve().parent.parent / "ancla" / "web" / "templates"

# The Jinja variable each screen uses for a model object, and the class
# behind it. Anything not listed here is out of this test's reach.
VARIABLES = {
    "experiencia": model.Experience,
    "educacion": model.Education,
    "perfil": model.Profile,
    "propuesta": model.Proposal,
    "sobre_mi": model.AboutMe,
}


def _known_names(clase: type) -> set[str]:
    return {campo.name for campo in fields(clase)} | {
        nombre for nombre in dir(clase) if not nombre.startswith("_")
    }


def test_las_plantillas_solo_usan_atributos_que_el_modelo_tiene():
    huerfanos = []
    patron = re.compile(r"\b(" + "|".join(VARIABLES) + r")\.([a-z_]+)")
    for plantilla in sorted(TEMPLATES.glob("*.html")):
        texto = plantilla.read_text(encoding="utf-8")
        for variable, atributo in patron.findall(texto):
            if atributo not in _known_names(VARIABLES[variable]):
                huerfanos.append(f"{plantilla.name}: {variable}.{atributo}")

    assert not huerfanos, "Atributos que el modelo ya no tiene: " + ", ".join(huerfanos)
