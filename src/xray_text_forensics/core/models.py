"""Typed domain models for XRay's scientific contract."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def utc_now() -> datetime:
    return datetime.now(UTC)


class EvidenceStatus(StrEnum):
    DETECTED = "DETECTED"
    NOT_DETECTED = "NOT_DETECTED"
    INCONCLUSIVE = "INCONCLUSIVE"
    NOT_TESTABLE = "NOT_TESTABLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    ERROR = "ERROR"


class EvidenceFamily(StrEnum):
    WATERMARK = "WATERMARK"
    STYLOMETRY = "STYLOMETRY"
    UNICODE = "UNICODE"
    SIMILARITY = "SIMILARITY"
    MANIPULATION = "MANIPULATION"
    PROVENANCE = "PROVENANCE"


class ViewKind(StrEnum):
    RAW_BYTES = "RAW_BYTES"
    RAW_UNICODE = "RAW_UNICODE"
    EXTRACTED_TEXT = "EXTRACTED_TEXT"
    NFC = "NFC"
    NFKC = "NFKC"
    TOKENIZED = "TOKENIZED"
    LEMMATIZED = "LEMMATIZED"
    CUSTOM = "CUSTOM"


class Artifact(BaseModel):
    artifact_id: str = Field(default_factory=lambda: _id("art"))
    sha256: str
    byte_length: int = Field(ge=0)
    media_type: str
    original_filename: str | None = None
    acquired_at: datetime = Field(default_factory=utc_now)
    acquisition_method: str
    source_declared: str | None = None
    storage_uri: str | None = None
    detected_encoding: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        normalized = value.lower()
        if len(normalized) != 64 or any(c not in "0123456789abcdef" for c in normalized):
            raise ValueError("sha256 must contain exactly 64 hexadecimal characters")
        return normalized


class DerivedView(BaseModel):
    view_id: str = Field(default_factory=lambda: _id("view"))
    artifact_id: str
    kind: ViewKind
    content_sha256: str
    byte_length: int = Field(ge=0)
    media_type: str
    transformation: str
    transformation_version: str
    encoding: str | None = None
    storage_uri: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("content_sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        normalized = value.lower()
        if len(normalized) != 64 or any(c not in "0123456789abcdef" for c in normalized):
            raise ValueError("content_sha256 must contain exactly 64 hexadecimal characters")
        return normalized


class EvidenceLocation(BaseModel):
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    label: str | None = None

    @model_validator(mode="after")
    def end_not_before_start(self) -> EvidenceLocation:
        if self.end < self.start:
            raise ValueError("location end must be >= start")
        return self


class Evidence(BaseModel):
    evidence_id: str = Field(default_factory=lambda: _id("ev"))
    artifact_id: str
    family: EvidenceFamily
    status: EvidenceStatus
    detector_id: str
    detector_version: str
    finding: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    reason: str | None = None
    derived_view_id: str | None = None
    locations: list[EvidenceLocation] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def require_reason_for_non_test(self) -> Evidence:
        if self.status in {
            EvidenceStatus.NOT_TESTABLE,
            EvidenceStatus.INSUFFICIENT_DATA,
            EvidenceStatus.ERROR,
        } and not self.reason:
            raise ValueError(f"{self.status} evidence requires a reason")
        return self


class DetectorRun(BaseModel):
    run_id: str = Field(default_factory=lambda: _id("run"))
    detector_id: str
    detector_version: str
    artifact_id: str
    view_ids: list[str] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    error: str | None = None


class Case(BaseModel):
    case_id: str = Field(default_factory=lambda: _id("case"))
    title: str
    created_at: datetime = Field(default_factory=utc_now)
    artifact_ids: list[str] = Field(default_factory=list)
    detector_run_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class Corpus(BaseModel):
    corpus_id: str = Field(default_factory=lambda: _id("corpus"))
    name: str
    artifact_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReferenceCorpus(Corpus):
    provider: str | None = None
    model: str | None = None
    model_version: str | None = None
    language: str | None = None
    topic: str | None = None
    source: str
    license: str | None = None
