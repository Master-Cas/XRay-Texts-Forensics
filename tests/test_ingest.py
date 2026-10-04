from __future__ import annotations

import io
import zipfile

import pytest
from pypdf import PdfWriter

from xray_text_forensics.core import ViewKind
from xray_text_forensics.ingest import ForensicIngestor, IngestPolicy
from xray_text_forensics.ingest.service import IngestLimitError
from xray_text_forensics.storage import ContentAddressedStore


def make_ingestor(tmp_path, **policy_overrides: int) -> ForensicIngestor:
    return ForensicIngestor(
        ContentAddressedStore(tmp_path / "store"),
        IngestPolicy(**policy_overrides),
    )


def read_view(view) -> bytes:
    assert view.storage_uri is not None
    from pathlib import Path
    from urllib.parse import unquote, urlparse

    parsed = urlparse(view.storage_uri)
    return Path(unquote(parsed.path)).read_bytes()


def test_plain_text_preserves_exact_original_and_creates_views(tmp_path) -> None:
    original = "línea uno\nline two\n".encode()
    result = make_ingestor(tmp_path).ingest_bytes(original, filename="evidence.txt")

    assert result.artifact.sha256
    assert result.artifact.byte_length == len(original)
    assert result.artifact.media_type == "text/plain"
    assert result.artifact.detected_encoding == "utf-8"
    assert {view.kind for view in result.views} == {
        ViewKind.RAW_UNICODE,
        ViewKind.EXTRACTED_TEXT,
    }

    artifact_path = result.artifact.storage_uri
    assert artifact_path is not None
    from pathlib import Path
    from urllib.parse import unquote, urlparse

    stored = Path(unquote(urlparse(artifact_path).path)).read_bytes()
    assert stored == original


def test_utf8_bom_remains_observable_in_raw_unicode(tmp_path) -> None:
    result = make_ingestor(tmp_path).ingest_bytes(
        b"\xef\xbb\xbfhello",
        filename="bom.txt",
    )
    raw = next(view for view in result.views if view.kind is ViewKind.RAW_UNICODE)
    assert read_view(raw).decode("utf-8").startswith("\ufeff")
    assert raw.parameters["bom"] == "UTF-8"


def test_html_keeps_raw_view_but_visible_extraction_omits_script(tmp_path) -> None:
    html = b"<html><body><p>Hello <b>world</b></p><script>secret()</script></body></html>"
    result = make_ingestor(tmp_path).ingest_bytes(html, filename="page.html")

    raw = next(view for view in result.views if view.kind is ViewKind.RAW_UNICODE)
    extracted = next(view for view in result.views if view.kind is ViewKind.EXTRACTED_TEXT)

    assert b"<script>" in read_view(raw)
    text = read_view(extracted).decode()
    assert "Hello world" in text
    assert "secret()" not in text


def test_minimal_docx_text_extraction(tmp_path) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "word/document.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
            <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
              <w:body>
                <w:p><w:r><w:t>Hello DOCX</w:t></w:r></w:p>
                <w:p><w:r><w:t>Second paragraph</w:t></w:r></w:p>
              </w:body>
            </w:document>""",
        )

    result = make_ingestor(tmp_path).ingest_bytes(buffer.getvalue(), filename="sample.docx")
    extracted = next(view for view in result.views if view.kind is ViewKind.EXTRACTED_TEXT)
    assert read_view(extracted).decode() == "Hello DOCX\nSecond paragraph"


def test_valid_pdf_is_preserved_and_text_view_created(tmp_path) -> None:
    buffer = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.write(buffer)

    result = make_ingestor(tmp_path).ingest_bytes(buffer.getvalue(), filename="sample.pdf")

    assert result.artifact.media_type == "application/pdf"
    assert any(view.kind is ViewKind.EXTRACTED_TEXT for view in result.views)
    assert not result.warnings


def test_malformed_pdf_is_still_preserved(tmp_path) -> None:
    data = b"%PDF-1.7\nthis is intentionally malformed"
    result = make_ingestor(tmp_path).ingest_bytes(data, filename="broken.pdf")

    assert result.artifact.media_type == "application/pdf"
    assert result.artifact.byte_length == len(data)
    assert result.artifact.storage_uri is not None
    assert any(warning.code == "TEXT_EXTRACTION_FAILED" for warning in result.warnings)


def test_input_limit_rejects_before_persistence(tmp_path) -> None:
    ingestor = make_ingestor(tmp_path, max_input_bytes=4)
    with pytest.raises(IngestLimitError):
        ingestor.ingest_bytes(b"12345", filename="too-large.txt")

    assert not list((tmp_path / "store").rglob("*"))


def test_signature_wins_over_misleading_extension(tmp_path) -> None:
    data = b"%PDF-1.7\ninvalid but enough for signature"
    result = make_ingestor(tmp_path).ingest_bytes(data, filename="not-really.txt")
    assert result.artifact.media_type == "application/pdf"
