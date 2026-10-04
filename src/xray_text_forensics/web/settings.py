"""Configuration for the XRay web service."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, Field

EnvironmentName = Literal["development", "test", "production"]
IdentityMode = Literal["local", "gateway", "oidc"]


class WebSettings(BaseModel):
    data_root: Path = Path(".xray-web-data")
    max_upload_bytes: int = Field(default=25 * 1024 * 1024, ge=1024)
    docs_enabled: bool = True
    environment: EnvironmentName = "development"
    max_job_workers: int = Field(default=2, ge=1, le=32)
    max_pending_jobs: int = Field(default=8, ge=1, le=1000)
    request_logging: bool = True
    bind_host: str = "127.0.0.1"
    bind_port: int = Field(default=8080, ge=1, le=65535)
    desktop_access_token: str | None = None
    identity_mode: IdentityMode = "local"
    gateway_shared_secret: str | None = None
    public_base_url: str | None = None
    oidc_issuer_url: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: str | None = None
    oidc_scopes: str = "openid profile email"
    oidc_tenant_claim: str = "org_id"
    oidc_role_claim: str = "role"
    oidc_session_ttl_seconds: int = Field(default=8 * 60 * 60, ge=300, le=7 * 24 * 60 * 60)
    oidc_allow_personal_tenant: bool = True

    @property
    def object_store_root(self) -> Path:
        return self.data_root / "objects"

    @property
    def case_database(self) -> Path:
        return self.data_root / "cases.sqlite"

    @classmethod
    def from_environment(cls) -> WebSettings:
        environment = os.environ.get("XRAY_ENV", "development").strip().casefold()
        if environment not in {"development", "test", "production"}:
            raise ValueError("XRAY_ENV must be development, test, or production")

        environment_name = cast(EnvironmentName, environment)
        identity_mode = os.environ.get("XRAY_IDENTITY_MODE", "local").strip().casefold()
        if identity_mode not in {"local", "gateway", "oidc"}:
            raise ValueError("XRAY_IDENTITY_MODE must be local, gateway, or oidc")
        identity_mode_name = cast(IdentityMode, identity_mode)

        docs_default = environment_name != "production"
        return cls(
            data_root=Path(os.environ.get("XRAY_DATA_ROOT", ".xray-web-data")),
            max_upload_bytes=_env_int(
                "XRAY_MAX_UPLOAD_BYTES",
                25 * 1024 * 1024,
            ),
            docs_enabled=_env_bool("XRAY_DOCS_ENABLED", docs_default),
            environment=environment_name,
            max_job_workers=_env_int("XRAY_MAX_JOB_WORKERS", 2),
            max_pending_jobs=_env_int("XRAY_MAX_PENDING_JOBS", 8),
            request_logging=_env_bool("XRAY_REQUEST_LOGGING", True),
            bind_host=os.environ.get("XRAY_HOST", "127.0.0.1"),
            bind_port=_env_int("XRAY_PORT", 8080),
            desktop_access_token=os.environ.get("XRAY_DESKTOP_ACCESS_TOKEN"),
            identity_mode=identity_mode_name,
            gateway_shared_secret=os.environ.get("XRAY_GATEWAY_SHARED_SECRET"),
            public_base_url=os.environ.get("XRAY_PUBLIC_BASE_URL"),
            oidc_issuer_url=os.environ.get("XRAY_OIDC_ISSUER_URL"),
            oidc_client_id=os.environ.get("XRAY_OIDC_CLIENT_ID"),
            oidc_client_secret=os.environ.get("XRAY_OIDC_CLIENT_SECRET"),
            oidc_scopes=os.environ.get("XRAY_OIDC_SCOPES", "openid profile email"),
            oidc_tenant_claim=os.environ.get("XRAY_OIDC_TENANT_CLAIM", "org_id"),
            oidc_role_claim=os.environ.get("XRAY_OIDC_ROLE_CLAIM", "role"),
            oidc_session_ttl_seconds=_env_int(
                "XRAY_OIDC_SESSION_TTL_SECONDS",
                8 * 60 * 60,
            ),
            oidc_allow_personal_tenant=_env_bool(
                "XRAY_OIDC_ALLOW_PERSONAL_TENANT",
                True,
            ),
        )


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    normalized = raw.strip().casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")
