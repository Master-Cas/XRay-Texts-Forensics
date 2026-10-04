from __future__ import annotations

from xray_text_forensics.detectors.watermark import generate_reference_watermarked_text
from xray_text_forensics.robustness import compare_texts, run_reference_watermark_stress


def test_identical_text_has_full_preservation() -> None:
    metrics = compare_texts("alpha beta gamma delta epsilon", "alpha beta gamma delta epsilon")
    assert metrics.token_jaccard == 1.0
    assert metrics.token_sequence_ratio == 1.0
    assert metrics.fivegram_survival == 1.0
    assert metrics.lexical_tfidf_cosine == 1.0
    assert metrics.char_length_ratio == 1.0


def test_replacement_reduces_ngram_survival() -> None:
    original = "one two three four five six seven eight nine ten eleven twelve"
    transformed = "one two X four five X seven eight X ten eleven X"
    metrics = compare_texts(original, transformed)
    assert metrics.fivegram_survival < 0.5
    assert metrics.token_sequence_ratio < 1.0


def test_reference_watermark_stress_records_fragility() -> None:
    secret = b"robustness-test-key"
    text = generate_reference_watermarked_text(secret=secret, token_count=260)
    report = run_reference_watermark_stress(text, secret=secret)

    assert report.baseline.status == "DETECTED"
    rows = {row.transform_id: row for row in report.results}
    assert rows["casefold"].measurement.status == "DETECTED"
    assert rows["whitespace_canonical"].measurement.status == "DETECTED"
    assert rows["replace_every_3rd_token"].preservation.fivegram_survival < 0.2
    assert rows["replace_every_3rd_token"].measurement.z_score < report.baseline.z_score
    assert "not semantic-equivalence" in report.scientific_note


def test_report_never_contains_secret() -> None:
    secret = b"DO_NOT_SERIALIZE_ME"
    text = generate_reference_watermarked_text(secret=secret, token_count=180)
    report = run_reference_watermark_stress(text, secret=secret)
    assert secret.decode() not in report.model_dump_json()
