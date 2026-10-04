"""Base contract for detector plugins."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from xray_text_forensics.core import Artifact, DerivedView, Evidence, EvidenceFamily


class DetectorRequirements(BaseModel):
    raw_bytes: bool = False
    raw_unicode: bool = False
    language: bool = False
    tokenizer: bool = False
    secret_key: bool = False
    corpus: bool = False
    reference_corpus: bool = False


class DetectorDescriptor(BaseModel):
    detector_id: str
    version: str
    family: EvidenceFamily
    requirements: DetectorRequirements = Field(default_factory=DetectorRequirements)


class AnalysisContext(BaseModel):
    artifact: Artifact
    views: dict[str, DerivedView] = Field(default_factory=dict)
    resources: dict[str, Any] = Field(default_factory=dict)


class Detector(ABC):
    """A detector produces typed Evidence and must not mutate the Artifact."""

    @property
    @abstractmethod
    def descriptor(self) -> DetectorDescriptor:
        raise NotImplementedError

    @abstractmethod
    def analyze(self, context: AnalysisContext) -> list[Evidence]:
        raise NotImplementedError
