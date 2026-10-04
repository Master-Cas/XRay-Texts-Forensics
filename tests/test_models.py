import pytest
from pydantic import ValidationError

from xray_text_forensics.core import Artifact, Evidence, EvidenceFamily, EvidenceStatus


def test_frozen_evidence_status_vocabulary() -> None:
    assert {status.value for status in EvidenceStatus} == {
        "DETECTED",
        "NOT_DETECTED",
        "INCONCLUSIVE",
        "NOT_TESTABLE",
        "INSUFFICIENT_DATA",
        "ERROR",
    }


def test_not_testable_requires_reason() -> None:
    with pytest.raises(ValidationError):
        Evidence(
            artifact_id="art_1",
            family=EvidenceFamily.WATERMARK,
            status=EvidenceStatus.NOT_TESTABLE,
            detector_id="synthid",
            detector_version="0.1.0",
        )


def test_not_testable_is_not_not_detected() -> None:
    assert EvidenceStatus.NOT_TESTABLE is not EvidenceStatus.NOT_DETECTED


def test_artifact_rejects_invalid_sha256() -> None:
    with pytest.raises(ValidationError):
        Artifact(
            sha256="abc",
            byte_length=3,
            media_type="text/plain",
            acquisition_method="upload",
        )


def test_artifact_normalizes_sha256_to_lowercase() -> None:
    artifact = Artifact(
        sha256="A" * 64,
        byte_length=1,
        media_type="text/plain",
        acquisition_method="upload",
    )
    assert artifact.sha256 == "a" * 64
