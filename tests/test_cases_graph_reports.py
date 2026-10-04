from __future__ import annotations

import json
import sqlite3

from xray_text_forensics.cases import CaseStore
from xray_text_forensics.core import DetectorRun
from xray_text_forensics.detectors.unicode import UnicodeForensicsSuite
from xray_text_forensics.graph import build_evidence_graph
from xray_text_forensics.ingest import ForensicIngestor
from xray_text_forensics.reports import (
    render_html_report,
    render_json_report,
    render_pdf_report,
)
from xray_text_forensics.runtime import analysis_context_from_ingest
from xray_text_forensics.storage import ContentAddressedStore


def build_case(tmp_path):
    db = tmp_path / "case.sqlite"
    evidence_store = ContentAddressedStore(tmp_path / "objects")
    ingest = ForensicIngestor(evidence_store).ingest_bytes(
        b"hello\xe2\x80\x8bworld",
        filename="evidence.txt",
    )
    evidence = UnicodeForensicsSuite().analyze(analysis_context_from_ingest(ingest))
    run = DetectorRun(
        detector_id="unicode.forensics.suite",
        detector_version="1.0.0",
        artifact_id=ingest.artifact.artifact_id,
        view_ids=[view.view_id for view in ingest.views],
        evidence_ids=[item.evidence_id for item in evidence],
    )
    case_store = CaseStore(db)
    case = case_store.create_case("Demo Case")
    case_store.record_analysis(
        case.case_id,
        artifact=ingest.artifact,
        views=ingest.views,
        run=run,
        evidence=evidence,
    )
    return case_store, case.case_id


def test_sqlite_uses_wal_and_roundtrips_bundle(tmp_path) -> None:
    store, case_id = build_case(tmp_path)
    try:
        assert store.journal_mode() == "wal"
        bundle = store.fetch_bundle(case_id)
        assert len(bundle.artifacts) == 1
        assert len(bundle.views) == 2
        assert len(bundle.runs) == 1
        assert bundle.evidence
        assert bundle.audit_verified is True
    finally:
        store.close()


def test_audit_chain_detects_tampering(tmp_path) -> None:
    store, case_id = build_case(tmp_path)
    try:
        assert store.verify_audit(case_id)
        row = store.connection.execute(
            "SELECT seq, payload FROM audit_events WHERE case_id=? ORDER BY seq LIMIT 1",
            (case_id,),
        ).fetchone()
        assert row is not None
        payload = json.loads(row[1])
        payload["action"] = "TAMPERED"
        with store.connection:
            store.connection.execute(
                "UPDATE audit_events SET payload=? WHERE seq=?",
                (json.dumps(payload), row[0]),
            )
        assert store.verify_audit(case_id) is False
    finally:
        store.close()


def test_duplicate_artifact_is_not_silently_overwritten(tmp_path) -> None:
    store, case_id = build_case(tmp_path)
    try:
        bundle = store.fetch_bundle(case_id)
        artifact = bundle.artifacts[0]
        run = bundle.runs[0].model_copy(
            update={"run_id": "other-run", "evidence_ids": []}
        )
        try:
            store.record_analysis(
                case_id,
                artifact=artifact,
                views=[],
                run=run,
                evidence=[],
            )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("duplicate artifact should fail")
    finally:
        store.close()


def test_graph_traces_evidence_to_artifact(tmp_path) -> None:
    store, case_id = build_case(tmp_path)
    try:
        bundle = store.fetch_bundle(case_id)
        graph = build_evidence_graph(bundle)
        evidence_id = bundle.evidence[0].evidence_id
        path = graph.trace_to_artifact(evidence_id)
        assert path[0] == evidence_id
        assert path[-1] == bundle.artifacts[0].artifact_id
    finally:
        store.close()


def test_reports_include_evidence_ids_and_no_universal_score(tmp_path) -> None:
    store, case_id = build_case(tmp_path)
    try:
        bundle = store.fetch_bundle(case_id)
        graph = build_evidence_graph(bundle)
        evidence_id = bundle.evidence[0].evidence_id

        html_report = render_html_report(bundle, graph)
        assert evidence_id in html_report
        assert "No universal AI score" in html_report

        json_report = render_json_report(bundle, graph)
        payload = json.loads(json_report)
        assert payload["case"]["audit_verified"] is True
        assert evidence_id in json_report

        pdf = render_pdf_report(bundle, graph)
        assert pdf.startswith(b"%PDF")
        assert len(pdf) > 1000
    finally:
        store.close()
