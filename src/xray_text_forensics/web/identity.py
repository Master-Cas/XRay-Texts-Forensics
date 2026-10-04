"""Provider-agnostic identity boundary for Web and Desktop deployments."""

from __future__ import annotations

import hmac
import re
from typing import Protocol, TypeGuard

from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class Principal(BaseModel):
    tenant_id: str
    subject_id: str
    roles: tuple[str, ...] = Field(default_factory=tuple)
    auth_method: str


class IdentityProvider(Protocol):
    async def authenticate(self, request: Request) -> Principal | None: ...


class LocalIdentityProvider:
    """Single-user identity used by local Web development and Desktop."""

    async def authenticate(self, request: Request) -> Principal:
        del request
        return Principal(
            tenant_id="local",
            subject_id="local-user",
            roles=("owner",),
            auth_method="local",
        )


class GatewayIdentityProvider:
    """Trust identity headers only when an upstream gateway proves possession of a secret.

    A browser must never receive this shared secret. The trusted reverse proxy/gateway strips
    any client-supplied X-XRay-* identity headers and injects its own after user authentication.
    """

    def __init__(self, *, shared_secret: str) -> None:
        if len(shared_secret) < 32:
            raise ValueError("XRAY gateway shared secret must be at least 32 characters")
        self.shared_secret = shared_secret

    async def authenticate(self, request: Request) -> Principal | None:
        supplied_secret = request.headers.get("x-xray-gateway-secret")
        if supplied_secret is None or not hmac.compare_digest(
            supplied_secret,
            self.shared_secret,
        ):
            return None

        tenant_id = request.headers.get("x-xray-tenant")
        subject_id = request.headers.get("x-xray-subject")
        if not _valid_id(tenant_id) or not _valid_id(subject_id):
            return None

        roles = _parse_roles(request.headers.get("x-xray-roles"))
        return Principal(
            tenant_id=tenant_id,
            subject_id=subject_id,
            roles=roles,
            auth_method="gateway",
        )


class IdentityBoundaryMiddleware(BaseHTTPMiddleware):
    """Authenticate private API calls and attach the principal to request.state."""

    def __init__(self, app: ASGIApp, *, provider: IdentityProvider) -> None:
        super().__init__(app)
        self.provider = provider

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        path = request.url.path
        if not path.startswith("/api/v1/") or path in {
            "/api/v1/health",
            "/api/v1/ready",
        }:
            return await call_next(request)

        principal = await self.provider.authenticate(request)
        if principal is None:
            return JSONResponse(
                status_code=401,
                content={"detail": "Authentication required"},
                headers={"WWW-Authenticate": "XRay-Gateway"},
            )

        request.state.xray_principal = principal
        return await call_next(request)


def principal_from_request(request: Request) -> Principal:
    principal = getattr(request.state, "xray_principal", None)
    if not isinstance(principal, Principal):
        raise RuntimeError("Authenticated principal is missing from request state")
    return principal


def _valid_id(value: str | None) -> TypeGuard[str]:
    return value is not None and _ID_RE.fullmatch(value) is not None


def _parse_roles(raw: str | None) -> tuple[str, ...]:
    if raw is None:
        return ()
    roles = []
    for candidate in raw.split(","):
        role = candidate.strip()
        if _valid_id(role) and role not in roles:
            roles.append(role)
    return tuple(roles)
