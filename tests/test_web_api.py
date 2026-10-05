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


def test_full_scan_exposes_multiple_evidence_families(tmp_path) -> None:
    response = client(tmp_path).post(
        "/api/v1/analyze/full",
        files={
            "file": (
                "story.txt",
                (
                    b"The small star crossed the quiet sky. "
                    b"It stopped above the forest and listened to the river. "
                    b"Then it returned home with a different light."
                ),
                "text/plain",
            )
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["unicode_evidence"]
    assert payload["linguistic_snapshot"]["token_count"] > 0
    assert payload["style_fingerprint"]["sentence_count"] == 3

    families = {item["family"]: item for item in payload["family_summaries"]}
    assert families["unicode"]["state"] == "COMPLETE"
    assert families["linguistic_profile"]["state"] in {"COMPLETE", "INSUFFICIENT_DATA"}
    assert families["reference_stylometry"]["state"] == "NOT_TESTABLE"
    assert families["watermark"]["state"] == "NOT_TESTABLE"
    assert payload["origin_assessment"]["state"] == "NOT_TESTABLE"
    assert payload["reference_comparison"] is None


def test_full_scan_uses_configured_reference_corpora(tmp_path) -> None:
    references = tmp_path / "references"
    human = references / "human-reference"
    model = references / "model-reference"
    human.mkdir(parents=True)
    model.mkdir(parents=True)

    (human / ".xray-reference.json").write_text(
        '{"label":"human-reference","source":"synthetic-test","language":"en"}',
        encoding="utf-8",
    )
    (model / ".xray-reference.json").write_text(
        '{"label":"model-reference","source":"synthetic-test","language":"en"}',
        encoding="utf-8",
    )

    human_samples = [
        "I walked home. Rain fell. The bus was late. I made tea.",
        "We met outside. She laughed. I forgot my keys. We waited.",
        "My dog barked. I opened the door. The street was quiet.",
    ]
    model_samples = [
        (
            "Across the quiet valley, the lantern remained visible while the traveler "
            "considered the meaning of the long and carefully described journey."
        ),
        (
            "Beneath the evening sky, the river reflected a gentle light while the "
            "traveler continued through the forest with deliberate patience."
        ),
        (
            "Within the silent garden, every path seemed to invite another thoughtful "
            "step toward a distant and softly illuminated horizon."
        ),
    ]
    for index, sample in enumerate(human_samples):
        (human / f"{index}.txt").write_text(sample, encoding="utf-8")
    for index, sample in enumerate(model_samples):
        (model / f"{index}.txt").write_text(sample, encoding="utf-8")

    app = create_app(
        WebSettings(
            data_root=tmp_path / "web-data",
            reference_root=references,
        )
    )
    web = TestClient(app)
    response = web.post(
        "/api/v1/analyze/full",
        files={
            "file": (
                "suspect.txt",
                model_samples[0].encode(),
                "text/plain",
            )
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["origin_assessment"]["state"] == "REFERENCE_COMPARISON"
    assert payload["reference_comparison"] is not None
    labels = {
        row["label"]
        for row in payload["reference_comparison"]["comparisons"]
    }
    assert labels == {"human-reference", "model-reference"}

    family = {
        item["family"]: item
        for item in payload["family_summaries"]
    }["reference_stylometry"]
    assert family["state"] == "COMPLETE"
    assert "not provider probabilities" in family["summary"].casefold()


def test_reference_library_drives_full_scan_comparison(tmp_path) -> None:
    web = client(tmp_path)

    human = web.post(
        "/api/v1/references",
        json={
            "label": "Human stories",
            "provider": "human",
            "language": "en",
            "source": "controlled-test",
        },
    )
    model = web.post(
        "/api/v1/references",
        json={
            "label": "Model stories",
            "provider": "synthetic-model",
            "language": "en",
            "source": "controlled-test",
        },
    )
    assert human.status_code == 200, human.text
    assert model.status_code == 200, model.text

    human_slug = human.json()["slug"]
    model_slug = model.json()["slug"]
    human_samples = [
        b"I got home late. The kettle was cold. I fed the cat and went to bed.",
        b"We missed the bus. Sam laughed. I called my sister and walked home.",
        b"My coat was wet. The shop was closed. I waited under the old awning.",
    ]
    model_samples = [
        (
            b"Across the quiet valley, a lantern glowed while the traveler "
            b"considered the long journey ahead."
        ),
        (
            b"Beneath the evening sky, the river reflected a gentle light "
            b"as the traveler crossed the forest."
        ),
        (
            b"Within the silent garden, every path invited another careful "
            b"step toward the distant horizon."
        ),
    ]

    for index, sample in enumerate(human_samples):
        response = web.post(
            f"/api/v1/references/{human_slug}/documents",
            files={"file": (f"human-{index}.txt", sample, "text/plain")},
        )
        assert response.status_code == 200, response.text

    for index, sample in enumerate(model_samples):
        response = web.post(
            f"/api/v1/references/{model_slug}/documents",
            files={"file": (f"model-{index}.txt", sample, "text/plain")},
        )
        assert response.status_code == 200, response.text

    listed = web.get("/api/v1/references")
    assert listed.status_code == 200
    by_label = {item["label"]: item for item in listed.json()}
    assert by_label["Human stories"]["document_count"] == 3
    assert by_label["Model stories"]["document_count"] == 3

    scan = web.post(
        "/api/v1/analyze/full",
        files={
            "file": (
                "suspect.txt",
                (
                    b"Beneath the quiet sky, the traveler followed the river "
                    b"toward a softly illuminated horizon."
                ),
                "text/plain",
            )
        },
    )
    assert scan.status_code == 200, scan.text
    payload = scan.json()
    assert payload["origin_assessment"]["state"] == "REFERENCE_COMPARISON"
    assert payload["reference_comparison"] is not None
    assert {
        row["label"]
        for row in payload["reference_comparison"]["comparisons"]
    } == {"Human stories", "Model stories"}


def test_reference_document_upload_is_content_deduplicated(tmp_path) -> None:
    web = client(tmp_path)
    created = web.post(
        "/api/v1/references",
        json={"label": "Claude", "source": "controlled-test"},
    )
    assert created.status_code == 200
    slug = created.json()["slug"]
    payload = b"Known-origin sample text."

    first = web.post(
        f"/api/v1/references/{slug}/documents",
        files={"file": ("first.txt", payload, "text/plain")},
    )
    second = web.post(
        f"/api/v1/references/{slug}/documents",
        files={"file": ("second.txt", payload, "text/plain")},
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["added"] is True
    assert second.json()["added"] is False

    listed = web.get("/api/v1/references").json()
    assert listed[0]["document_count"] == 1
