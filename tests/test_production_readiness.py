from __future__ import annotations

import json
import logging
import sqlite3
import time
from threading import Event

import pytest
from fastapi.testclient import TestClient

from xray_text_forensics.cases import CaseStore
from xray_text_forensics.core import Case
from xray_text_forensics.web import WebSettings, create_app
from xray_text_forensics.web.jobs import JobCapacityError, JobManager, JobStatus


def test_case_store_adopts_legacy_schema_without_rewriting_cases(tmp_path) -> None:
    database = tmp_path / "legacy.sqlite"
    legacy_case = Case(title="Legacy case")
    connection = sqlite3.connect(database)
    connection.execute(
        "CREATE TABLE cases (case_id TEXT PRIMARY KEY, payload TEXT NOT NULL)"
    )
    connection.execute(
        "INSERT INTO cases(case_id, payload) VALUES (?, ?)",
        (legacy_case.case_id, legacy_case.model_dump_json()),
    )
    connection.commit()
    connection.close()

    with CaseStore(database) as store:
        assert store.schema_version() == 1
        bundle = store.fetch_bundle(legacy_case.case_id)
        assert bundle.case.title == "Legacy case"
        assert bundle.artifacts == []


def test_case_store_rejects_future_schema(tmp_path) -> None:
    database = tmp_path / "future.sqlite"
    connection = sqlite3.connect(database)
    connection.execute(
        """
        CREATE TABLE schema_meta (
            singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
            version INTEGER NOT NULL
        )
        """
    )
    connection.execute(
        "INSERT INTO schema_meta(singleton, version) VALUES (1, 999)"
    )
    connection.commit()
    connection.close()

    with pytest.raises(RuntimeError, match="newer than supported"):
        CaseStore(database)


def test_production_environment_defaults_docs_off(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("XRAY_ENV", "production")
    monkeypatch.setenv("XRAY_DATA_ROOT", str(tmp_path / "production-data"))
    monkeypatch.setenv("XRAY_MAX_JOB_WORKERS", "3")
    monkeypatch.setenv("XRAY_MAX_PENDING_JOBS", "12")
    monkeypatch.delenv("XRAY_DOCS_ENABLED", raising=False)

    settings = WebSettings.from_environment()
    assert settings.environment == "production"
    assert settings.docs_enabled is False
    assert settings.max_job_workers == 3
    assert settings.max_pending_jobs == 12


def test_readiness_checks_database_wal_and_object_store(tmp_path) -> None:
    app = create_app(
        WebSettings(
            data_root=tmp_path / "data",
            environment="test",
            request_logging=False,
        )
    )
    with TestClient(app) as client:
        response = client.get("/api/v1/ready")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["schema_version"] == 1
    assert payload["checks"]["database"] == "ok"
    assert payload["checks"]["journal_mode"] == "wal"
    assert payload["checks"]["object_store"] == "ok"
    assert payload["environment"] == "test"


def test_request_id_is_propagated_and_logged_as_json(tmp_path, caplog) -> None:
    app = create_app(WebSettings(data_root=tmp_path / "data", environment="test"))
    caplog.set_level(logging.INFO, logger="xray.web.access")

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/health",
            headers={"X-Request-ID": "client-request-123"},
        )

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "client-request-123"

    access_records = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "xray.web.access"
    ]
    assert access_records
    latest = access_records[-1]
    assert latest["event"] == "http_request"
    assert latest["request_id"] == "client-request-123"
    assert latest["path"] == "/api/v1/health"
    assert latest["status_code"] == 200
    assert latest["duration_ms"] >= 0


def test_invalid_request_id_is_replaced(tmp_path) -> None:
    app = create_app(
        WebSettings(
            data_root=tmp_path / "data",
            environment="test",
            request_logging=False,
        )
    )
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/health",
            headers={"X-Request-ID": "not a valid request id"},
        )

    request_id = response.headers["x-request-id"]
    assert request_id.startswith("req_")
    assert request_id != "not a valid request id"


def test_job_manager_enforces_in_flight_capacity() -> None:
    manager = JobManager(max_workers=1, max_pending_jobs=1)
    entered = Event()
    release = Event()

    def slow_task() -> dict[str, object]:
        entered.set()
        assert release.wait(timeout=5)
        return {"ok": True}

    try:
        first = manager.submit(kind="slow", task=slow_task)
        assert entered.wait(timeout=5)
        with pytest.raises(JobCapacityError):
            manager.submit(kind="overflow", task=lambda: {"ok": True})

        release.set()
        for _ in range(100):
            current = manager.get(first.job_id)
            assert current is not None
            if current.status is JobStatus.SUCCEEDED:
                break
            time.sleep(0.01)
        else:
            raise AssertionError("background job did not finish")

        assert current.result == {"ok": True}
    finally:
        release.set()
        manager.shutdown()


def test_compare_transform_background_job_api(tmp_path) -> None:
    app = create_app(
        WebSettings(
            data_root=tmp_path / "data",
            environment="test",
            request_logging=False,
        )
    )
    document = b"alpha beta gamma delta epsilon zeta"

    with TestClient(app) as client:
        submitted = client.post(
            "/api/v1/jobs/compare-transform",
            files={
                "original": ("original.txt", document, "text/plain"),
                "transformed": ("transformed.txt", document, "text/plain"),
            },
        )
        assert submitted.status_code == 202, submitted.text
        job_id = submitted.json()["job_id"]

        for _ in range(100):
            response = client.get(f"/api/v1/jobs/{job_id}")
            assert response.status_code == 200
            payload = response.json()
            if payload["status"] == "SUCCEEDED":
                break
            time.sleep(0.01)
        else:
            raise AssertionError("job API did not complete")

    assert payload["result"]["fivegram_survival"] == 1.0
    assert payload["result"]["lexical_tfidf_cosine"] == 1.0
    assert payload["error"] is None
