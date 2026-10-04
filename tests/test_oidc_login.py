from __future__ import annotations

import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from xray_text_forensics.web import WebSettings, create_app
from xray_text_forensics.web.identity import Principal
from xray_text_forensics.web.oidc import (
    AuthorizationStart,
    GenericOidcClient,
    OidcError,
    OidcSessionStore,
)


class FakeOidcClient:
    def __init__(self) -> None:
        self.start = AuthorizationStart(
            url=(
                "https://identity.example/authorize"
                "?response_type=code&state=fake-state"
            ),
            state="fake-state",
            nonce="fake-nonce",
            code_verifier="fake-verifier",
        )
        self.completed: list[dict[str, object]] = []

    def authorization_start(
        self,
        *,
        redirect_uri: str,
        scopes: str,
    ) -> AuthorizationStart:
        assert redirect_uri == "http://testserver/auth/callback"
        assert scopes == "openid profile email"
        return self.start

    def complete(self, **kwargs: object) -> tuple[Principal, int]:
        self.completed.append(kwargs)
        assert kwargs["code"] == "valid-code"
        assert kwargs["redirect_uri"] == "http://testserver/auth/callback"
        assert kwargs["code_verifier"] == "fake-verifier"
        assert kwargs["expected_nonce"] == "fake-nonce"
        return (
            Principal(
                tenant_id="org_test",
                subject_id="user_test",
                roles=("analyst",),
                auth_method="oidc",
            ),
            int(time.time()) + 3600,
        )


def oidc_settings(tmp_path) -> WebSettings:
    return WebSettings(
        data_root=tmp_path / "data",
        environment="test",
        request_logging=False,
        identity_mode="oidc",
        public_base_url="http://testserver",
        oidc_issuer_url="https://identity.example",
        oidc_client_id="client_test",
        oidc_client_secret="secret_test",
    )


def test_oidc_mode_fails_closed_when_configuration_is_incomplete(tmp_path) -> None:
    with pytest.raises(ValueError, match="OIDC mode requires"):
        create_app(
            WebSettings(
                data_root=tmp_path / "data",
                environment="test",
                identity_mode="oidc",
            )
        )


def test_production_oidc_requires_https_public_base_and_issuer(tmp_path) -> None:
    with pytest.raises(ValueError, match="https XRAY_PUBLIC_BASE_URL"):
        create_app(
            WebSettings(
                data_root=tmp_path / "data",
                environment="production",
                identity_mode="oidc",
                public_base_url="http://xray.example",
                oidc_issuer_url="https://identity.example",
                oidc_client_id="client",
                oidc_client_secret="secret",
            )
        )


def test_oidc_login_callback_creates_opaque_server_side_session(tmp_path) -> None:
    fake = FakeOidcClient()
    app = create_app(oidc_settings(tmp_path), oidc_client=fake)

    with TestClient(app) as client:
        before = client.get("/api/v1/session")
        assert before.status_code == 401

        login = client.get(
            "/auth/login",
            params={"return_to": "/"},
            follow_redirects=False,
        )
        assert login.status_code == 302
        assert login.headers["location"].startswith("https://identity.example/authorize")
        state_cookie = login.headers["set-cookie"].lower()
        assert "xray_oidc_state=" in state_cookie
        assert "httponly" in state_cookie
        assert "samesite=lax" in state_cookie

        callback = client.get(
            "/auth/callback",
            params={"code": "valid-code", "state": "fake-state"},
            follow_redirects=False,
        )
        assert callback.status_code == 303
        assert callback.headers["location"] == "/"
        session_cookie = callback.headers["set-cookie"].lower()
        assert "xray_session=" in session_cookie
        assert "httponly" in session_cookie
        assert "samesite=lax" in session_cookie
        assert "valid-code" not in session_cookie
        assert "secret_test" not in session_cookie

        session = client.get("/api/v1/session")
        assert session.status_code == 200
        assert session.json() == {
            "tenant_id": "org_test",
            "subject_id": "user_test",
            "roles": ["analyst"],
            "auth_method": "oidc",
        }

        logout = client.get("/auth/logout", follow_redirects=False)
        assert logout.status_code == 303
        assert logout.headers["location"] == "/"
        assert client.get("/api/v1/session").status_code == 401

    assert len(fake.completed) == 1


def test_oidc_callback_rejects_state_mismatch(tmp_path) -> None:
    fake = FakeOidcClient()
    app = create_app(oidc_settings(tmp_path), oidc_client=fake)

    with TestClient(app) as client:
        client.get("/auth/login", follow_redirects=False)
        response = client.get(
            "/auth/callback",
            params={"code": "valid-code", "state": "attacker-state"},
        )

    assert response.status_code == 400
    assert fake.completed == []


def test_oidc_pending_state_is_one_time_and_return_to_is_local(tmp_path) -> None:
    fake = FakeOidcClient()
    store = OidcSessionStore(tmp_path / "auth.sqlite")
    try:
        pending = store.store_pending(
            start=fake.start,
            return_to="https://attacker.example/phish",
        )
        assert pending.return_to == "/"
        assert store.consume_pending("fake-state") is not None
        assert store.consume_pending("fake-state") is None
    finally:
        store.close()


def test_generic_oidc_authorization_request_uses_pkce_state_and_nonce(monkeypatch) -> None:
    client = GenericOidcClient(
        issuer_url="https://identity.example",
        client_id="client_test",
        client_secret="secret_test",
    )
    monkeypatch.setattr(
        client,
        "_get_discovery",
        lambda: {
            "issuer": "https://identity.example",
            "authorization_endpoint": "https://identity.example/authorize",
            "token_endpoint": "https://identity.example/token",
            "jwks_uri": "https://identity.example/jwks",
        },
    )

    start = client.authorization_start(
        redirect_uri="https://xray.example/auth/callback",
        scopes="openid profile email",
    )
    parsed = urlparse(start.url)
    query = parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert query["response_type"] == ["code"]
    assert query["client_id"] == ["client_test"]
    assert query["state"] == [start.state]
    assert query["nonce"] == [start.nonce]
    assert query["code_challenge_method"] == ["S256"]
    assert query["code_challenge"][0]
    assert start.code_verifier not in start.url


def test_generic_oidc_verifies_signature_issuer_audience_and_nonce() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    now = int(time.time())
    claims = {
        "iss": "https://identity.example",
        "aud": "client_test",
        "sub": "user_123",
        "nonce": "nonce_123",
        "iat": now,
        "exp": now + 600,
        "org_id": "org_123",
    }
    token = jwt.encode(
        claims,
        private_key,
        algorithm="RS256",
        headers={"kid": "key-1"},
    )

    client = GenericOidcClient(
        issuer_url="https://identity.example",
        client_id="client_test",
        client_secret="secret_test",
    )
    client._jwks_client = SimpleNamespace(  # type: ignore[assignment]
        get_signing_key_from_jwt=lambda _: SimpleNamespace(key=public_key)
    )
    discovery = {
        "issuer": "https://identity.example",
        "jwks_uri": "https://identity.example/jwks",
        "id_token_signing_alg_values_supported": ["RS256"],
    }

    verified = client._verify_id_token(  # noqa: SLF001
        token,
        discovery=discovery,
        expected_nonce="nonce_123",
    )
    assert verified["sub"] == "user_123"

    with pytest.raises(OidcError, match="nonce"):
        client._verify_id_token(  # noqa: SLF001
            token,
            discovery=discovery,
            expected_nonce="wrong-nonce",
        )


def test_generic_oidc_maps_org_role_and_personal_fallback(monkeypatch) -> None:
    client = GenericOidcClient(
        issuer_url="https://identity.example",
        client_id="client_test",
        client_secret="secret_test",
    )
    discovery = {
        "issuer": "https://identity.example",
        "authorization_endpoint": "https://identity.example/authorize",
        "token_endpoint": "https://identity.example/token",
        "jwks_uri": "https://identity.example/jwks",
    }
    monkeypatch.setattr(client, "_get_discovery", lambda: discovery)

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, str]:
            return {
                "id_token": "fake-id-token",
                "access_token": "fake-access-token",
            }

    monkeypatch.setattr(
        "xray_text_forensics.web.oidc.httpx.post",
        lambda *args, **kwargs: FakeResponse(),
    )

    now = int(time.time())
    monkeypatch.setattr(
        client,
        "_verify_id_token",
        lambda *args, **kwargs: {
            "sub": "user_1",
            "exp": now + 600,
        },
    )
    monkeypatch.setattr(
        client,
        "_verify_access_token",
        lambda *args, **kwargs: {
            "sub": "user_1",
            "org_id": "org_1",
            "role": "admin",
            "exp": now + 300,
        },
    )
    principal, _ = client.complete(
        code="code",
        redirect_uri="https://xray.example/auth/callback",
        code_verifier="verifier",
        expected_nonce="nonce",
        tenant_claim="org_id",
        role_claim="role",
        allow_personal_tenant=True,
    )
    assert principal.tenant_id == "org_1"
    assert principal.roles == ("admin",)

    monkeypatch.setattr(
        client,
        "_verify_id_token",
        lambda *args, **kwargs: {
            "sub": "user_2",
            "exp": now + 600,
        },
    )
    monkeypatch.setattr(
        client,
        "_verify_access_token",
        lambda *args, **kwargs: {
            "sub": "user_2",
            "exp": now + 300,
        },
    )
    personal, _ = client.complete(
        code="code",
        redirect_uri="https://xray.example/auth/callback",
        code_verifier="verifier",
        expected_nonce="nonce",
        tenant_claim="org_id",
        role_claim="role",
        allow_personal_tenant=True,
    )
    assert personal.tenant_id == "personal:user_2"


def test_oidc_readiness_includes_auth_database(tmp_path) -> None:
    fake = FakeOidcClient()
    app = create_app(oidc_settings(tmp_path), oidc_client=fake)

    with TestClient(app) as client:
        response = client.get("/api/v1/ready")

    assert response.status_code == 200
    payload = response.json()
    assert payload["checks"]["identity_mode"] == "oidc"
    assert payload["checks"]["auth_database"] == "ok"
    assert payload["checks"]["auth_journal_mode"] == "wal"


def test_generic_oidc_rejects_subject_mismatch(monkeypatch) -> None:
    client = GenericOidcClient(
        issuer_url="https://identity.example",
        client_id="client_test",
        client_secret="secret_test",
    )
    monkeypatch.setattr(
        client,
        "_get_discovery",
        lambda: {
            "issuer": "https://identity.example",
            "authorization_endpoint": "https://identity.example/authorize",
            "token_endpoint": "https://identity.example/token",
            "jwks_uri": "https://identity.example/jwks",
        },
    )

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, str]:
            return {
                "id_token": "fake-id-token",
                "access_token": "fake-access-token",
            }

    monkeypatch.setattr(
        "xray_text_forensics.web.oidc.httpx.post",
        lambda *args, **kwargs: FakeResponse(),
    )
    now = int(time.time())
    monkeypatch.setattr(
        client,
        "_verify_id_token",
        lambda *args, **kwargs: {
            "sub": "identity-user",
            "exp": now + 600,
        },
    )
    monkeypatch.setattr(
        client,
        "_verify_access_token",
        lambda *args, **kwargs: {
            "sub": "different-user",
            "org_id": "org_1",
            "exp": now + 300,
        },
    )

    with pytest.raises(OidcError, match="subject"):
        client.complete(
            code="code",
            redirect_uri="https://xray.example/auth/callback",
            code_verifier="verifier",
            expected_nonce="nonce",
            tenant_claim="org_id",
            role_claim="role",
            allow_personal_tenant=True,
        )


def test_access_token_can_use_independent_audience() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    now = int(time.time())
    token = jwt.encode(
        {
            "iss": "https://identity.example",
            "aud": "https://api.xray.example",
            "sub": "user_123",
            "iat": now,
            "exp": now + 600,
            "org_id": "org_123",
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "key-1"},
    )
    discovery = {
        "issuer": "https://identity.example",
        "jwks_uri": "https://identity.example/jwks",
        "id_token_signing_alg_values_supported": ["RS256"],
    }

    configured = GenericOidcClient(
        issuer_url="https://identity.example",
        client_id="client_test",
        client_secret="secret_test",
        access_token_audience="https://api.xray.example",
    )
    configured._jwks_client = SimpleNamespace(  # type: ignore[assignment]
        get_signing_key_from_jwt=lambda _: SimpleNamespace(key=public_key)
    )
    verified = configured._verify_access_token(  # noqa: SLF001
        token,
        discovery=discovery,
    )
    assert verified["org_id"] == "org_123"

    default_audience = GenericOidcClient(
        issuer_url="https://identity.example",
        client_id="client_test",
        client_secret="secret_test",
    )
    default_audience._jwks_client = SimpleNamespace(  # type: ignore[assignment]
        get_signing_key_from_jwt=lambda _: SimpleNamespace(key=public_key)
    )
    with pytest.raises(OidcError, match="validation"):
        default_audience._verify_access_token(  # noqa: SLF001
            token,
            discovery=discovery,
        )
