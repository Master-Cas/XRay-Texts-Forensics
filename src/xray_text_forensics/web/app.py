"""FastAPI application that exposes the XRay core without duplicating it."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response

from xray_text_forensics.cases import CaseBundle, CaseStore
from xray_text_forensics.core import Case, DetectorRun
from xray_text_forensics.detectors.unicode import UnicodeForensicsSuite
from xray_text_forensics.graph import build_evidence_graph
from xray_text_forensics.ingest import ForensicIngestor, IngestPolicy, IngestResult
from xray_text_forensics.reports import render_html_report, render_pdf_report
from xray_text_forensics.robustness import PreservationMetrics, compare_texts
from xray_text_forensics.runtime import analysis_context_from_ingest
from xray_text_forensics.storage import ContentAddressedStore

from .models import (
    CaseBundleResponse,
    CaseCreateRequest,
    HealthResponse,
    IngestResponse,
    UnicodeAnalysisResponse,
)
from .settings import WebSettings


def create_app(settings: WebSettings | None = None) -> FastAPI:
    settings = settings or WebSettings()
    settings.data_root.mkdir(parents=True, exist_ok=True)
    settings.object_store_root.mkdir(parents=True, exist_ok=True)

    app = FastAPI(
        title="XRay Texts Forensics API",
        version="0.9.0",
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url=None,
    )
    app.state.xray_settings = settings

    @app.get("/api/v1/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse()

    @app.post("/api/v1/ingest", response_model=IngestResponse)
    async def ingest(file: Annotated[UploadFile, File()]) -> IngestResponse:
        data, filename = await _read_upload(file, settings.max_upload_bytes)
        result = _ingestor(settings).ingest_bytes(
            data,
            filename=filename,
            acquisition_method="web-upload",
            source_declared="web-upload",
        )
        return IngestResponse.from_domain(result)

    @app.post("/api/v1/analyze/unicode", response_model=UnicodeAnalysisResponse)
    async def analyze_unicode(
        file: Annotated[UploadFile, File()],
    ) -> UnicodeAnalysisResponse:
        data, filename = await _read_upload(file, settings.max_upload_bytes)
        result = _ingestor(settings).ingest_bytes(
            data,
            filename=filename,
            acquisition_method="web-upload",
            source_declared="web-upload",
        )
        evidence = UnicodeForensicsSuite().analyze(analysis_context_from_ingest(result))
        base = IngestResponse.from_domain(result)
        return UnicodeAnalysisResponse(
            **base.model_dump(),
            evidence=evidence,
        )

    @app.post("/api/v1/compare-transform", response_model=PreservationMetrics)
    async def compare_transform(
        original: Annotated[UploadFile, File()],
        transformed: Annotated[UploadFile, File()],
    ) -> PreservationMetrics:
        original_data, original_name = await _read_upload(
            original,
            settings.max_upload_bytes,
        )
        transformed_data, transformed_name = await _read_upload(
            transformed,
            settings.max_upload_bytes,
        )
        original_text = _best_text(
            _ingestor(settings).ingest_bytes(
                original_data,
                filename=original_name,
                acquisition_method="web-upload",
                source_declared="web-upload",
            )
        )
        transformed_text = _best_text(
            _ingestor(settings).ingest_bytes(
                transformed_data,
                filename=transformed_name,
                acquisition_method="web-upload",
                source_declared="web-upload",
            )
        )
        return compare_texts(original_text, transformed_text)

    @app.post("/api/v1/cases", response_model=Case)
    def create_case(request: CaseCreateRequest) -> Case:
        with CaseStore(settings.case_database) as store:
            return store.create_case(request.title)

    @app.get("/api/v1/cases/{case_id}", response_model=CaseBundleResponse)
    def get_case(case_id: str) -> CaseBundleResponse:
        return CaseBundleResponse.from_domain(_bundle_or_404(settings, case_id))

    @app.post(
        "/api/v1/cases/{case_id}/analyze/unicode",
        response_model=CaseBundleResponse,
    )
    async def case_analyze_unicode(
        case_id: str,
        file: Annotated[UploadFile, File()],
    ) -> CaseBundleResponse:
        _bundle_or_404(settings, case_id)
        data, filename = await _read_upload(file, settings.max_upload_bytes)
        result = _ingestor(settings).ingest_bytes(
            data,
            filename=filename,
            acquisition_method="web-upload",
            source_declared="web-upload",
        )
        context = analysis_context_from_ingest(result)
        started_at = datetime.now(UTC)
        evidence = UnicodeForensicsSuite().analyze(context)
        run = DetectorRun(
            detector_id="unicode.forensics.suite",
            detector_version="1.0.0",
            artifact_id=result.artifact.artifact_id,
            view_ids=[view.view_id for view in result.views],
            started_at=started_at,
            finished_at=datetime.now(UTC),
            evidence_ids=[item.evidence_id for item in evidence],
        )
        with CaseStore(settings.case_database) as store:
            store.record_analysis(
                case_id,
                artifact=result.artifact,
                views=result.views,
                run=run,
                evidence=evidence,
            )
            bundle = store.fetch_bundle(case_id)
        return CaseBundleResponse.from_domain(bundle)

    @app.get("/api/v1/cases/{case_id}/report")
    def case_report(
        case_id: str,
        format_name: Annotated[
            Literal["json", "html", "pdf"],
            Query(alias="format"),
        ] = "json",
    ) -> Response:
        bundle = _bundle_or_404(settings, case_id)
        graph = build_evidence_graph(bundle)

        if format_name == "html":
            return HTMLResponse(render_html_report(bundle, graph))
        if format_name == "pdf":
            return Response(
                content=render_pdf_report(bundle, graph),
                media_type="application/pdf",
                headers={
                    "Content-Disposition": (
                        f'inline; filename="xray-{_safe_identifier(case_id)}.pdf"'
                    )
                },
            )

        safe_bundle = CaseBundleResponse.from_domain(bundle)
        payload = {
            "case": safe_bundle.model_dump(mode="json"),
            "evidence_graph": graph.model_dump(mode="json"),
            "scientific_note": (
                "Evidence families remain separate. No universal AI score is calculated."
            ),
        }
        return JSONResponse(payload)

    return app


async def _read_upload(upload: UploadFile, max_bytes: int) -> tuple[bytes, str]:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"Upload exceeds {max_bytes} byte limit",
            )
        chunks.append(chunk)
    filename = Path(upload.filename or "upload.bin").name or "upload.bin"
    return b"".join(chunks), filename


def _ingestor(settings: WebSettings) -> ForensicIngestor:
    return ForensicIngestor(
        ContentAddressedStore(settings.object_store_root),
        IngestPolicy(max_input_bytes=settings.max_upload_bytes),
    )


def _best_text(result: IngestResult) -> str:
    context = analysis_context_from_ingest(result)
    selected = context.preferred_text_view()
    if selected is None:
        raise HTTPException(status_code=422, detail="Uploaded artifact has no usable text view")
    return selected[1]


def _bundle_or_404(settings: WebSettings, case_id: str) -> CaseBundle:
    try:
        with CaseStore(settings.case_database) as store:
            return store.fetch_bundle(case_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Case not found") from exc


def _safe_identifier(value: str) -> str:
    return "".join(character for character in value if character.isalnum() or character in "-_")
