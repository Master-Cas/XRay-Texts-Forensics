"""Tenant-scoped reference corpus management for M17.

Reference texts are user-supplied known-origin samples. They are kept inside the
authenticated tenant's opaque storage root and are never shared across tenants.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field

from xray_text_forensics.corpus.loaders import load_directory
from xray_text_forensics.ingest import ForensicIngestor, IngestPolicy
from xray_text_forensics.storage import ContentAddressedStore
from xray_text_forensics.stylometry import (
    ReferenceComparator,
    ReferenceMetadata,
    ReferenceSet,
)

from .tenant_storage import TenantStorage

_ALLOWED_SUFFIXES = {".txt", ".md", ".json", ".csv", ".html", ".docx", ".odt", ".pdf"}
_SLUG_RE = re.compile(r"[^a-z0-9]+")
_MIN_REFERENCE_SETS = 2
_MIN_DOCUMENTS_PER_SET = 5


class ReferenceSetCreate(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    provider: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=160)
    model_version: str | None = Field(default=None, max_length=160)
    language: str | None = Field(default=None, max_length=40)
    topic: str | None = Field(default=None, max_length=120)
    source: str = Field(default="user-upload", min_length=1, max_length=300)
    license: str | None = Field(default=None, max_length=120)


class ReferenceSetSummary(BaseModel):
    slug: str
    label: str
    provider: str | None = None
    model: str | None = None
    model_version: str | None = None
    language: str | None = None
    topic: str | None = None
    source: str
    license: str | None = None
    document_count: int


class ReferenceDocumentResponse(BaseModel):
    set_slug: str
    filename: str
    sha256: str
    added: bool


@dataclass(frozen=True, slots=True)
class ReferenceComparatorState:
    comparator: ReferenceComparator | None
    warning_count: int
    unavailable_reason: str | None
    configured: bool


class TenantReferenceLibrary:
    def __init__(self, *, max_input_bytes: int) -> None:
        self.max_input_bytes = max_input_bytes

    def list_sets(self, storage: TenantStorage) -> list[ReferenceSetSummary]:
        root = storage.reference_root
        root.mkdir(parents=True, exist_ok=True)
        summaries: list[ReferenceSetSummary] = []
        for directory in sorted(path for path in root.iterdir() if path.is_dir()):
            metadata = self._read_metadata(directory)
            if metadata is None:
                continue
            summaries.append(
                ReferenceSetSummary(
                    slug=directory.name,
                    label=metadata.label,
                    provider=metadata.provider,
                    model=metadata.model,
                    model_version=metadata.model_version,
                    language=metadata.language,
                    topic=metadata.topic,
                    source=metadata.source,
                    license=metadata.license,
                    document_count=self._document_count(directory),
                )
            )
        return summaries

    def create_set(
        self,
        storage: TenantStorage,
        payload: ReferenceSetCreate,
    ) -> ReferenceSetSummary:
        slug = _slugify(payload.label)
        directory = storage.reference_root / slug
        if directory.exists():
            raise ValueError("A reference set with this label already exists")
        directory.mkdir(parents=True, exist_ok=False)

        metadata = ReferenceMetadata(
            label=payload.label.strip(),
            provider=_clean_optional(payload.provider),
            model=_clean_optional(payload.model),
            model_version=_clean_optional(payload.model_version),
            language=_clean_optional(payload.language),
            topic=_clean_optional(payload.topic),
            source=payload.source.strip(),
            license=_clean_optional(payload.license),
        )
        self._metadata_path(directory).write_text(
            json.dumps(metadata.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return ReferenceSetSummary(
            slug=slug,
            label=metadata.label,
            provider=metadata.provider,
            model=metadata.model,
            model_version=metadata.model_version,
            language=metadata.language,
            topic=metadata.topic,
            source=metadata.source,
            license=metadata.license,
            document_count=0,
        )

    def add_document(
        self,
        storage: TenantStorage,
        set_slug: str,
        *,
        filename: str,
        data: bytes,
    ) -> ReferenceDocumentResponse:
        directory = self._resolve_set(storage, set_slug)
        suffix = Path(filename).suffix.casefold()
        if suffix not in _ALLOWED_SUFFIXES:
            raise ValueError(
                "Reference documents must be TXT, Markdown, JSON, CSV, HTML, DOCX, ODT or PDF"
            )
        if not data:
            raise ValueError("Reference document is empty")
        if len(data) > self.max_input_bytes:
            raise ValueError(f"Reference document exceeds {self.max_input_bytes} byte limit")

        digest = hashlib.sha256(data).hexdigest()
        target_name = f"{digest}{suffix}"
        target = directory / target_name
        added = not target.exists()
        if added:
            target.write_bytes(data)

        return ReferenceDocumentResponse(
            set_slug=directory.name,
            filename=target_name,
            sha256=digest,
            added=added,
        )

    def comparator_for(
        self,
        storage: TenantStorage,
    ) -> ReferenceComparatorState:
        sets = self.list_sets(storage)
        if not sets:
            return ReferenceComparatorState(
                comparator=None,
                warning_count=0,
                unavailable_reason=None,
                configured=False,
            )

        eligible = [
            item
            for item in sets
            if item.document_count >= _MIN_DOCUMENTS_PER_SET
        ]
        if len(eligible) < _MIN_REFERENCE_SETS:
            return ReferenceComparatorState(
                comparator=None,
                warning_count=0,
                unavailable_reason=(
                    "Reference comparison needs at least "
                    f"{_MIN_REFERENCE_SETS} reference sets with "
                    f"{_MIN_DOCUMENTS_PER_SET} usable samples each. "
                    f"Ready sets: {len(eligible)}/{_MIN_REFERENCE_SETS}."
                ),
                configured=True,
            )

        ingestor = ForensicIngestor(
            ContentAddressedStore(storage.reference_object_store_root),
            IngestPolicy(max_input_bytes=self.max_input_bytes),
        )
        references: list[ReferenceSet] = []
        warnings: list[str] = []
        for summary in eligible:
            directory = storage.reference_root / summary.slug
            metadata = self._read_metadata(directory)
            if metadata is None:
                warnings.append(f"{summary.slug}: metadata unavailable")
                continue
            documents, corpus_warnings = load_directory(directory, ingestor)
            warnings.extend(corpus_warnings)
            if len(documents) < _MIN_DOCUMENTS_PER_SET:
                warnings.append(
                    f"{summary.slug}: only {len(documents)} usable samples after ingestion"
                )
                continue
            references.append(
                ReferenceSet(
                    metadata=metadata,
                    documents=documents,
                )
            )

        if len(references) < _MIN_REFERENCE_SETS:
            return ReferenceComparatorState(
                comparator=None,
                warning_count=len(warnings),
                unavailable_reason=(
                    "Reference samples were configured, but fewer than "
                    f"{_MIN_REFERENCE_SETS} sets retained "
                    f"{_MIN_DOCUMENTS_PER_SET} usable samples after ingestion."
                ),
                configured=True,
            )

        try:
            comparator = ReferenceComparator(references)
        except ValueError:
            return ReferenceComparatorState(
                comparator=None,
                warning_count=len(warnings) + 1,
                unavailable_reason="The reference library could not build a comparison model.",
                configured=True,
            )
        return ReferenceComparatorState(
            comparator=comparator,
            warning_count=len(warnings),
            unavailable_reason=None,
            configured=True,
        )

    def _resolve_set(self, storage: TenantStorage, set_slug: str) -> Path:
        if set_slug != _slugify(set_slug):
            raise ValueError("Invalid reference set identifier")
        directory = storage.reference_root / set_slug
        if not directory.is_dir() or self._read_metadata(directory) is None:
            raise KeyError(set_slug)
        return directory

    @staticmethod
    def _metadata_path(directory: Path) -> Path:
        return directory / ".xray-reference.json"

    def _read_metadata(self, directory: Path) -> ReferenceMetadata | None:
        path = self._metadata_path(directory)
        if not path.is_file():
            return None
        try:
            return ReferenceMetadata.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    @staticmethod
    def _document_count(directory: Path) -> int:
        return sum(
            1
            for path in directory.iterdir()
            if path.is_file() and path.name != ".xray-reference.json"
        )


def _slugify(value: str) -> str:
    slug = _SLUG_RE.sub("-", value.strip().casefold()).strip("-")
    if not slug or len(slug) > 80:
        raise ValueError("Reference set label does not produce a valid identifier")
    return slug


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None
