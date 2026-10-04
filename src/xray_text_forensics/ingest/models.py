"""Models used by the forensic ingestion pipeline."""

from __future__ import annotations

from pydantic import BaseModel, Field

from xray_text_forensics.core import Artifact, DerivedView


class IngestPolicy(BaseModel):
    max_input_bytes: int = Field(default=100 * 1024 * 1024, gt=0)
    max_archive_entries: int = Field(default=10_000, gt=0)
    max_archive_uncompressed_bytes: int = Field(default=512 * 1024 * 1024, gt=0)
    max_extracted_text_chars: int = Field(default=20_000_000, gt=0)
    max_pdf_pages: int = Field(default=5_000, gt=0)


class IngestWarning(BaseModel):
    code: str
    message: str
    details: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class IngestResult(BaseModel):
    artifact: Artifact
    views: list[DerivedView] = Field(default_factory=list)
    warnings: list[IngestWarning] = Field(default_factory=list)
