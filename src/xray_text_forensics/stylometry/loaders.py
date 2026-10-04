"""Load versionable reference corpora from directories."""

from __future__ import annotations

import json
from pathlib import Path

from xray_text_forensics.corpus.loaders import load_directory
from xray_text_forensics.ingest import ForensicIngestor

from .models import ReferenceMetadata, ReferenceSet


def load_reference_root(
    root: Path,
    ingestor: ForensicIngestor,
) -> tuple[list[ReferenceSet], list[str]]:
    references: list[ReferenceSet] = []
    warnings: list[str] = []

    for directory in sorted(path for path in root.iterdir() if path.is_dir()):
        metadata_path = directory / ".xray-reference.json"
        if metadata_path.exists():
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
            payload.setdefault("label", directory.name)
            payload.setdefault("source", str(directory))
            metadata = ReferenceMetadata.model_validate(payload)
        else:
            metadata = ReferenceMetadata(label=directory.name, source=str(directory))

        documents, corpus_warnings = load_directory(directory, ingestor)
        warnings.extend(corpus_warnings)
        if not documents:
            warnings.append(f"{directory}: no usable reference documents")
            continue
        references.append(ReferenceSet(metadata=metadata, documents=documents))

    if not references:
        raise ValueError(f"No usable reference sets found under {root}")
    return references, warnings
