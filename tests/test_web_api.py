from __future__ import annotations

import io
import json
import zipfile

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
        b"I lost my ticket. The driver waited. I found it inside my coat.",
        b"We ate outside. The coffee was hot. Then the rain started again.",
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
        (
            b"Beyond the sleeping village, the traveler watched the pale moon "
            b"rise over a landscape filled with quiet possibility."
        ),
        (
            b"Along the ancient road, a soft wind carried distant sounds while "
            b"the traveler continued toward the glowing edge of morning."
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
    assert by_label["Human stories"]["document_count"] == 5
    assert by_label["Model stories"]["document_count"] == 5

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




def test_reference_comparison_waits_for_minimum_corpus(tmp_path) -> None:
    web = client(tmp_path)
    slugs = []
    for label in ("Human", "Claude"):
        created = web.post(
            "/api/v1/references",
            json={"label": label, "source": "controlled-test"},
        )
        assert created.status_code == 200
        slugs.append(created.json()["slug"])

    for slug in slugs:
        for index in range(2):
            uploaded = web.post(
                f"/api/v1/references/{slug}/documents",
                files={
                    "file": (
                        f"{slug}-{index}.txt",
                        f"Known origin sample {slug} number {index}.".encode(),
                        "text/plain",
                    )
                },
            )
            assert uploaded.status_code == 200

    scan = web.post(
        "/api/v1/analyze/full",
        files={
            "file": (
                "suspect.txt",
                b"This is a suspect document with enough words for a basic scan.",
                "text/plain",
            )
        },
    )
    assert scan.status_code == 200, scan.text
    payload = scan.json()
    assert payload["origin_assessment"]["state"] == "NOT_TESTABLE"
    assert payload["reference_comparison"] is None
    family = {
        item["family"]: item
        for item in payload["family_summaries"]
    }["reference_stylometry"]
    assert family["state"] == "NOT_TESTABLE"
    assert "5 usable samples each" in family["summary"]
    assert "Ready sets: 0/2" in family["summary"]


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



def _minimal_odt_bytes(text: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("mimetype", "application/vnd.oasis.opendocument.text")
        archive.writestr(
            "META-INF/manifest.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
            <manifest:manifest
              xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0"/>""",
        )
        archive.writestr(
            "content.xml",
            f"""<?xml version="1.0" encoding="UTF-8"?>
            <office:document-content
              xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
              xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">
              <office:body>
                <office:text>
                  <text:p>{text}</text:p>
                </office:text>
              </office:body>
            </office:document-content>""",
        )
    return buffer.getvalue()


def test_private_odt_reference_participates_in_comparator(tmp_path) -> None:
    web = client(tmp_path)
    private_sets = {
        "ODT human": "I walked home after work and made tea before reading the newspaper.",
        "ODT model": (
            "Across the quiet valley, a lantern remained visible while the traveler "
            "considered the carefully described journey ahead."
        ),
    }

    for label, sample in private_sets.items():
        created = web.post(
            "/api/v1/references",
            json={"label": label, "source": "controlled-odt-test"},
        )
        assert created.status_code == 200, created.text
        slug = created.json()["slug"]

        odt_upload = web.post(
            f"/api/v1/references/{slug}/documents",
            files={
                "file": (
                    "sample-0.odt",
                    _minimal_odt_bytes(sample),
                    "application/vnd.oasis.opendocument.text",
                )
            },
        )
        assert odt_upload.status_code == 200, odt_upload.text

        for index in range(1, 5):
            txt_upload = web.post(
                f"/api/v1/references/{slug}/documents",
                files={
                    "file": (
                        f"sample-{index}.txt",
                        f"{sample} Controlled variant number {index}.".encode(),
                        "text/plain",
                    )
                },
            )
            assert txt_upload.status_code == 200, txt_upload.text

    status = web.get("/api/v1/references/status")
    assert status.status_code == 200, status.text
    status_payload = status.json()
    assert status_payload["active_scope"] == "tenant"
    assert status_payload["tenant_ready"] is True
    assert status_payload["total_tenant_documents"] == 10

    scan = web.post(
        "/api/v1/analyze/full",
        files={
            "file": (
                "suspect.txt",
                b"Across the quiet valley, the traveler followed a distant light.",
                "text/plain",
            )
        },
    )
    assert scan.status_code == 200, scan.text
    payload = scan.json()
    assert payload["origin_assessment"]["state"] == "REFERENCE_COMPARISON"
    assert {
        row["label"]
        for row in payload["reference_comparison"]["comparisons"]
    } == {"ODT human", "ODT model"}


def _write_global_reference_root(tmp_path):
    references = tmp_path / "global-references"
    sets = {
        "global-human": [
            "I walked home after work and made tea before reading the newspaper.",
            "We missed the bus, so my sister and I walked through the rain.",
            "The shop closed early and I waited outside with my old coat.",
            "I forgot my keys, called a friend, and sat near the front door.",
            "We ate lunch outside while the dog slept under the wooden table.",
        ],
        "global-model": [
            (
                "Across the quiet valley, a lantern remained visible while the traveler "
                "considered the carefully described journey ahead."
            ),
            (
                "Beneath the evening sky, the river reflected a gentle light while the "
                "traveler continued through the silent forest."
            ),
            (
                "Within the tranquil garden, every path seemed to invite another thoughtful "
                "step toward the softly illuminated horizon."
            ),
            (
                "Beyond the sleeping village, a pale moon appeared above the distant hills "
                "as the traveler reflected on the road ahead."
            ),
            (
                "Along the ancient road, a soft wind carried distant sounds while the "
                "traveler moved deliberately toward the morning light."
            ),
        ],
    }
    metadata = {
        "global-human": {
            "label": "Global human",
            "provider": "human",
            "source": "global-test",
            "language": "en",
        },
        "global-model": {
            "label": "Global model",
            "provider": "test-model",
            "model": "global-model-v1",
            "source": "global-test",
            "language": "en",
        },
    }
    for slug, samples in sets.items():
        directory = references / slug
        directory.mkdir(parents=True)
        (directory / ".xray-reference.json").write_text(
            json.dumps(metadata[slug]),
            encoding="utf-8",
        )
        for index, sample in enumerate(samples):
            (directory / f"{index}.txt").write_text(sample, encoding="utf-8")
    return references


def test_reference_status_exposes_global_baseline(tmp_path) -> None:
    references = _write_global_reference_root(tmp_path)
    app = create_app(
        WebSettings(
            data_root=tmp_path / "web-data",
            reference_root=references,
        )
    )
    web = TestClient(app)

    response = web.get("/api/v1/references/status")
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["active_scope"] == "global"
    assert payload["total_global_documents"] == 10
    assert payload["total_tenant_documents"] == 0
    assert payload["tenant_sets"] == []
    assert {
        item["label"]
        for item in payload["global_sets"]
    } == {"Global human", "Global model"}


def test_incomplete_private_references_do_not_disable_global(tmp_path) -> None:
    references = _write_global_reference_root(tmp_path)
    app = create_app(
        WebSettings(
            data_root=tmp_path / "web-data",
            reference_root=references,
        )
    )
    web = TestClient(app)

    private = web.post(
        "/api/v1/references",
        json={"label": "Private Claude", "source": "controlled-private"},
    )
    assert private.status_code == 200, private.text
    slug = private.json()["slug"]
    uploaded = web.post(
        f"/api/v1/references/{slug}/documents",
        files={
            "file": (
                "sample.txt",
                b"One private known-origin sample that is intentionally below readiness.",
                "text/plain",
            )
        },
    )
    assert uploaded.status_code == 200, uploaded.text

    status = web.get("/api/v1/references/status")
    assert status.status_code == 200
    status_payload = status.json()
    assert status_payload["active_scope"] == "global"
    assert status_payload["tenant_configured"] is True
    assert status_payload["tenant_ready"] is False
    assert status_payload["total_global_documents"] == 10
    assert status_payload["total_tenant_documents"] == 1

    scan = web.post(
        "/api/v1/analyze/full",
        files={
            "file": (
                "suspect.txt",
                (
                    b"Beneath the evening sky, the traveler followed the river "
                    b"toward a distant light beyond the quiet village."
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
    } == {"Global human", "Global model"}


def test_ready_private_references_layer_global_baseline(tmp_path) -> None:
    references = _write_global_reference_root(tmp_path)
    app = create_app(
        WebSettings(
            data_root=tmp_path / "web-data",
            reference_root=references,
        )
    )
    web = TestClient(app)

    private_sets = {
        "Private human": [
            b"I called home after dinner and wrote a short note before going to bed.",
            b"The train was late, so we waited by the station and talked about work.",
            b"I washed the dishes, opened the window, and listened to the traffic.",
            b"My neighbour knocked at noon and returned the book I had lent her.",
            b"We bought bread, walked home, and left our wet umbrellas by the door.",
        ],
        "Private model": [
            (
                b"Across a tranquil landscape, the traveler contemplated the distant "
                b"horizon with deliberate attention."
            ),
            (
                b"Beneath a luminous sky, the path unfolded gradually through a quiet "
                b"and carefully described valley."
            ),
            (
                b"Within the silent garden, each measured step suggested another moment "
                b"of thoughtful reflection."
            ),
            (
                b"Beyond the village, the gentle river reflected the evening light while "
                b"the traveler continued onward."
            ),
            (
                b"Along the distant road, a calm wind moved through the trees as the "
                b"traveler considered the journey."
            ),
        ],
    }

    for label, samples in private_sets.items():
        created = web.post(
            "/api/v1/references",
            json={"label": label, "source": "controlled-private"},
        )
        assert created.status_code == 200, created.text
        slug = created.json()["slug"]
        for index, sample in enumerate(samples):
            uploaded = web.post(
                f"/api/v1/references/{slug}/documents",
                files={
                    "file": (
                        f"{index}.txt",
                        sample,
                        "text/plain",
                    )
                },
            )
            assert uploaded.status_code == 200, uploaded.text

    status = web.get("/api/v1/references/status")
    assert status.status_code == 200, status.text
    status_payload = status.json()
    assert status_payload["active_scope"] == "combined"
    assert status_payload["tenant_ready"] is True
    assert status_payload["total_global_documents"] == 10
    assert status_payload["total_tenant_documents"] == 10

    scan = web.post(
        "/api/v1/analyze/full",
        files={
            "file": (
                "suspect.txt",
                (
                    b"Across the quiet valley, the traveler continued toward a softly "
                    b"illuminated horizon while considering the road ahead."
                ),
                "text/plain",
            )
        },
    )
    assert scan.status_code == 200, scan.text
    payload = scan.json()
    labels = {
        row["label"]
        for row in payload["reference_comparison"]["comparisons"]
    }
    assert labels == {
        "Global human",
        "Global model",
        "Private human",
        "Private model",
    }
