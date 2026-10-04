"""Configuration for the single-node web backend."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class WebSettings(BaseModel):
    data_root: Path = Path(".xray-web-data")
    max_upload_bytes: int = Field(default=25 * 1024 * 1024, ge=1024)
    docs_enabled: bool = True

    @property
    def object_store_root(self) -> Path:
        return self.data_root / "objects"

    @property
    def case_database(self) -> Path:
        return self.data_root / "cases.sqlite"
