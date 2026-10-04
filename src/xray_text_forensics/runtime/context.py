"""Build detector contexts from preserved ingestion results."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote, urlparse

from xray_text_forensics.detectors import AnalysisContext
from xray_text_forensics.ingest import IngestResult


def analysis_context_from_ingest(result: IngestResult) -> AnalysisContext:
    views = {view.view_id: view for view in result.views}
    view_text: dict[str, str] = {}

    for view in result.views:
        if view.storage_uri is None or view.encoding is None:
            continue
        data = _read_file_uri(view.storage_uri)
        view_text[view.view_id] = data.decode(view.encoding, errors="strict")

    return AnalysisContext(
        artifact=result.artifact,
        views=views,
        view_text=view_text,
    )


def _read_file_uri(uri: str) -> bytes:
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        raise ValueError(f"M2 local runtime only supports file:// view URIs, got {parsed.scheme!r}")

    path = Path(unquote(parsed.path))
    return path.read_bytes()
