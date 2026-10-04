from __future__ import annotations

from xray_text_forensics.corpus import CorpusDocument
from xray_text_forensics.stylometry import (
    ReferenceComparator,
    ReferenceMetadata,
    ReferenceSet,
    extract_style_fingerprint,
    reference_manifest,
)


def ref(label: str, *texts: str) -> ReferenceSet:
    return ReferenceSet(
        metadata=ReferenceMetadata(label=label, source=f"synthetic:{label}"),
        documents=[
            CorpusDocument(document_id=f"{label}-{index}", text=text)
            for index, text in enumerate(texts)
        ],
    )


def test_style_fingerprint_is_deterministic() -> None:
    text = "One short sentence. Another one!\n\nNew paragraph."
    assert extract_style_fingerprint(text) == extract_style_fingerprint(text)


def test_reference_manifest_is_document_order_independent() -> None:
    first = ref("a", "one text", "second text")
    second = ReferenceSet(
        metadata=first.metadata,
        documents=list(reversed(first.documents)),
    )
    assert reference_manifest(first).manifest_sha256 == reference_manifest(second).manifest_sha256


def test_style_and_content_signals_can_disagree() -> None:
    short_style = ref(
        "short-style",
        "Alpha. Beta. Gamma. Delta.",
        "Red. Blue. Green. Yellow.",
        "North. South. East. West.",
    )
    content_match = ref(
        "content-match",
        "The sun and moon appear together across a broad and slowly changing night sky.",
        "A star and moon can remain visible while the sun changes the color of the sky.",
        "The moon, star, and sun are discussed in this deliberately long sentence about sky.",
    )
    comparator = ReferenceComparator([short_style, content_match])
    report = comparator.compare("Sun. Moon. Star. Sky.")
    rows = {item.label: item for item in report.comparisons}

    assert rows["short-style"].style_similarity > rows["content-match"].style_similarity
    assert rows["content-match"].content_similarity > rows["short-style"].content_similarity


def test_report_does_not_claim_authorship_probability() -> None:
    comparator = ReferenceComparator(
        [
            ref("a", "One. Two. Three.", "Four. Five. Six."),
            ref("b", "This is a much longer sentence about an unrelated system and process."),
        ]
    )
    payload = comparator.compare("Short. Text. Here.").model_dump()
    assert "authorship_probability" not in str(payload)
    assert "not authorship probabilities" in payload["scientific_note"]
