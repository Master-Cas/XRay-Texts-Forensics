"""Full forensic scan orchestration for the web product.

This layer intentionally keeps evidence families separate. It exposes what XRay can
measure now and marks unavailable provenance tests as NOT_TESTABLE instead of silently
turning absence of a detector into a negative result.
"""

from __future__ import annotations

import math

from typing import Any, Literal, cast

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

from .composite import CompositeClassifier
from .models import IngestResponse
from .settings import WebSettings

FamilyState = Literal["COMPLETE", "NOT_TESTABLE", "INSUFFICIENT_DATA", "ERROR"]
OriginState = Literal["NOT_TESTABLE", "REFERENCE_COMPARISON"]
AuthorshipState = Literal["AI_LIKELY", "HUMAN_LIKELY", "INCONCLUSIVE", "NOT_TESTABLE", "ERROR"]


class AnalysisFamilySummary(BaseModel):
    family: str
    title: str
    state: FamilyState
    summary: str


class OriginAssessment(BaseModel):
    state: OriginState
    headline: str
    explanation: str


class AuthorshipAssessment(BaseModel):
    state: AuthorshipState
    headline: str
    explanation: str
    disclaimer: str = "Clasificación estadística, no prueba criptográfica de procedencia."
    eligible: bool | None = None
    original_tokens: int | None = None
    ai_likely: bool | None = None
    human_likely: bool | None = None
    diagnostics: dict[str, float | int | bool | str | None] = Field(default_factory=dict)
    versions: dict[str, str] = Field(default_factory=dict)


class FullScanResponse(IngestResponse):
    unicode_evidence: list[Evidence]
    linguistic_snapshot: CorpusSnapshot | None = None
    style_fingerprint: StyleFingerprint | None = None
    reference_comparison: ReferenceComparisonReport | None = None
    family_summaries: list[AnalysisFamilySummary] = Field(default_factory=list)
    origin_assessment: OriginAssessment
    authorship_assessment: AuthorshipAssessment
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
    reference_unavailable_reason: str | None = None,
    authorship_classifier: CompositeClassifier | None = None,
    authorship_unavailable_reason: str | None = None,
) -> FullScanResponse:
    context = analysis_context_from_ingest(result)
    unicode_evidence = UnicodeForensicsSuite().analyze(context)
    base = IngestResponse.from_domain(result)

    selected = context.preferred_text_view()
    if selected is None:
        authorship = _authorship_assessment(
            None,
            authorship_classifier,
            authorship_unavailable_reason,
        )
        families = [
            _authorship_summary(authorship),
            _unicode_summary(unicode_evidence),
            AnalysisFamilySummary(
                family="linguistic_profile",
                title="Linguistic profile",
                state="NOT_TESTABLE",
                summary="No usable text view was available for linguistic analysis.",
            ),
            _reference_unavailable_summary(
                comparator,
                reference_warning_count,
                reference_unavailable_reason,
            ),
            _watermark_summary(),
        ]
        return FullScanResponse(
            **base.model_dump(),
            unicode_evidence=unicode_evidence,
            family_summaries=families,
            origin_assessment=_origin_assessment(None),
            authorship_assessment=authorship,
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

    authorship = _authorship_assessment(
        text,
        authorship_classifier,
        authorship_unavailable_reason,
    )

    families = [
        _authorship_summary(authorship),
        _unicode_summary(unicode_evidence),
        _linguistic_summary(linguistic_snapshot),
        _reference_summary(
            reference_report,
            comparator,
            reference_warning_count,
            reference_unavailable_reason,
        ),
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
        authorship_assessment=authorship,
    )


def _validate_authorship_result(value: object) -> dict[str, Any]:
    """Strict integration schema; no thresholds or scientific logic are changed."""
    if not isinstance(value, dict):
        raise ValueError("Invalid composite response")
    state = value.get("state")
    eligible = value.get("eligible")
    ai = value.get("ai_likely")
    human = value.get("human_likely")
    tokens = value.get("original_tokens")
    if type(state) is not str or state not in {"AI_LIKELY", "HUMAN_LIKELY", "INCONCLUSIVE"}:
        raise ValueError("Unknown composite state")
    if type(eligible) is not bool or type(ai) is not bool or type(human) is not bool:
        raise ValueError("Invalid channel booleans")
    if type(tokens) is not int or tokens < 0:
        raise ValueError("Invalid token count")
    if not eligible and (ai or human or state != "INCONCLUSIVE"):
        raise ValueError("An ineligible row cannot be positive")
    expected = "AI_LIKELY" if ai else "HUMAN_LIKELY" if human else "INCONCLUSIVE"
    if state != expected:
        raise ValueError("Frozen precedence contradiction")
    mandatory = (
        "parent_score", "specialist_score", "p_human",
        "human_density_score", "human_score",
    )
    if any(name not in value for name in mandatory):
        raise ValueError("Missing composite diagnostics")
    for key in (*mandatory, "combined_score"):
        v = value.get(key)
        if v is not None and (type(v) not in (float, int) or not math.isfinite(v)):
            raise ValueError("Invalid numeric diagnostic")
    prob = value.get("p_human")
    if prob is not None and not 0.0 <= prob <= 1.0:
        raise ValueError("Invalid probability")
    if eligible and any(value.get(key) is None for key in mandatory):
        raise ValueError("Eligible sample missing scores")
    versions = value.get("versions")
    if not isinstance(versions, dict) or not versions:
        raise ValueError("Missing frozen identifiers")
    if any(
        not isinstance(k, str) or not k or not isinstance(v, str) or not v
        for k, v in versions.items()
    ):
        raise ValueError("Invalid frozen identifiers")
    return value


def _authorship_assessment(
    text: str | None,
    classifier: CompositeClassifier | None,
    unavailable_reason: str | None,
) -> AuthorshipAssessment:
    if text is None:
        return AuthorshipAssessment(
            state="NOT_TESTABLE",
            headline="Authorship classifier not testable",
            explanation="No usable text view was available for the frozen authorship classifier.",
        )
    if classifier is None:
        if unavailable_reason:
            return AuthorshipAssessment(
                state="ERROR",
                headline="Authorship classifier initialization error",
                explanation="A configured frozen runtime failed verification or initialization.",
            )
        return AuthorshipAssessment(
            state="NOT_TESTABLE",
            headline="Authorship classifier unavailable",
            explanation="The frozen XTF composite runtime is not configured for this deployment.",
        )
    try:
        result = _validate_authorship_result(classifier.classify(text))
        state = cast(AuthorshipState, result["state"])
        explanations = {
            "AI_LIKELY": (
                "AI-like statistical evidence detected",
                "The frozen AI_LIKELY channel fired. This statistical classification has "
                "precedence over the independent HUMAN_LIKELY channel and is not proof of "
                "provider provenance.",
            ),
            "HUMAN_LIKELY": (
                "Human-like statistical evidence detected",
                "The AI_LIKELY channel did not fire and the independent frozen HUMAN_LIKELY "
                "channel did. This is statistical evidence, not proof of human authorship.",
            ),
            "INCONCLUSIVE": (
                "Authorship remains inconclusive",
                "Neither frozen positive channel produced sufficient evidence. INCONCLUSIVE is "
                "not converted into human or AI attribution.",
            ),
        }
        headline, explanation = explanations[state]
        diagnostics = {
            name: result.get(name)
            for name in (
                "parent_score", "specialist_score", "combined_score", "p_human",
                "human_density_score", "human_score",
            )
        }
        return AuthorshipAssessment(
            state=state,
            headline=headline,
            explanation=explanation,
            eligible=result["eligible"],
            original_tokens=result["original_tokens"],
            ai_likely=result["ai_likely"],
            human_likely=result["human_likely"],
            diagnostics=diagnostics,
            versions=result["versions"],
        )
    except Exception:
        # No internal error strings, model paths, or user text in public output.
        return AuthorshipAssessment(
            state="ERROR",
            headline="Authorship classifier error",
            explanation=(
                "The frozen classifier could not complete this scan. XRay does not convert "
                "runtime failure into AI, human, or negative evidence."
            ),
        )


def _authorship_summary(assessment: AuthorshipAssessment) -> AnalysisFamilySummary:
    if assessment.state == "NOT_TESTABLE":
        state: FamilyState = "NOT_TESTABLE"
    elif assessment.state == "ERROR":
        state = "ERROR"
    elif assessment.eligible is False:
        state = "INSUFFICIENT_DATA"
    else:
        state = "COMPLETE"

    return AnalysisFamilySummary(
        family="ai_authorship",
        title="AI / human statistical classification",
        state=state,
        summary=f"{assessment.headline}. {assessment.disclaimer}",
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
    unavailable_reason: str | None,
) -> AnalysisFamilySummary:
    if comparator is not None:
        return AnalysisFamilySummary(
            family="reference_stylometry",
            title="Reference-corpus comparison",
            state="ERROR",
            summary="Reference corpora loaded but the document could not be compared.",
        )
    if unavailable_reason:
        summary = unavailable_reason
    else:
        suffix = " The configured reference library could not be loaded." if warning_count else ""
        summary = (
            "No versioned reference corpus is configured, so XRay cannot compare this text "
            "with known human or model samples yet." + suffix
        )
    return AnalysisFamilySummary(
        family="reference_stylometry",
        title="Reference-corpus comparison",
        state="NOT_TESTABLE",
        summary=summary,
    )


def _reference_summary(
    report: ReferenceComparisonReport | None,
    comparator: ReferenceComparator | None,
    warning_count: int,
    unavailable_reason: str | None,
) -> AnalysisFamilySummary:
    if report is None:
        return _reference_unavailable_summary(
            comparator,
            warning_count,
            unavailable_reason,
        )

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
