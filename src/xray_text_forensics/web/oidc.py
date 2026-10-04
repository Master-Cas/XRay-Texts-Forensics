"""Generic OIDC authorization-code + PKCE login support."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any, Protocol
from urllib.parse import urlencode, urlparse

import httpx
import jwt
from pydantic import BaseModel
from starlette.requests import Request

from .identity import IdentityProvider, Principal

SESSION_COOKIE = "xray_session"
STATE_COOKIE = "xray_oidc_state"
_SAFE_ID_TOKEN_ALGS = {"RS256", "PS256", "ES256"}


class OidcError(RuntimeError):
    pass


class PendingAuthorization(BaseModel):
    state: str
    nonce: str
    code_verifier: str
    return_to: str
    expires_at: int


class StoredSession(BaseModel):
    session_id: str
    principal: Principal
    expires_at: int


@dataclass(frozen=True, slots=True)
class AuthorizationStart:
    url: str
    state: str
    nonce: str
    code_verifier: str


class OidcClientProtocol(Protocol):
    def authorization_start(
        self,
        *,
        redirect_uri: str,
        scopes: str,
    ) -> AuthorizationStart: ...

    def complete(
        self,
        *,
        code: str,
        redirect_uri: str,
        code_verifier: str,
        expected_nonce: str,
        tenant_claim: str,
        role_claim: str,
        allow_personal_tenant: bool,
    ) -> tuple[Principal, int]: ...


class OidcSessionStore:
    """SQLite-backed opaque browser sessions and one-time authorization state."""

    def __init__(self, database: Path) -> None:
        database.parent.mkdir(parents=True, exist_ok=True)
        self.database = database
        self.connection = sqlite3.connect(
            database,
            check_same_thread=False,
        )
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=FULL")
        self._lock = Lock()
        self._create_schema()

    def close(self) -> None:
        with self._lock:
            self.connection.close()

    def store_pending(
        self,
        *,
        start: AuthorizationStart,
        return_to: str,
        ttl_seconds: int = 600,
    ) -> PendingAuthorization:
        now = int(time.time())
        pending = PendingAuthorization(
            state=start.state,
            nonce=start.nonce,
            code_verifier=start.code_verifier,
            return_to=_safe_return_to(return_to),
            expires_at=now + ttl_seconds,
        )
        with self._lock:
            self._prune_locked(now)
            self.connection.execute(
                """
                INSERT OR REPLACE INTO oidc_pending(
                    state, nonce, code_verifier, return_to, expires_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    pending.state,
                    pending.nonce,
                    pending.code_verifier,
                    pending.return_to,
                    pending.expires_at,
                ),
            )
            self.connection.commit()
        return pending

    def consume_pending(self, state: str) -> PendingAuthorization | None:
        now = int(time.time())
        with self._lock:
            row = self.connection.execute(
                """
                SELECT state, nonce, code_verifier, return_to, expires_at
                FROM oidc_pending
                WHERE state=?
                """,
                (state,),
            ).fetchone()
            self.connection.execute(
                "DELETE FROM oidc_pending WHERE state=?",
                (state,),
            )
            self.connection.commit()

        if row is None:
            return None
        pending = PendingAuthorization(
            state=str(row[0]),
            nonce=str(row[1]),
            code_verifier=str(row[2]),
            return_to=str(row[3]),
            expires_at=int(row[4]),
        )
        if pending.expires_at <= now:
            return None
        return pending

    def create_session(
        self,
        *,
        principal: Principal,
        expires_at: int,
    ) -> StoredSession:
        now = int(time.time())
        if expires_at <= now:
            raise OidcError("Cannot create an already-expired session")

        session = StoredSession(
            session_id=secrets.token_urlsafe(32),
            principal=principal,
            expires_at=expires_at,
        )
        with self._lock:
            self._prune_locked(now)
            self.connection.execute(
                """
                INSERT INTO oidc_sessions(
                    session_id, tenant_id, subject_id, roles_json,
                    auth_method, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    session.session_id,
                    principal.tenant_id,
                    principal.subject_id,
                    json.dumps(list(principal.roles)),
                    principal.auth_method,
                    session.expires_at,
                ),
            )
            self.connection.commit()
        return session

    def get_session(self, session_id: str) -> StoredSession | None:
        now = int(time.time())
        with self._lock:
            row = self.connection.execute(
                """
                SELECT tenant_id, subject_id, roles_json, auth_method, expires_at
                FROM oidc_sessions
                WHERE session_id=?
                """,
                (session_id,),
            ).fetchone()
            if row is not None and int(row[4]) <= now:
                self.connection.execute(
                    "DELETE FROM oidc_sessions WHERE session_id=?",
                    (session_id,),
                )
                self.connection.commit()
                return None

        if row is None:
            return None
        return StoredSession(
            session_id=session_id,
            principal=Principal(
                tenant_id=str(row[0]),
                subject_id=str(row[1]),
                roles=tuple(json.loads(str(row[2]))),
                auth_method=str(row[3]),
            ),
            expires_at=int(row[4]),
        )

    def delete_session(self, session_id: str) -> None:
        with self._lock:
            self.connection.execute(
                "DELETE FROM oidc_sessions WHERE session_id=?",
                (session_id,),
            )
            self.connection.commit()

    def _create_schema(self) -> None:
        with self._lock:
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS oidc_pending (
                    state TEXT PRIMARY KEY,
                    nonce TEXT NOT NULL,
                    code_verifier TEXT NOT NULL,
                    return_to TEXT NOT NULL,
                    expires_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS oidc_sessions (
                    session_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    roles_json TEXT NOT NULL,
                    auth_method TEXT NOT NULL,
                    expires_at INTEGER NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_oidc_sessions_expires
                ON oidc_sessions(expires_at);

                CREATE INDEX IF NOT EXISTS idx_oidc_pending_expires
                ON oidc_pending(expires_at);
                """
            )
            self.connection.commit()

    def _prune_locked(self, now: int) -> None:
        self.connection.execute(
            "DELETE FROM oidc_pending WHERE expires_at<=?",
            (now,),
        )
        self.connection.execute(
            "DELETE FROM oidc_sessions WHERE expires_at<=?",
            (now,),
        )


class OidcSessionIdentityProvider(IdentityProvider):
    def __init__(self, store: OidcSessionStore) -> None:
        self.store = store

    async def authenticate(self, request: Request) -> Principal | None:
        session_id = request.cookies.get(SESSION_COOKIE)
        if not session_id:
            return None
        session = self.store.get_session(session_id)
        return session.principal if session else None


class GenericOidcClient:
    """Standards-based OIDC client with discovery, PKCE and JWT verification."""

    def __init__(
        self,
        *,
        issuer_url: str,
        client_id: str,
        client_secret: str,
        token_auth_method: str = "client_secret_post",
        timeout_seconds: float = 8.0,
    ) -> None:
        if token_auth_method not in {"client_secret_post", "client_secret_basic"}:
            raise ValueError("Unsupported OIDC token endpoint auth method")
        self.issuer_url = issuer_url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_auth_method = token_auth_method
        self.timeout_seconds = timeout_seconds
        self._discovery: dict[str, Any] | None = None
        self._jwks_client: jwt.PyJWKClient | None = None

    def authorization_start(
        self,
        *,
        redirect_uri: str,
        scopes: str,
    ) -> AuthorizationStart:
        discovery = self._get_discovery()
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        code_verifier = secrets.token_urlsafe(48)
        challenge = _pkce_challenge(code_verifier)

        query = urlencode(
            {
                "response_type": "code",
                "client_id": self.client_id,
                "redirect_uri": redirect_uri,
                "scope": scopes,
                "state": state,
                "nonce": nonce,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
        return AuthorizationStart(
            url=f"{discovery['authorization_endpoint']}?{query}",
            state=state,
            nonce=nonce,
            code_verifier=code_verifier,
        )

    def complete(
        self,
        *,
        code: str,
        redirect_uri: str,
        code_verifier: str,
        expected_nonce: str,
        tenant_claim: str,
        role_claim: str,
        allow_personal_tenant: bool,
    ) -> tuple[Principal, int]:
        discovery = self._get_discovery()
        token_endpoint = str(discovery["token_endpoint"])
        token_data: dict[str, str] = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
        }
        auth: tuple[str, str] | None = None
        if self.token_auth_method == "client_secret_post":
            token_data["client_id"] = self.client_id
            token_data["client_secret"] = self.client_secret
        else:
            auth = (self.client_id, self.client_secret)

        try:
            response = httpx.post(
                token_endpoint,
                data=token_data,
                auth=auth,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise OidcError("OIDC token exchange failed") from exc

        payload = response.json()
        id_token = payload.get("id_token")
        access_token = payload.get("access_token")
        if not isinstance(id_token, str) or not id_token:
            raise OidcError("OIDC provider did not return an ID token")
        if not isinstance(access_token, str) or not access_token:
            raise OidcError("OIDC provider did not return an access token")

        identity_claims = self._verify_id_token(
            id_token,
            discovery=discovery,
            expected_nonce=expected_nonce,
        )
        access_claims = self._verify_access_token(
            access_token,
            discovery=discovery,
        )

        subject = identity_claims.get("sub")
        access_subject = access_claims.get("sub")
        if not isinstance(subject, str) or not subject:
            raise OidcError("OIDC ID token has no valid subject")
        if access_subject != subject:
            raise OidcError("OIDC access token subject does not match ID token")

        tenant_value = access_claims.get(
            tenant_claim,
            identity_claims.get(tenant_claim),
        )
        if isinstance(tenant_value, str) and tenant_value:
            tenant_id = tenant_value
        elif allow_personal_tenant:
            tenant_id = f"personal:{subject}"
        else:
            raise OidcError("OIDC login is not associated with an organization")

        roles = _roles_from_claim(
            access_claims.get(
                role_claim,
                identity_claims.get(role_claim),
            )
        )
        identity_exp = identity_claims.get("exp")
        access_exp = access_claims.get("exp")
        if not isinstance(identity_exp, int) or not isinstance(access_exp, int):
            raise OidcError("OIDC tokens have no valid expiration")

        return (
            Principal(
                tenant_id=tenant_id,
                subject_id=subject,
                roles=roles,
                auth_method="oidc",
            ),
            min(identity_exp, access_exp),
        )

    def _get_discovery(self) -> dict[str, Any]:
        if self._discovery is not None:
            return self._discovery
        url = f"{self.issuer_url}/.well-known/openid-configuration"
        try:
            response = httpx.get(url, timeout=self.timeout_seconds)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise OidcError("OIDC discovery failed") from exc

        discovery = response.json()
        required = {
            "issuer",
            "authorization_endpoint",
            "token_endpoint",
            "jwks_uri",
        }
        if not required.issubset(discovery):
            raise OidcError("OIDC discovery metadata is incomplete")
        if str(discovery["issuer"]).rstrip("/") != self.issuer_url:
            raise OidcError("OIDC discovery issuer mismatch")

        self._discovery = dict(discovery)
        return self._discovery

    def _verify_id_token(
        self,
        token: str,
        *,
        discovery: dict[str, Any],
        expected_nonce: str,
    ) -> dict[str, Any]:
        header = jwt.get_unverified_header(token)
        algorithm = header.get("alg")
        advertised = set(discovery.get("id_token_signing_alg_values_supported", []))
        allowed = _SAFE_ID_TOKEN_ALGS & advertised if advertised else _SAFE_ID_TOKEN_ALGS
        if algorithm not in allowed:
            raise OidcError("OIDC ID token uses an unsupported signing algorithm")

        if self._jwks_client is None:
            self._jwks_client = jwt.PyJWKClient(
                str(discovery["jwks_uri"]),
                cache_keys=True,
                lifespan=300,
            )
        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=[str(algorithm)],
                audience=self.client_id,
                issuer=str(discovery["issuer"]),
                options={
                    "require": ["exp", "iat", "iss", "aud", "sub", "nonce"],
                },
            )
        except jwt.PyJWTError as exc:
            raise OidcError("OIDC ID token validation failed") from exc

        nonce = claims.get("nonce")
        if not isinstance(nonce, str) or not hmac.compare_digest(
            nonce,
            expected_nonce,
        ):
            raise OidcError("OIDC nonce validation failed")

        authorized_party = claims.get("azp")
        if authorized_party is not None and authorized_party != self.client_id:
            raise OidcError("OIDC authorized-party claim does not match client")

        return dict(claims)

    def _verify_access_token(
        self,
        token: str,
        *,
        discovery: dict[str, Any],
    ) -> dict[str, Any]:
        return self._verify_signed_token(
            token,
            discovery=discovery,
            required_claims=["exp", "iat", "iss", "aud", "sub"],
        )

    def _verify_signed_token(
        self,
        token: str,
        *,
        discovery: dict[str, Any],
        required_claims: list[str],
    ) -> dict[str, Any]:
        header = jwt.get_unverified_header(token)
        algorithm = header.get("alg")
        advertised = set(discovery.get("id_token_signing_alg_values_supported", []))
        allowed = _SAFE_ID_TOKEN_ALGS & advertised if advertised else _SAFE_ID_TOKEN_ALGS
        if algorithm not in allowed:
            raise OidcError("OIDC token uses an unsupported signing algorithm")

        if self._jwks_client is None:
            self._jwks_client = jwt.PyJWKClient(
                str(discovery["jwks_uri"]),
                cache_keys=True,
                lifespan=300,
                timeout=self.timeout_seconds,
            )
        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=[str(algorithm)],
                audience=self.client_id,
                issuer=str(discovery["issuer"]),
                options={"require": required_claims},
            )
        except (jwt.PyJWTError, jwt.PyJWKClientError) as exc:
            raise OidcError("OIDC token validation failed") from exc
        return dict(claims)


def _pkce_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _roles_from_claim(value: Any) -> tuple[str, ...]:
    if isinstance(value, str) and value:
        return (value,)
    if isinstance(value, list):
        return tuple(
            role
            for role in value
            if isinstance(role, str) and role
        )
    return ()


def _safe_return_to(value: str) -> str:
    parsed = urlparse(value)
    if (
        parsed.scheme
        or parsed.netloc
        or not value.startswith("/")
        or value.startswith("//")
    ):
        return "/"
    return value
