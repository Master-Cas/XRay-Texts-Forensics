from __future__ import annotations

import http.cookiejar
import urllib.error
import urllib.request

from fastapi.testclient import TestClient

from xray_text_forensics.desktop import DesktopServer
from xray_text_forensics.web import WebSettings, create_app


def test_desktop_mode_requires_session_token_for_private_routes(tmp_path) -> None:
    token = "x" * 43
    app = create_app(
        WebSettings(
            data_root=tmp_path / "data",
            environment="production",
            docs_enabled=False,
            request_logging=False,
            desktop_access_token=token,
        )
    )

    with TestClient(app) as client:
        assert client.get("/api/v1/health").status_code == 200
        assert client.get("/static/app.js").status_code == 200
        assert client.get("/").status_code == 403
        assert client.get("/api/v1/cases/case_missing").status_code == 403

        launched = client.get("/", params={"desktop_token": token})
        assert launched.status_code == 200
        set_cookie = launched.headers["set-cookie"].lower()
        assert "httponly" in set_cookie
        assert "samesite=strict" in set_cookie

        # TestClient keeps the launch cookie. Authorization succeeds, then the domain
        # route itself reports that this particular case does not exist.
        assert client.get("/api/v1/cases/case_missing").status_code == 404


def test_wrong_desktop_launch_token_is_rejected(tmp_path) -> None:
    token = "a" * 43
    app = create_app(
        WebSettings(
            data_root=tmp_path / "data",
            environment="production",
            docs_enabled=False,
            request_logging=False,
            desktop_access_token=token,
        )
    )

    with TestClient(app) as client:
        response = client.get("/", params={"desktop_token": "b" * 43})
    assert response.status_code == 403


def test_desktop_server_starts_on_ephemeral_loopback_and_stops(tmp_path) -> None:
    server = DesktopServer(data_root=tmp_path / "desktop-data", startup_timeout=10)
    launch_url = server.start()

    try:
        assert server.origin.startswith("http://127.0.0.1:")
        assert "desktop_token=" in launch_url
        assert server.token in launch_url

        with urllib.request.urlopen(
            f"{server.origin}/api/v1/health",
            timeout=2,
        ) as response:
            assert response.status == 200

        with pytest_http_error(403):
            urllib.request.urlopen(server.origin + "/", timeout=2)

        cookies = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(cookies)
        )
        with opener.open(launch_url, timeout=2) as response:
            assert response.status == 200

        try:
            opener.open(
                f"{server.origin}/api/v1/cases/case_missing",
                timeout=2,
            )
        except urllib.error.HTTPError as exc:
            # 404 proves desktop authorization succeeded; without the cookie it is 403.
            assert exc.code == 404
        else:
            raise AssertionError("missing case should return HTTP 404")
    finally:
        server.stop()

    try:
        _ = server.port
    except RuntimeError:
        pass
    else:
        raise AssertionError("stopped desktop server must not expose a port")


class pytest_http_error:
    def __init__(self, status: int) -> None:
        self.status = status

    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type, exc, tb) -> bool:
        if not isinstance(exc, urllib.error.HTTPError):
            return False
        if exc.code != self.status:
            return False
        return True
