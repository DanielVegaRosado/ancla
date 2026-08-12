"""Shared guard against zip bombs.

A zip can claim a huge uncompressed size while staying small on disk. Used
both when extracting text from an uploaded `.docx` (`extraction.py`) and
when restoring a profile backup (`store.py`) — same check, two call sites,
one shared function.
"""
from __future__ import annotations

import zipfile


def uncompressed_size(zip_: zipfile.ZipFile) -> int:
    """Sum of `file_size` across every entry, without extracting anything."""
    return sum(info.file_size for info in zip_.infolist())
