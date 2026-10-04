"""Local development runner for the XRay web backend."""

from __future__ import annotations

import os
from pathlib import Path

import uvicorn

from .app import create_app
from .settings import WebSettings


def main() -> None:
    data_root = Path(os.environ.get("XRAY_DATA_ROOT", ".xray-web-data"))
    host = os.environ.get("XRAY_HOST", "127.0.0.1")
    port = int(os.environ.get("XRAY_PORT", "8080"))

    # Local-only by default. Public deployments require an authenticated front door.
    uvicorn.run(
        create_app(WebSettings(data_root=data_root)),
        host=host,
        port=port,
        log_level="info",
    )
