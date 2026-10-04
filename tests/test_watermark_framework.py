from __future__ import annotations

from xray_text_forensics.core import EvidenceStatus
from xray_text_forensics.detectors.watermark import (
    InMemorySecretProvider,
    RedGreenConfig,
    ReferenceRedGreenDetector,
    StableWordTokenizer,
    generate_reference_watermarked_text,
)
from xray_text_forensics.ingest import ForensicIngestor
from xray_text_forensics.runtime import analysis_context_from_ingest
from xray_text_forensics.storage import ContentAddressedStore


def context_for(tmp_path, text: str):
    result = ForensicIngestor(ContentAddressedStore(tmp_path / "store")).ingest_bytes(
        text.encode("utf-8"),
        filename="sample.txt",
    )
    return analysis_context_from_ingest(result)


def configured_context(tmp_path, text: str, key: bytes):
    context = context_for(tmp_path, text)
    context.resources.update(
        {
            "secret_provider": InMemorySecretProvider({"test-key": key}),
            "secret_ref": "test-key",
            "watermark_tokenizer": StableWordTokenizer(),
        }
    )
    return context


def test_missing_key_is_not_testable(tmp_path) -> None:
    context = context_for(tmp_path, "ordinary text " * 80)
    item = ReferenceRedGreenDetector().analyze(context)[0]
    assert item.status is EvidenceStatus.NOT_TESTABLE


def test_short_text_is_insufficient_data(tmp_path) -> None:
    context = configured_context(tmp_path, "one two three four five six", b"secret")
    item = ReferenceRedGreenDetector().analyze(context)[0]
    assert item.status is EvidenceStatus.INSUFFICIENT_DATA


def test_reference_watermarked_text_detects_with_known_key(tmp_path) -> None:
    key = b"correct secret material"
    text = generate_reference_watermarked_text(secret=key, token_count=220)
    context = configured_context(tmp_path, text, key)
    item = ReferenceRedGreenDetector().analyze(context)[0]

    assert item.status is EvidenceStatus.DETECTED
    assert item.parameters["z_score"] >= 4.0
    assert item.parameters["green_fraction"] > 0.5


def test_reference_watermark_does_not_validate_with_wrong_key(tmp_path) -> None:
    text = generate_reference_watermarked_text(secret=b"correct", token_count=240)
    context = configured_context(tmp_path, text, b"wrong")
    item = ReferenceRedGreenDetector().analyze(context)[0]

    assert item.status is EvidenceStatus.NOT_DETECTED
    assert item.parameters["secret_ref"] == "test-key"
    assert "correct" not in str(item.parameters)
    assert "wrong" not in str(item.parameters)


def test_repeated_contexts_are_masked(tmp_path) -> None:
    config = RedGreenConfig(min_scored_tokens=1, context_width=2)
    context = configured_context(tmp_path, "a b c a b c a b c a b c", b"secret")
    item = ReferenceRedGreenDetector(config).analyze(context)[0]
    assert item.parameters["repeated_contexts_skipped"] > 0
