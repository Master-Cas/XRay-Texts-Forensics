from xray_text_forensics.core import Artifact, Evidence, EvidenceFamily, EvidenceStatus
from xray_text_forensics.detectors import (
    AnalysisContext,
    Detector,
    DetectorDescriptor,
    DetectorRequirements,
)


class DummyDetector(Detector):
    @property
    def descriptor(self) -> DetectorDescriptor:
        return DetectorDescriptor(
            detector_id="dummy.unicode",
            version="1.0.0",
            family=EvidenceFamily.UNICODE,
            requirements=DetectorRequirements(raw_unicode=True),
        )

    def analyze(self, context: AnalysisContext) -> list[Evidence]:
        return [
            Evidence(
                artifact_id=context.artifact.artifact_id,
                family=self.descriptor.family,
                status=EvidenceStatus.NOT_DETECTED,
                detector_id=self.descriptor.detector_id,
                detector_version=self.descriptor.version,
                finding="dummy",
            )
        ]


def test_detector_returns_typed_evidence() -> None:
    artifact = Artifact(
        sha256="0" * 64,
        byte_length=0,
        media_type="text/plain",
        acquisition_method="test",
    )
    result = DummyDetector().analyze(AnalysisContext(artifact=artifact))
    assert len(result) == 1
    assert result[0].family is EvidenceFamily.UNICODE
    assert result[0].status is EvidenceStatus.NOT_DETECTED
