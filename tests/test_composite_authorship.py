from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from xray_text_forensics.web import WebSettings, create_app
from xray_text_forensics.web.composite import load_frozen_composite


class FakeComposite:
    def __init__(self, payload: dict[str, Any] | None = None, *, fail: bool = False) -> None:
        self.payload = payload or {}
        self.fail = fail

    def classify(self, text: str) -> dict[str, Any]:
        if self.fail:
            raise RuntimeError("synthetic runtime failure")
        return self.payload



class UnhealthyComposite(FakeComposite):
    def health(self) -> bool:
        return False

def _scan(tmp_path, classifier: FakeComposite, text: str | None = None) -> dict[str, Any]:
    app = create_app(
        WebSettings(data_root=tmp_path / "web-data"),
        composite_classifier=classifier,
    )
    web = TestClient(app)
    sample = text or ("Una historia suficientemente larga para el análisis. " * 30)
    response = web.post(
        "/api/v1/analyze/full",
        files={"file": ("sample.txt", sample.encode("utf-8"), "text/plain")},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _payload(state: str, *, eligible: bool = True) -> dict[str, Any]:
    return {
        "state": state,
        "eligible": eligible,
        "original_tokens": 180 if eligible else 4,
        "ai_likely": state == "AI_LIKELY",
        "human_likely": state == "HUMAN_LIKELY",
        "parent_score": 2.1 if state == "AI_LIKELY" else 0.1,
        "specialist_score": 0.2,
        "combined_score": 0.3,
        "p_human": 0.999 if state == "HUMAN_LIKELY" else 0.4,
        "human_density_score": -80.0 if state == "HUMAN_LIKELY" else -200.0,
        "human_score": 0.2 if state == "HUMAN_LIKELY" else -0.5,
        "versions": {
            "composite_freeze_sha256": "frozen",
            "ai_closure_sha256": "ai",
            "human_closure_sha256": "human",
        },
    }


def test_ai_likely_authorship_is_separate_from_reference_origin(tmp_path) -> None:
    payload = _scan(tmp_path, FakeComposite(_payload("AI_LIKELY")))
    assert payload["authorship_assessment"]["state"] == "AI_LIKELY"
    assert payload["authorship_assessment"]["ai_likely"] is True
    assert payload["authorship_assessment"]["human_likely"] is False
    assert "no prueba criptográfica" in payload["authorship_assessment"]["disclaimer"]
    assert payload["origin_assessment"]["state"] == "NOT_TESTABLE"
    families = {row["family"]: row for row in payload["family_summaries"]}
    assert families["ai_authorship"]["state"] == "COMPLETE"
    assert families["reference_stylometry"]["state"] == "NOT_TESTABLE"


def test_human_likely_and_inconclusive_states_are_preserved(tmp_path) -> None:
    human = _scan(tmp_path / "human", FakeComposite(_payload("HUMAN_LIKELY")))
    assert human["authorship_assessment"]["state"] == "HUMAN_LIKELY"
    assert human["authorship_assessment"]["human_likely"] is True

    inconclusive = _scan(tmp_path / "inc", FakeComposite(_payload("INCONCLUSIVE")))
    assert inconclusive["authorship_assessment"]["state"] == "INCONCLUSIVE"
    assert inconclusive["authorship_assessment"]["ai_likely"] is False
    assert inconclusive["authorship_assessment"]["human_likely"] is False


def test_ineligible_composite_result_is_insufficient_not_negative_evidence(tmp_path) -> None:
    result = _payload("INCONCLUSIVE", eligible=False)
    payload = _scan(tmp_path, FakeComposite(result), text="texto corto")
    assessment = payload["authorship_assessment"]
    assert assessment["state"] == "INCONCLUSIVE"
    assert assessment["eligible"] is False
    families = {row["family"]: row for row in payload["family_summaries"]}
    assert families["ai_authorship"]["state"] == "INSUFFICIENT_DATA"


def test_composite_runtime_failure_does_not_become_authorship_verdict(tmp_path) -> None:
    payload = _scan(tmp_path, FakeComposite(fail=True))
    assessment = payload["authorship_assessment"]
    assert assessment["state"] == "ERROR"
    assert "does not convert" in assessment["explanation"]
    families = {row["family"]: row for row in payload["family_summaries"]}
    assert families["ai_authorship"]["state"] == "ERROR"


def test_unconfigured_composite_remains_not_testable(tmp_path) -> None:
    app = create_app(WebSettings(data_root=tmp_path / "web-data"))
    web = TestClient(app)
    response = web.post(
        "/api/v1/analyze/full",
        files={
            "file": (
                "sample.txt",
                ("Texto humano de ejemplo para una prueba controlada. " * 20).encode(),
                "text/plain",
            )
        },
    )
    assert response.status_code == 200
    assert response.json()["authorship_assessment"]["state"] == "NOT_TESTABLE"
    ready = web.get("/api/v1/ready")
    assert ready.status_code == 200
    assert ready.json()["checks"]["composite_runtime"] == "not_configured"


def test_configured_broken_composite_fails_readiness(tmp_path) -> None:
    bad_root = tmp_path / "broken-composite"
    bad_root.mkdir()
    settings = WebSettings(
        data_root=tmp_path / "web-data",
        composite_root=bad_root,
    )
    app = create_app(settings)
    web = TestClient(app)
    ready = web.get("/api/v1/ready")
    assert ready.status_code == 503
    assert ready.json()["checks"]["composite_runtime"] == "error"


def test_loader_rejects_unverified_runtime_without_importing_heavy_dependencies(tmp_path) -> None:
    root = tmp_path / "runtime"
    root.mkdir()
    result = load_frozen_composite(root)
    assert result.classifier is None
    assert result.status == "error"
    assert result.reason is not None
    assert "Missing frozen composite artifact" in result.reason


def test_configured_unhealthy_worker_fails_live_readiness(tmp_path) -> None:
    configured_root = tmp_path / "configured-runtime"
    configured_root.mkdir()
    app = create_app(
        WebSettings(
            data_root=tmp_path / "web-data-live",
            composite_root=configured_root,
        ),
        composite_classifier=UnhealthyComposite(_payload("INCONCLUSIVE")),
    )
    web = TestClient(app)
    ready = web.get("/api/v1/ready")
    assert ready.status_code == 503
    assert ready.json()["checks"]["composite_runtime"] == "error"
