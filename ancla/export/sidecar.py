"""Reads the `<name>.yaml` sidecar next to a template resource.

Shared by every template-discovery module (`html_templates.py`, and
previously the removed `.docx` discovery in `templates.py`) so a template
someone is still preparing is skipped the same way everywhere, instead of
crashing the screen.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def read_yaml_sidecar(resource_path: Path) -> dict[str, Any] | None:
    """Reads and parses the `.yaml` sidecar next to a template resource
    (an `.html` fragment in `html_templates.py`). `None` when the sidecar
    is missing, invalid YAML, or not a mapping.
    """
    yaml_path = resource_path.with_suffix(".yaml")
    if not yaml_path.exists():
        return None
    try:
        datos = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return None
    if not isinstance(datos, dict):
        return None
    return datos
