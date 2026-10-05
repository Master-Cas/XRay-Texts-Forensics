"""Full forensic scan orchestration for the web product.

This layer intentionally keeps evidence families separate. It exposes what XRay can
measure now and marks unavailable provenance tests as NOT_TESTABLE instead of silently
turning absence of a detector into a negative result.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from xray_text_forensics.core import Evidence, EvidenceStatus
from xray_text_forensics.corpus import CorpusDocument, CorpusEngine, CorpusSnapshot
from xray_text_forensics.detectors.unicode import UnicodeForensicsSuite
from xray_text_forensics.ingest import ForensicIngestor, IngestPolicy, IngestResult
from xray_text_forensics.runtime import analysis_context_from_ingest
from xray_text_forensics.storage import ContentAddressedStore
from xray_text_forensics.stylometry import (
    ReferenceComparator,
    ReferenceComparisonReport,
    StyleFingerprint,
    extract_style_fingerprint,
)
from xray_text_forensics.stylometry.loaders import load_reference_root

from .models import IngestResponse
from .settings import WebSettings

FamilyState = Literal["COMPLETE", "NOT_TESTABLE", "INSUFFICIENT_DATA", "ERROR"]
OriginState = Literal["NOT_TESTABLE", "REFERENCE_COMPARISON"]


class AnalysisFamilySummary(BaseModel):
    family: str
    title: str
    state: FamilyState
    summary: str


class OriginAssessment(BaseModel):
    state: OriginState
    headline: str
    explanation: str


class FullScanResponse(IngestResponse):
    unicode_evidence: list[Evidence]
    linguistic_snapshot: CorpusSnapshot | None = None
    style_fingerprint: StyleFingerprint | None = None
    reference_comparison: ReferenceComparisonReport | None = None
    family_summaries: list[AnalysisFamilySummary] = Field(default_factory=list)
    origin_assessment: OriginAssessment
    scientific_note: str = (
        "XRay keeps Unicode, linguistic, stylometric, watermark and provenance signals "
        "separate. Similarity to a reference corpus is not an authorship probability, "
        "and unavailable tests are reported as NOT_TESTABLE rather than NOT_DETECTED."
    )


def load_reference_comparator(
    settings: WebSettings,
) -> tuple[ReferenceComparator | None, int]:
    """Load optional versioned reference corpora without making them a startup requirement."""

    root = settings.reference_root
    if root is None or not root.exists() or not root.is_dir():
        return None, 0

    reference_objects = settings.data_root / "reference-objects"
    ingestor = ForensicIngestor(
        ContentAddressedStore(reference_objects),
        IngestPolicy(max_input_bytes=settings.max_upload_bytes),
    )
    try:
        references, warnings = load_reference_root(root, ingestor)
        return ReferenceComparator(references), len(warnings)
    except (OSError, ValueError):
        return None, 1


def run_full_scan(
    result: IngestResult,
    *,
    comparator: ReferenceComparator | None,
    reference_warning_count: int = 0,
) -> FullScanResponse:
    context = analysis_context_from_ingest(result)
    unicode_evidence = UnicodeForensicsSuite().analyze(context)
    base = IngestResponse.from_domain(result)

    selected = context.preferred_text_view()
    if selected is None:
        families = [
            _unicode_summary(unicode_evidence),
            AnalysisFamilySummary(
                family="linguistic_profile",
                title="Linguistic profile",
                state="NOT_TESTABLE",
                summary="No usable text view was available for linguistic analysis.",
            ),
            _reference_unavailable_summary(comparator, reference_warning_count),
            _watermark_summary(),
        ]
        return FullScanResponse(
            **base.model_dump(),
            unicode_evidence=unicode_evidence,
            family_summaries=families,
            origin_assessment=_origin_assessment(None),
        )

    _, text = selected
    document = CorpusDocument(
        document_id=result.artifact.artifact_id,
        text=text,
        metadata={"source": "suspect"},
    )
    corpus = CorpusEngine([document], name="suspect")
    linguistic_snapshot = corpus.snapshot()
    style_fingerprint = extract_style_fingerprint(text)

    reference_report: ReferenceComparisonReport | None = None
    if comparator is not None:
        reference_report = comparator.compare(text)

    families = [
        _unicode_summary(unicode_evidence),
        _linguistic_summary(linguistic_snapshot),
        _reference_summary(reference_report, comparator, reference_warning_count),
        _watermark_summary(),
    ]

    return FullScanResponse(
        **base.model_dump(),
        unicode_evidence=unicode_evidence,
        linguistic_snapshot=linguistic_snapshot,
        style_fingerprint=style_fingerprint,
        reference_comparison=reference_report,
        family_summaries=families,
        origin_assessment=_origin_assessment(reference_report),
    )


def _unicode_summary(evidence: list[Evidence]) -> AnalysisFamilySummary:
    detected = [item for item in evidence if item.status is EvidenceStatus.DETECTED]
    noteworthy = [
        item
        for item in detected
        if item.finding
        not in {
            "NORMALIZATION_DIFFERENCE",
            "SPACE_VARIANT",
            "VARIATION_SELECTOR",
        }
    ]
    if noteworthy:
        return AnalysisFamilySummary(
            family="unicode",
            title="Unicode and invisible characters",
            state="COMPLETE",
            summary=(
                f"{len(noteworthy)} Unicode pattern(s) deserve contextual review. "
                "This is encoding evidence, not AI-authorship evidence."
            ),
        )
    if detected:
        return AnalysisFamilySummary(
            family="unicode",
            title="Unicode and invisible characters",
            state="COMPLETE",
            summary=(
                "Only descriptive Unicode differences were found. They do not by themselves "
                "indicate manipulation, watermarking or AI authorship."
            ),
        )
    return AnalysisFamilySummary(
        family="unicode",
        title="Unicode and invisible characters",
        state="COMPLETE",
        summary="No unusual Unicode pattern covered by this scan was detected.",
    )


def _linguistic_summary(snapshot: CorpusSnapshot) -> AnalysisFamilySummary:
    if snapshot.token_count < 40:
        return AnalysisFamilySummary(
            family="linguistic_profile",
            title="Linguistic profile",
            state="INSUFFICIENT_DATA",
            summary=(
                f"The text contains {snapshot.token_count} tokens. A profile was extracted, "
                "but the sample is short for meaningful reference comparison."
            ),
        )
    return AnalysisFamilySummary(
        family="linguistic_profile",
        title="Linguistic profile",
        state="COMPLETE",
        summary=(
            f"Profile extracted from {snapshot.token_count} tokens across "
            f"{snapshot.context_count} sentence contexts."
        ),
    )


def _reference_unavailable_summary(
    comparator: ReferenceComparator | None,
    warning_count: int,
) -> AnalysisFamilySummary:
    if comparator is not None:
        return AnalysisFamilySummary(
            family="reference_stylometry",
            title="Reference-corpus comparison",
            state="ERROR",
            summary="Reference corpora loaded but the document could not be compared.",
        )
    suffix = " The configured reference library could not be loaded." if warning_count else ""
    return AnalysisFamilySummary(
        family="reference_stylometry",
        title="Reference-corpus comparison",
        state="NOT_TESTABLE",
        summary=(
            "No versioned reference corpus is configured, so XRay cannot compare this text "
            "with known human or model samples yet." + suffix
        ),
    )


def _reference_summary(
    report: ReferenceComparisonReport | None,
    comparator: ReferenceComparator | None,
    warning_count: int,
) -> AnalysisFamilySummary:
    if report is None:
        return _reference_unavailable_summary(comparator, warning_count)

    if not report.comparisons:
        return AnalysisFamilySummary(
            family="reference_stylometry",
            title="Reference-corpus comparison",
            state="NOT_TESTABLE",
            summary="The configured reference library produced no usable comparison.",
        )

    best_style = max(report.comparisons, key=lambda item: item.style_similarity)
    best_char = max(report.comparisons, key=lambda item: item.char_svd_similarity)
    return AnalysisFamilySummary(
        family="reference_stylometry",
        title="Reference-corpus comparison",
        state="COMPLETE",
        summary=(
            f"Closest style reference: {best_style.label}. "
            f"Closest character-pattern reference: {best_char.label}. "
            "These are similarities, not provider probabilities."
        ),
    )


def _watermark_summary() -> AnalysisFamilySummary:
    return AnalysisFamilySummary(
        family="watermark",
        title="Verified watermark",
        state="NOT_TESTABLE",
        summary=(
            "No authorized provider-specific watermark detector, tokenizer and key are "
            "configured for this scan. XRay will not report NOT_DETECTED when the test "
            "cannot actually be performed."
        ),
    )


def _origin_assessment(
    report: ReferenceComparisonReport | None,
) -> OriginAssessment:
    if report is None or not report.comparisons:
        return OriginAssessment(
            state="NOT_TESTABLE",
            headline="Origin cannot be assessed yet",
            explanation=(
                "The document was inspected for Unicode and linguistic structure, but XRay "
                "does not yet have a configured versioned reference library for human/model "
                "comparison. No AI-origin verdict is produced from Unicode alone."
            ),
        )

    style = max(report.comparisons, key=lambda item: item.style_similarity)
    chars = max(report.comparisons, key=lambda item: item.char_svd_similarity)
    content = max(report.comparisons, key=lambda item: item.content_similarity)
    return OriginAssessment(
        state="REFERENCE_COMPARISON",
        headline="Reference comparison available",
        explanation=(
            f"Closest style corpus: {style.label}; closest character-pattern corpus: "
            f"{chars.label}; closest content corpus: {content.label}. These independent "
            "similarities are shown separately and are not converted into an AI probability."
        ),
    )
