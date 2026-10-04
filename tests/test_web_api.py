from __future__ import annotations

from fastapi.testclient import TestClient

from xray_text_forensics.web import WebSettings, create_app


def client(tmp_path, *, max_upload_bytes: int = 1024 * 1024) -> TestClient:
    app = create_app(
        WebSettings(
            data_root=tmp_path / "web-data",
            max_upload_bytes=max_upload_bytes,
        )
    )
    return TestClient(app)


def test_health(tmp_path) -> None:
    response = client(tmp_path).get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_ingest_redacts_internal_storage_paths(tmp_path) -> None:
    response = client(tmp_path).post(
        "/api/v1/ingest",
        files={"file": ("evidence.txt", b"hello forensic web", "text/plain")},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    serialized = response.text
    assert payload["artifact"]["sha256"]
    assert payload["artifact"]["original_filename"] == "evidence.txt"
    assert "storage_uri" not in serialized
    assert "source_declared" not in serialized
    assert "file://" not in serialized


def test_unicode_analysis_detects_zero_width(tmp_path) -> None:
    response = client(tmp_path).post(
        "/api/v1/analyze/unicode",
        files={
            "file": (
                "unicode.txt",
                "ab\u200bcd".encode(),
                "text/plain",
            )
        },
    )
    assert response.status_code == 200, response.text
    evidence = {
        item["finding"]: item
        for item in response.json()["evidence"]
    }
    assert evidence["ZERO_WIDTH_CHARACTER"]["status"] == "DETECTED"
    assert evidence["ZERO_WIDTH_CHARACTER"]["locations"][0]["start"] == 2


def test_upload_limit_returns_413(tmp_path) -> None:
    response = client(tmp_path, max_upload_bytes=1024).post(
        "/api/v1/ingest",
        files={"file": ("large.txt", b"x" * 1025, "text/plain")},
    )
    assert response.status_code == 413


def test_compare_transform_identity(tmp_path) -> None:
    data = b"alpha beta gamma delta epsilon"
    response = client(tmp_path).post(
        "/api/v1/compare-transform",
        files={
            "original": ("original.txt", data, "text/plain"),
            "transformed": ("transformed.txt", data, "text/plain"),
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["fivegram_survival"] == 1.0
    assert payload["lexical_tfidf_cosine"] == 1.0


def test_case_workflow_and_safe_reports(tmp_path) -> None:
    web = client(tmp_path)
    created = web.post("/api/v1/cases", json={"title": "Web Case"})
    assert created.status_code == 200
    case_id = created.json()["case_id"]

    analyzed = web.post(
        f"/api/v1/cases/{case_id}/analyze/unicode",
        files={"file": ("case.txt", "ab\u200bcd".encode(), "text/plain")},
    )
    assert analyzed.status_code == 200, analyzed.text
    assert analyzed.json()["audit_verified"] is True
    assert analyzed.json()["evidence"]

    fetched = web.get(f"/api/v1/cases/{case_id}")
    assert fetched.status_code == 200
    assert "storage_uri" not in fetched.text
    assert "file://" not in fetched.text

    json_report = web.get(f"/api/v1/cases/{case_id}/report?format=json")
    assert json_report.status_code == 200
    assert "storage_uri" not in json_report.text
    assert "file://" not in json_report.text

    html_report = web.get(f"/api/v1/cases/{case_id}/report?format=html")
    assert html_report.status_code == 200
    assert "XRay Forensic Report" in html_report.text

    pdf_report = web.get(f"/api/v1/cases/{case_id}/report?format=pdf")
    assert pdf_report.status_code == 200
    assert pdf_report.headers["content-type"].startswith("application/pdf")
    assert pdf_report.content.startswith(b"%PDF")


def test_missing_case_returns_404(tmp_path) -> None:
    response = client(tmp_path).get("/api/v1/cases/case_does_not_exist")
    assert response.status_code == 404
