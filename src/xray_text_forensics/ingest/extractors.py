"""Text extractors for supported M1 document formats."""

from __future__ import annotations

import io
import zipfile
from html.parser import HTMLParser
from xml.etree import ElementTree

from pypdf import PdfReader

from .models import IngestPolicy

DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class ExtractionError(RuntimeError):
    pass


class ExtractionLimitError(ExtractionError):
    pass


def extract_text(
    media_type: str,
    data: bytes,
    decoded_text: str | None,
    policy: IngestPolicy,
) -> tuple[str | None, str | None]:
    """Return extracted text and a stable transformation identifier."""

    if media_type in {"text/plain", "text/markdown", "application/json", "text/csv"}:
        if decoded_text is None:
            raise ExtractionError("Decoded text is required for textual media")
        return _limit_text(decoded_text, policy), "identity-text"

    if media_type == "text/html":
        if decoded_text is None:
            raise ExtractionError("Decoded text is required for HTML")
        parser = _VisibleHTMLTextParser()
        parser.feed(decoded_text)
        parser.close()
        return _limit_text(parser.text(), policy), "extract-html-visible-text"

    if media_type == DOCX_MEDIA_TYPE:
        return _extract_docx(data, policy), "extract-docx-text"

    if media_type == "application/pdf":
        return _extract_pdf(data, policy), "extract-pdf-text"

    return None, None


def _limit_text(text: str, policy: IngestPolicy) -> str:
    if len(text) > policy.max_extracted_text_chars:
        raise ExtractionLimitError(
            f"Extracted text exceeds {policy.max_extracted_text_chars} characters"
        )
    return text


class _VisibleHTMLTextParser(HTMLParser):
    _SKIPPED = {"script", "style", "template", "noscript"}
    _BLOCK = {
        "address",
        "article",
        "aside",
        "blockquote",
        "br",
        "div",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "li",
        "main",
        "nav",
        "p",
        "section",
        "table",
        "td",
        "th",
        "tr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        lowered = tag.lower()
        if lowered in self._SKIPPED:
            self._skip_depth += 1
        elif self._skip_depth == 0 and lowered in self._BLOCK:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in self._SKIPPED and self._skip_depth:
            self._skip_depth -= 1
        elif self._skip_depth == 0 and lowered in self._BLOCK:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._parts.append(data)

    def text(self) -> str:
        lines = (" ".join(part.split()) for part in "".join(self._parts).splitlines())
        return "\n".join(line for line in lines if line)


def _extract_docx(data: bytes, policy: IngestPolicy) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
            if len(infos) > policy.max_archive_entries:
                raise ExtractionLimitError(
                    f"DOCX has more than {policy.max_archive_entries} archive entries"
                )

            total_uncompressed = sum(info.file_size for info in infos)
            if total_uncompressed > policy.max_archive_uncompressed_bytes:
                raise ExtractionLimitError(
                    "DOCX uncompressed archive size exceeds configured limit"
                )

            try:
                document_xml = archive.read("word/document.xml")
            except KeyError as exc:
                raise ExtractionError("DOCX is missing word/document.xml") from exc
    except zipfile.BadZipFile as exc:
        raise ExtractionError("Invalid DOCX/ZIP container") from exc

    try:
        root = ElementTree.fromstring(document_xml)
    except ElementTree.ParseError as exc:
        raise ExtractionError("Invalid DOCX document XML") from exc

    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    paragraphs: list[str] = []
    for paragraph in root.iter(f"{namespace}p"):
        parts: list[str] = []
        for node in paragraph.iter():
            if node.tag == f"{namespace}t" and node.text:
                parts.append(node.text)
            elif node.tag == f"{namespace}tab":
                parts.append("\t")
            elif node.tag in {f"{namespace}br", f"{namespace}cr"}:
                parts.append("\n")
        paragraphs.append("".join(parts))

    return _limit_text("\n".join(paragraphs), policy)


def _extract_pdf(data: bytes, policy: IngestPolicy) -> str:
    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
        page_count = len(reader.pages)
        if page_count > policy.max_pdf_pages:
            raise ExtractionLimitError(
                f"PDF has {page_count} pages; limit is {policy.max_pdf_pages}"
            )

        parts: list[str] = []
        current_chars = 0
        for page in reader.pages:
            page_text = page.extract_text() or ""
            current_chars += len(page_text)
            if current_chars > policy.max_extracted_text_chars:
                raise ExtractionLimitError(
                    f"Extracted PDF text exceeds {policy.max_extracted_text_chars} characters"
                )
            parts.append(page_text)
        return "\n".join(parts)
    except ExtractionError:
        raise
    except Exception as exc:
        raise ExtractionError(f"PDF text extraction failed: {type(exc).__name__}") from exc
