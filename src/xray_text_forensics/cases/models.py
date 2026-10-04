"""Case, relationship, and audit models."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from xray_text_forensics.core import Artifact, Case, DerivedView, DetectorRun, Evidence
from xray_text_forensics.core.models import utc_now


class Relationship(BaseModel):
    relationship_id: str = Field(default_factory=lambda: f"rel_{uuid4().hex}")
    case_id: str
    subject_id: str
    predicate: str
    object_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuditEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: f"audit_{uuid4().hex}")
    case_id: str
    action: str
    object_type: str
    object_id: str
    created_at: datetime = Field(default_factory=utc_now)
    details: dict[str, Any] = Field(default_factory=dict)
    previous_hash: str | None = None
    event_hash: str


class CaseBundle(BaseModel):
    case: Case
    artifacts: list[Artifact] = Field(default_factory=list)
    views: list[DerivedView] = Field(default_factory=list)
    runs: list[DetectorRun] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)
    audit_events: list[AuditEvent] = Field(default_factory=list)
    audit_verified: bool
