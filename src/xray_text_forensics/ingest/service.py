"""Forensic ingestion service: preserve first, derive second."""

from __future__ import annotations

from pathlib import Path

from xray_text_forensics.core import Artifact, DerivedView, ViewKind
from xray_text_forensics.storage import ContentAddressedStore

from .encoding import DecodedText, decode_text
from .extractors import ExtractionError, extract_text
from .media import TEXTUAL_MEDIA_TYPES, detect_media_type
from .models import IngestPolicy, IngestResult, IngestWarning


class IngestLimitError(ValueError):
    pass


class ForensicIngestor:
    """Preserve original bytes before creating any analytical representation."""

    def __init__(
        self,
        store: ContentAddressedStore,
        policy: IngestPolicy | None = None,
    ) -> None:
        self.store = store
        self.policy = policy or IngestPolicy()

    def ingest_path(
        self,
        path: str | Path,
        *,
        source_declared: str | None = None,
    ) -> IngestResult:
        source_path = Path(path)
        stat = source_path.stat()
        if stat.st_size > self.policy.max_input_bytes:
            raise IngestLimitError(
                f"Input is {stat.st_size} bytes; limit is {self.policy.max_input_bytes}"
            )

        data = source_path.read_bytes()
        return self.ingest_bytes(
            data,
            filename=source_path.name,
            acquisition_method="file",
            source_declared=source_declared or str(source_path),
            source_metadata={
                "source_mtime_ns": stat.st_mtime_ns,
                "source_mode": stat.st_mode,
            },
        )

    def ingest_bytes(
        self,
        data: bytes,
        *,
        filename: str | None = None,
        acquisition_method: str = "bytes",
        source_declared: str | None = None,
        source_metadata: dict[str, str | int | float | bool | None] | None = None,
    ) -> IngestResult:
        if len(data) > self.policy.max_input_bytes:
            raise IngestLimitError(
                f"Input is {len(data)} bytes; limit is {self.policy.max_input_bytes}"
            )

        # Preservation always precedes decoding, parsing, normalization, or extraction.
        stored_original = self.store.put_bytes("artifacts", data)
        media_type = detect_media_type(data, filename)

        warnings: list[IngestWarning] = []
        views: list[DerivedView] = []
        decoded: DecodedText | None = None

        if media_type in TEXTUAL_MEDIA_TYPES:
            try:
                decoded = decode_text(data)
            except UnicodeError as exc:
                warnings.append(
                    IngestWarning(
                        code="TEXT_DECODE_FAILED",
                        message=str(exc),
                        details={"media_type": media_type},
                    )
                )
            else:
                raw_view = self._store_text_view(
                    artifact_id=stored_original.sha256,
                    kind=ViewKind.RAW_UNICODE,
                    text=decoded.text,
                    transformation=f"decode:{decoded.encoding}",
                    encoding="utf-8",
                    parameters={
                        "source_encoding": decoded.encoding,
                        "bom": decoded.bom,
                    },
                )
                views.append(raw_view)

        artifact = Artifact(
            sha256=stored_original.sha256,
            byte_length=stored_original.byte_length,
            media_type=media_type,
            original_filename=filename,
            acquisition_method=acquisition_method,
            source_declared=source_declared,
            storage_uri=stored_original.uri,
            detected_encoding=decoded.encoding if decoded else None,
            metadata={
                "forensic_ingest_version": "1",
                **(source_metadata or {}),
            },
        )

        try:
            extracted, transformation = extract_text(
                media_type,
                data,
                decoded.text if decoded else None,
                self.policy,
            )
        except ExtractionError as exc:
            warnings.append(
                IngestWarning(
                    code="TEXT_EXTRACTION_FAILED",
                    message=str(exc),
                    details={"media_type": media_type},
                )
            )
        else:
            if extracted is not None and transformation is not None:
                views.append(
                    self._store_text_view(
                        artifact_id=artifact.artifact_id,
                        kind=ViewKind.EXTRACTED_TEXT,
                        text=extracted,
                        transformation=transformation,
                        encoding="utf-8",
                        parameters={"source_media_type": media_type},
                    )
                )
            elif media_type == "application/octet-stream":
                warnings.append(
                    IngestWarning(
                        code="UNSUPPORTED_MEDIA_TYPE",
                        message="Original bytes were preserved but no text extractor is available.",
                        details={"media_type": media_type},
                    )
                )

        # Correct the RAW_UNICODE view's foreign key now that the Artifact ID exists.
        for index, view in enumerate(views):
            if view.artifact_id == stored_original.sha256:
                views[index] = view.model_copy(update={"artifact_id": artifact.artifact_id})

        return IngestResult(artifact=artifact, views=views, warnings=warnings)

    def _store_text_view(
        self,
        *,
        artifact_id: str,
        kind: ViewKind,
        text: str,
        transformation: str,
        encoding: str,
        parameters: dict[str, str | int | float | bool | None],
    ) -> DerivedView:
        encoded = text.encode(encoding)
        stored = self.store.put_bytes("views", encoded)
        return DerivedView(
            artifact_id=artifact_id,
            kind=kind,
            content_sha256=stored.sha256,
            byte_length=stored.byte_length,
            media_type="text/plain",
            transformation=transformation,
            transformation_version="1",
            encoding=encoding,
            storage_uri=stored.uri,
            parameters=parameters,
        )
