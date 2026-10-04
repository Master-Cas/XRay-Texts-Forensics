"""HTTP request correlation and structured access logs."""

from __future__ import annotations

import json
import logging
import re
import time
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_ACCESS_LOGGER = logging.getLogger("xray.web.access")


class RequestContextMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: object, *, enabled: bool = True) -> None:
        super().__init__(app)
        self.enabled = enabled

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        request_id = _request_id(request.headers.get("x-request-id"))
        request.state.request_id = request_id
        started = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - started) * 1000.0
            if self.enabled:
                _log_access(
                    request_id=request_id,
                    method=request.method,
                    path=request.url.path,
                    status_code=500,
                    duration_ms=duration_ms,
                )
            raise

        response.headers["X-Request-ID"] = request_id
        if self.enabled:
            _log_access(
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=(time.perf_counter() - started) * 1000.0,
            )
        return response


def _request_id(candidate: str | None) -> str:
    if candidate and _REQUEST_ID_RE.fullmatch(candidate):
        return candidate
    return f"req_{uuid4().hex}"


def _log_access(
    *,
    request_id: str,
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
) -> None:
    payload = {
        "event": "http_request",
        "request_id": request_id,
        "method": method,
        "path": path,
        "status_code": status_code,
        "duration_ms": round(duration_ms, 3),
    }
    _ACCESS_LOGGER.info(json.dumps(payload, separators=(",", ":"), sort_keys=True))
