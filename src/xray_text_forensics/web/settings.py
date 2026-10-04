"""Configuration for the XRay web service."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

EnvironmentName = Literal["development", "test", "production"]


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

        docs_default = environment != "production"
        return cls(
            data_root=Path(os.environ.get("XRAY_DATA_ROOT", ".xray-web-data")),
            max_upload_bytes=_env_int(
                "XRAY_MAX_UPLOAD_BYTES",
                25 * 1024 * 1024,
            ),
            docs_enabled=_env_bool("XRAY_DOCS_ENABLED", docs_default),
            environment=environment,
            max_job_workers=_env_int("XRAY_MAX_JOB_WORKERS", 2),
            max_pending_jobs=_env_int("XRAY_MAX_PENDING_JOBS", 8),
            request_logging=_env_bool("XRAY_REQUEST_LOGGING", True),
            bind_host=os.environ.get("XRAY_HOST", "127.0.0.1"),
            bind_port=_env_int("XRAY_PORT", 8080),
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
