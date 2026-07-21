"""Textos de presentación compartidos entre plantillas.

`EstadoCV` (en `perfil/modelo.py`) son valores de dominio; sus etiquetas en
español son un detalle de la interfaz y no tienen por qué vivir en el mismo
sitio que el modelo.
"""
from __future__ import annotations

from cv_adaptativo.perfil.modelo import EstadoCV

ETIQUETAS_ESTADO = {
    EstadoCV.BORRADOR: "Borrador",
    EstadoCV.ENVIADO: "Enviado",
    EstadoCV.ENTREVISTA: "Entrevista",
    EstadoCV.DESCARTADO: "Descartado",
    EstadoCV.ACEPTADO: "Aceptado",
}
