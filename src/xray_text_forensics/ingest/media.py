"""Media-type detection without executing the input."""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

_EXTENSION_TYPES = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".json": "application/json",
    ".csv": "text/csv",
    ".html": "text/html",
    ".htm": "text/html",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

TEXTUAL_MEDIA_TYPES = frozenset(
    {
        "text/plain",
        "text/markdown",
        "application/json",
        "text/csv",
        "text/html",
    }
)


def detect_media_type(data: bytes, filename: str | None = None) -> str:
    """Detect a conservative media type using signatures before file extensions."""

    if data.startswith(b"%PDF-"):
        return "application/pdf"

    if _looks_like_docx(data):
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    sample = data[:8192]
    ascii_sample = sample.decode("ascii", errors="ignore").lstrip()
    if re.match(r"(?is)<!doctype\s+html\b|<html\b|<head\b|<body\b", ascii_sample):
        return "text/html"

    if filename:
        extension = Path(filename).suffix.lower()
        if extension in _EXTENSION_TYPES:
            return _EXTENSION_TYPES[extension]

    if b"\x00" not in sample:
        return "text/plain"

    return "application/octet-stream"


def _looks_like_docx(data: bytes) -> bool:
    if not data.startswith(b"PK"):
        return False
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = set(archive.namelist())
    except (OSError, zipfile.BadZipFile):
        return False
    return "word/document.xml" in names
