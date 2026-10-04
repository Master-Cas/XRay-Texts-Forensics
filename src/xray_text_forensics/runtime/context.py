"""Build detector contexts from preserved ingestion results."""

from __future__ import annotations

import os
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
    return _file_uri_to_path(uri).read_bytes()


def _file_uri_to_path(
    uri: str,
    *,
    windows: bool | None = None,
) -> Path:
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        raise ValueError(
            f"M2 local runtime only supports file:// view URIs, got {parsed.scheme!r}"
        )

    is_windows = os.name == "nt" if windows is None else windows
    decoded_path = unquote(parsed.path)

    if is_windows:
        # pathlib.Path.as_uri() emits Windows drive URIs as file:///C:/...
        # The first slash belongs to URI syntax, not to the Windows filesystem path.
        if (
            len(decoded_path) >= 3
            and decoded_path[0] == "/"
            and decoded_path[1].isalpha()
            and decoded_path[2] == ":"
        ):
            decoded_path = decoded_path[1:]

        if parsed.netloc and parsed.netloc.casefold() != "localhost":
            decoded_path = f"//{parsed.netloc}{decoded_path}"
    elif parsed.netloc and parsed.netloc.casefold() != "localhost":
        decoded_path = f"//{parsed.netloc}{decoded_path}"

    return Path(decoded_path)
