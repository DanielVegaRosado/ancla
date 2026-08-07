"""The profile error, in its own module so there are no circular imports.

Raised by both `almacen` (files and folders) and `serializacion` (YAML
format), and neither one can import from the other without biting its tail.
"""
from __future__ import annotations


class ProfileError(Exception):
    """Failure reading or writing the profile, with a message for the user.

    The text is in Spanish and names the file: the web layer shows it as-is,
    never a Python traceback.
    """
