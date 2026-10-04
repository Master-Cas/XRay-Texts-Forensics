"""Loopback server lifecycle for packaged desktop builds."""

from __future__ import annotations

import contextlib
import os
import secrets
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlencode

import uvicorn

from xray_text_forensics.web import WebSettings, create_app


def default_desktop_data_root() -> Path:
    if os.name == "nt":
        base = Path(
            os.environ.get(
                "LOCALAPPDATA",
                str(Path.home() / "AppData" / "Local"),
            )
        )
        return base / "XRay Texts Forensics"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "XRay Texts Forensics"
    data_home = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
    return data_home / "xray-texts-forensics"


class DesktopServer:
    def __init__(
        self,
        *,
        data_root: Path | None = None,
        startup_timeout: float = 15.0,
    ) -> None:
        self.data_root = data_root or default_desktop_data_root()
        self.startup_timeout = startup_timeout
        self.token = secrets.token_urlsafe(32)
        self._socket: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._server: uvicorn.Server | None = None
        self._port: int | None = None

    @property
    def port(self) -> int:
        if self._port is None:
            raise RuntimeError("Desktop server has not started")
        return self._port

    @property
    def origin(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def launch_url(self) -> str:
        return f"{self.origin}/?{urlencode({'desktop_token': self.token})}"

    def start(self) -> str:
        if self._thread is not None:
            raise RuntimeError("Desktop server is already started")

        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        self._socket = listener
        self._port = int(listener.getsockname()[1])

        settings = WebSettings(
            data_root=self.data_root,
            docs_enabled=False,
            environment="production",
            request_logging=False,
            bind_host="127.0.0.1",
            bind_port=self.port,
            desktop_access_token=self.token,
        )
        config = uvicorn.Config(
            create_app(settings),
            host="127.0.0.1",
            port=self.port,
            log_level="warning",
            access_log=False,
        )
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(
            target=self._run_server,
            name="xray-desktop-server",
            daemon=True,
        )
        self._thread.start()

        deadline = time.monotonic() + self.startup_timeout
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(
                    f"{self.origin}/api/v1/health",
                    timeout=0.5,
                ) as response:
                    if response.status == 200:
                        return self.launch_url
            except (urllib.error.URLError, TimeoutError):
                time.sleep(0.05)

        self.stop()
        raise TimeoutError("XRay desktop server did not become healthy in time")

    def stop(self) -> None:
        server = self._server
        thread = self._thread
        listener = self._socket

        if server is not None:
            server.should_exit = True
        if thread is not None:
            thread.join(timeout=5)
        if listener is not None:
            with contextlib.suppress(OSError):
                listener.close()

        self._server = None
        self._thread = None
        self._socket = None
        self._port = None

    def _run_server(self) -> None:
        assert self._server is not None
        assert self._socket is not None
        self._server.run(sockets=[self._socket])
