"""One screen, one module: `profile`, `adapt`, `proposal`, `cvs`, `settings`,
`support`, `canva_templates`, `import_cv`, `terms`. Each registers its routes
on `ancla.web.blueprint.bp` when imported — importing this package is all
it takes for every route to be registered.
"""
from __future__ import annotations

from ancla.web.views import (
    adapt,
    canva_templates,
    cvs,
    import_cv,
    profile,
    proposal,
    settings,
    support,
    terms,
)

__all__ = [
    "adapt",
    "canva_templates",
    "cvs",
    "import_cv",
    "profile",
    "proposal",
    "settings",
    "support",
    "terms",
]
