from __future__ import annotations

from xray_text_forensics.core import EvidenceStatus
from xray_text_forensics.detectors.unicode import UnicodeForensicsSuite
from xray_text_forensics.ingest import ForensicIngestor
from xray_text_forensics.runtime import analysis_context_from_ingest
from xray_text_forensics.storage import ContentAddressedStore


def analyze(tmp_path, text: str):
    ingestor = ForensicIngestor(ContentAddressedStore(tmp_path / "store"))
    result = ingestor.ingest_bytes(text.encode("utf-8"), filename="sample.txt")
    return UnicodeForensicsSuite().analyze(analysis_context_from_ingest(result))


def finding(evidence, name: str):
    return next(item for item in evidence if item.finding == name)


def test_zero_width_location_is_exact(tmp_path) -> None:
    evidence = analyze(tmp_path, "ab\u200bcd")
    item = finding(evidence, "ZERO_WIDTH_CHARACTER")

    assert item.status is EvidenceStatus.DETECTED
    assert item.parameters["total_count"] == 1
    assert item.locations[0].start == 2
    assert item.locations[0].end == 3
    assert "U+200B" in (item.locations[0].label or "")


def test_bidi_control_is_detected(tmp_path) -> None:
    item = finding(analyze(tmp_path, "abc\u202edef"), "BIDI_CONTROL")
    assert item.status is EvidenceStatus.DETECTED
    assert item.parameters["total_count"] == 1


def test_unicode_tag_character_is_detected(tmp_path) -> None:
    item = finding(analyze(tmp_path, "hello\U000E0061world"), "UNICODE_TAG_CHARACTER")
    assert item.status is EvidenceStatus.DETECTED


def test_variation_selector_is_detected(tmp_path) -> None:
    item = finding(analyze(tmp_path, "A\ufe0f"), "VARIATION_SELECTOR")
    assert item.status is EvidenceStatus.DETECTED


def test_space_variant_is_detected(tmp_path) -> None:
    item = finding(analyze(tmp_path, "hello\u00a0world"), "SPACE_VARIANT")
    assert item.status is EvidenceStatus.DETECTED


def test_normal_text_has_no_hidden_character_findings(tmp_path) -> None:
    evidence = analyze(tmp_path, "Simple normal text. Línea normal.")
    assert finding(evidence, "ZERO_WIDTH_CHARACTER").status is EvidenceStatus.NOT_DETECTED
    assert finding(evidence, "BIDI_CONTROL").status is EvidenceStatus.NOT_DETECTED
    assert finding(evidence, "UNICODE_TAG_CHARACTER").status is EvidenceStatus.NOT_DETECTED
    assert finding(evidence, "MIXED_SCRIPT_TOKEN").status is EvidenceStatus.NOT_DETECTED


def test_nfkc_difference_is_descriptive_evidence(tmp_path) -> None:
    item = finding(analyze(tmp_path, "office: ﬁle"), "NORMALIZATION_DIFFERENCE")
    assert item.status is EvidenceStatus.DETECTED
    forms = item.parameters["forms"]
    assert forms["NFKC"]["changed"] is True


def test_mixed_latin_cyrillic_token_is_flagged(tmp_path) -> None:
    # The second character is CYRILLIC SMALL LETTER A.
    item = finding(analyze(tmp_path, "pаypal"), "MIXED_SCRIPT_TOKEN")
    assert item.status is EvidenceStatus.DETECTED
    assert item.parameters["total_count"] == 1
    assert "CYRILLIC" in (item.locations[0].label or "")
    assert "LATIN" in (item.locations[0].label or "")


def test_single_decomposed_accent_is_not_suspicious_combining_run(tmp_path) -> None:
    item = finding(analyze(tmp_path, "cafe\u0301"), "SUSPICIOUS_COMBINING_SEQUENCE")
    assert item.status is EvidenceStatus.NOT_DETECTED


def test_long_combining_run_is_flagged(tmp_path) -> None:
    item = finding(
        analyze(tmp_path, "a\u0301\u0302\u0303\u0304"),
        "SUSPICIOUS_COMBINING_SEQUENCE",
    )
    assert item.status is EvidenceStatus.DETECTED
    assert item.parameters["total_sequences"] == 1
