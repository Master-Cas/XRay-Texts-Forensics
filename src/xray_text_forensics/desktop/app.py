"""Native-window entrypoint for the desktop product."""

from __future__ import annotations

import importlib
from typing import Any

from .server import DesktopServer


def main() -> None:
    try:
        webview: Any = importlib.import_module("webview")
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Desktop UI dependency is not installed. "
            "Install XRay with the 'desktop' optional dependency."
        ) from exc

    server = DesktopServer()
    url = server.start()
    try:
        webview.create_window(
            "XRay Texts Forensics",
            url,
            width=1280,
            height=820,
            min_size=(900, 620),
        )
        webview.start()
    finally:
        server.stop()


if __name__ == "__main__":
    main()
