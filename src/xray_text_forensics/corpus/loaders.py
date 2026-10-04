"""Load corpus documents through the forensic ingestion layer."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from xray_text_forensics.ingest import ForensicIngestor
from xray_text_forensics.runtime import analysis_context_from_ingest

from .models import CorpusDocument

_SUPPORTED = {".txt", ".md", ".markdown", ".json", ".csv", ".html", ".htm", ".docx", ".pdf"}


def load_directory(
    root: Path,
    ingestor: ForensicIngestor,
) -> tuple[list[CorpusDocument], list[str]]:
    documents: list[CorpusDocument] = []
    warnings: list[str] = []

    for path in _iter_supported(root):
        result = ingestor.ingest_path(path)
        context = analysis_context_from_ingest(result)
        selected = context.preferred_text_view()
        if selected is None:
            warnings.append(f"{path}: no text view")
            continue
        _, text = selected
        documents.append(
            CorpusDocument(
                document_id=result.artifact.artifact_id,
                text=text,
                metadata={
                    "filename": path.name,
                    "source": str(path),
                    "sha256": result.artifact.sha256,
                },
            )
        )
        warnings.extend(f"{path}: {warning.code}: {warning.message}" for warning in result.warnings)

    return documents, warnings


def _iter_supported(root: Path) -> Iterable[Path]:
    if not root.is_dir():
        raise ValueError(f"Corpus path is not a directory: {root}")
    for path in sorted(root.rglob("*")):
        if path.name == ".xray-reference.json":
            continue
        if path.is_file() and path.suffix.lower() in _SUPPORTED:
            yield path
