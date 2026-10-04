from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from xray_text_forensics.web import WebSettings, create_app
from xray_text_forensics.web.identity import Principal
from xray_text_forensics.web.tenant_storage import TenantStorageResolver

_GATEWAY_SECRET = "gateway-secret-" + ("x" * 48)


def gateway_headers(
    tenant: str,
    *,
    subject: str = "user-1",
    secret: str = _GATEWAY_SECRET,
) -> dict[str, str]:
    return {
        "X-XRay-Gateway-Secret": secret,
        "X-XRay-Tenant": tenant,
        "X-XRay-Subject": subject,
        "X-XRay-Roles": "analyst,viewer",
    }


def gateway_client(tmp_path) -> TestClient:
    app = create_app(
        WebSettings(
            data_root=tmp_path / "saas-data",
            environment="test",
            request_logging=False,
            identity_mode="gateway",
            gateway_shared_secret=_GATEWAY_SECRET,
        )
    )
    return TestClient(app)


def test_gateway_mode_fails_closed_without_shared_secret(tmp_path) -> None:
    with pytest.raises(ValueError, match="XRAY_GATEWAY_SHARED_SECRET"):
        create_app(
            WebSettings(
                data_root=tmp_path / "data",
                environment="test",
                identity_mode="gateway",
                gateway_shared_secret=None,
            )
        )


def test_liveness_and_readiness_remain_public_but_private_api_requires_auth(tmp_path) -> None:
    with gateway_client(tmp_path) as client:
        assert client.get("/api/v1/health").status_code == 200
        assert client.get("/api/v1/ready").status_code == 200

        response = client.post("/api/v1/cases", json={"title": "No auth"})
        assert response.status_code == 401
        assert response.json()["detail"] == "Authentication required"


def test_wrong_gateway_secret_and_invalid_identity_are_rejected(tmp_path) -> None:
    with gateway_client(tmp_path) as client:
        wrong = client.get(
            "/api/v1/session",
            headers=gateway_headers("tenant-a", secret="z" * 64),
        )
        assert wrong.status_code == 401

        malformed = client.get(
            "/api/v1/session",
            headers=gateway_headers("../tenant-a"),
        )
        assert malformed.status_code == 401


def test_authenticated_session_exposes_only_verified_principal(tmp_path) -> None:
    with gateway_client(tmp_path) as client:
        response = client.get(
            "/api/v1/session",
            headers=gateway_headers("tenant-a", subject="alice"),
        )

    assert response.status_code == 200
    principal = Principal.model_validate(response.json())
    assert principal.tenant_id == "tenant-a"
    assert principal.subject_id == "alice"
    assert principal.roles == ("analyst", "viewer")
    assert principal.auth_method == "gateway"


def test_cases_are_isolated_across_tenants(tmp_path) -> None:
    with gateway_client(tmp_path) as client:
        created = client.post(
            "/api/v1/cases",
            json={"title": "Tenant A Case"},
            headers=gateway_headers("tenant-a", subject="alice"),
        )
        assert created.status_code == 200, created.text
        case_id = created.json()["case_id"]

        same_tenant = client.get(
            f"/api/v1/cases/{case_id}",
            headers=gateway_headers("tenant-a", subject="bob"),
        )
        assert same_tenant.status_code == 200

        other_tenant = client.get(
            f"/api/v1/cases/{case_id}",
            headers=gateway_headers("tenant-b", subject="mallory"),
        )
        assert other_tenant.status_code == 404


def test_artifact_storage_is_physically_separated_by_opaque_tenant_directory(tmp_path) -> None:
    data_root = tmp_path / "saas-data"
    resolver = TenantStorageResolver(data_root)

    tenant_a = resolver.for_principal(
        Principal(
            tenant_id="customer-alpha",
            subject_id="alice",
            auth_method="test",
        )
    )
    tenant_b = resolver.for_principal(
        Principal(
            tenant_id="customer-beta",
            subject_id="bob",
            auth_method="test",
        )
    )
    local = resolver.for_principal(
        Principal(
            tenant_id="local",
            subject_id="local-user",
            auth_method="local",
        )
    )

    assert tenant_a.root != tenant_b.root
    assert tenant_a.root.parent == data_root / "tenants"
    assert tenant_b.root.parent == data_root / "tenants"
    assert "customer-alpha" not in str(tenant_a.root)
    assert "customer-beta" not in str(tenant_b.root)
    assert local.root == data_root


def test_same_artifact_bytes_are_stored_inside_each_tenant_scope(tmp_path) -> None:
    data_root = tmp_path / "saas-data"
    payload = b"same evidence bytes"

    with gateway_client(tmp_path) as client:
        for tenant in ("tenant-a", "tenant-b"):
            response = client.post(
                "/api/v1/ingest",
                files={"file": ("evidence.txt", payload, "text/plain")},
                headers=gateway_headers(tenant),
            )
            assert response.status_code == 200, response.text

    resolver = TenantStorageResolver(data_root)
    roots = [
        resolver.for_principal(
            Principal(
                tenant_id=tenant,
                subject_id="user",
                auth_method="test",
            )
        ).object_store_root
        for tenant in ("tenant-a", "tenant-b")
    ]
    for root in roots:
        stored_files = [path for path in root.rglob("*") if path.is_file()]
        assert stored_files


def test_background_job_ids_cannot_cross_tenant_boundary(tmp_path) -> None:
    document = b"alpha beta gamma delta epsilon zeta"

    with gateway_client(tmp_path) as client:
        submitted = client.post(
            "/api/v1/jobs/compare-transform",
            files={
                "original": ("original.txt", document, "text/plain"),
                "transformed": ("transformed.txt", document, "text/plain"),
            },
            headers=gateway_headers("tenant-a"),
        )
        assert submitted.status_code == 202, submitted.text
        job_id = submitted.json()["job_id"]

        other_tenant = client.get(
            f"/api/v1/jobs/{job_id}",
            headers=gateway_headers("tenant-b"),
        )
        assert other_tenant.status_code == 404

        for _ in range(100):
            own = client.get(
                f"/api/v1/jobs/{job_id}",
                headers=gateway_headers("tenant-a"),
            )
            assert own.status_code == 200
            if own.json()["status"] == "SUCCEEDED":
                break
            time.sleep(0.01)
        else:
            raise AssertionError("tenant-owned background job did not finish")

    assert own.json()["result"]["fivegram_survival"] == 1.0


def test_gateway_identity_configuration_reads_from_environment(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("XRAY_ENV", "production")
    monkeypatch.setenv("XRAY_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("XRAY_IDENTITY_MODE", "gateway")
    monkeypatch.setenv("XRAY_GATEWAY_SHARED_SECRET", _GATEWAY_SECRET)

    settings = WebSettings.from_environment()

    assert settings.identity_mode == "gateway"
    assert settings.gateway_shared_secret == _GATEWAY_SECRET
