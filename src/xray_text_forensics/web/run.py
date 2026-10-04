"""Web service runner for XRay."""

from __future__ import annotations

import logging

import uvicorn

from .app import create_app
from .settings import WebSettings


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = WebSettings.from_environment()

    # Local-only by default. A public production deployment still needs an authenticated
    # reverse proxy/service boundary before exposing this process to the Internet.
    uvicorn.run(
        create_app(settings),
        host=settings.bind_host,
        port=settings.bind_port,
        log_level="info",
    )
