"""Loopback access control used by the packaged desktop application."""

from __future__ import annotations

import hmac

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

_DESKTOP_COOKIE = "xray_desktop_access"


class DesktopAccessMiddleware(BaseHTTPMiddleware):
    """Require an ephemeral token for desktop UI/API access."""

    def __init__(self, app: ASGIApp, *, token: str) -> None:
        super().__init__(app)
        if len(token) < 32:
            raise ValueError("desktop access token is too short")
        self.token = token

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        path = request.url.path
        if path.startswith("/static/") or path in {
            "/api/v1/health",
            "/api/v1/ready",
        }:
            return await call_next(request)

        cookie_ok = _matches(request.cookies.get(_DESKTOP_COOKIE), self.token)
        launch_token = request.query_params.get("desktop_token")
        launch_ok = path == "/" and _matches(launch_token, self.token)

        if not cookie_ok and not launch_ok:
            if path.startswith("/api/"):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Desktop session authorization required"},
                )
            return Response("Forbidden", status_code=403, media_type="text/plain")

        response = await call_next(request)
        if launch_ok:
            response.set_cookie(
                _DESKTOP_COOKIE,
                self.token,
                httponly=True,
                secure=False,
                samesite="strict",
                path="/",
            )
            response.headers["Cache-Control"] = "no-store"
        return response


def _matches(candidate: str | None, expected: str) -> bool:
    return candidate is not None and hmac.compare_digest(candidate, expected)
