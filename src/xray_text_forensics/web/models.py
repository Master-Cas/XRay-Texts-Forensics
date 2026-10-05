"""Sanitized HTTP response models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from xray_text_forensics.cases import CaseBundle, Relationship
from xray_text_forensics.core import (
    Artifact,
    Case,
    DerivedView,
    DetectorRun,
    Evidence,
    ViewKind,
)
from xray_text_forensics.ingest import IngestResult, IngestWarning

from .jobs import JobRecord, JobStatus


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "xray-texts-forensics"
    api_version: str = "v1"
    build_sha: str | None = None


class ReadinessResponse(BaseModel):
    status: str
    checks: dict[str, str]
    schema_version: int | None = None
    environment: str
    build_sha: str | None = None


class JobResponse(BaseModel):
    job_id: str
    kind: str
    status: JobStatus
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_domain(cls, job: JobRecord) -> JobResponse:
        return cls(
            job_id=job.job_id,
            kind=job.kind,
            status=job.status,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
            result=job.result,
            error="Job failed" if job.status is JobStatus.FAILED else None,
            metadata=job.metadata,
        )


class ArtifactResponse(BaseModel):
    artifact_id: str
    sha256: str
    byte_length: int
    media_type: str
    original_filename: str | None
    acquired_at: datetime
    acquisition_method: str
    detected_encoding: str | None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_domain(cls, artifact: Artifact) -> ArtifactResponse:
        return cls(
            artifact_id=artifact.artifact_id,
            sha256=artifact.sha256,
            byte_length=artifact.byte_length,
            media_type=artifact.media_type,
            original_filename=artifact.original_filename,
            acquired_at=artifact.acquired_at,
            acquisition_method=artifact.acquisition_method,
            detected_encoding=artifact.detected_encoding,
            metadata=artifact.metadata,
        )


class ViewResponse(BaseModel):
    view_id: str
    artifact_id: str
    kind: ViewKind
    content_sha256: str
    byte_length: int
    media_type: str
    transformation: str
    transformation_version: str
    encoding: str | None
    parameters: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    @classmethod
    def from_domain(cls, view: DerivedView) -> ViewResponse:
        return cls(
            view_id=view.view_id,
            artifact_id=view.artifact_id,
            kind=view.kind,
            content_sha256=view.content_sha256,
            byte_length=view.byte_length,
            media_type=view.media_type,
            transformation=view.transformation,
            transformation_version=view.transformation_version,
            encoding=view.encoding,
            parameters=view.parameters,
            created_at=view.created_at,
        )


class IngestResponse(BaseModel):
    artifact: ArtifactResponse
    views: list[ViewResponse]
    warnings: list[IngestWarning]

    @classmethod
    def from_domain(cls, result: IngestResult) -> IngestResponse:
        return cls(
            artifact=ArtifactResponse.from_domain(result.artifact),
            views=[ViewResponse.from_domain(view) for view in result.views],
            warnings=result.warnings,
        )


class UnicodeAnalysisResponse(IngestResponse):
    evidence: list[Evidence]


class CaseCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class CaseBundleResponse(BaseModel):
    case: Case
    artifacts: list[ArtifactResponse]
    views: list[ViewResponse]
    runs: list[DetectorRun]
    evidence: list[Evidence]
    relationships: list[Relationship]
    audit_verified: bool
    audit_event_count: int

    @classmethod
    def from_domain(cls, bundle: CaseBundle) -> CaseBundleResponse:
        return cls(
            case=bundle.case,
            artifacts=[ArtifactResponse.from_domain(item) for item in bundle.artifacts],
            views=[ViewResponse.from_domain(item) for item in bundle.views],
            runs=bundle.runs,
            evidence=bundle.evidence,
            relationships=bundle.relationships,
            audit_verified=bundle.audit_verified,
            audit_event_count=len(bundle.audit_events),
        )
