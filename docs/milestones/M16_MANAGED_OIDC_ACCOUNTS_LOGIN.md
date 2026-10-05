# M16 — Managed OIDC Accounts & Login

## Objective

Add real managed-account login to the Web product while keeping XRay's forensic engine,
tenant model, and authorization boundary independent of any one identity vendor.

Initial provider: **WorkOS AuthKit**.

Integration contract: **standard OIDC Authorization Code + PKCE**.

## Why WorkOS first

WorkOS is the initial managed provider because it exposes standard OpenID Connect discovery,
JWKS, authorization-code flows, organizations, SSO, MFA/passkeys, and organization-aware
tokens.

XRay does not import a WorkOS SDK into the forensic Core.

The provider-specific surface is configuration only.

## Browser security model

XRay uses a backend-for-frontend session model.

The browser receives:

- an opaque random session cookie;
- HttpOnly;
- SameSite=Lax;
- Secure in production.

The browser does **not** receive or persist:

- OIDC client secrets;
- refresh tokens;
- ID tokens;
- access tokens.

No OIDC token is written to Local Storage or browser JavaScript.

## Authorization flow

```text
GET /auth/login
        |
        | state + nonce + PKCE S256
        v
Managed OIDC provider
        |
        | authorization code
        v
GET /auth/callback
        |
        +--> state cookie validation
        +--> one-time state consumption
        +--> code exchange
        +--> ID token verification
        +--> access token verification
        +--> Principal creation
        +--> opaque server-side session
        |
        v
303 back to XRay
```

## OIDC verification

XRay verifies:

- discovery issuer;
- signature against provider JWKS;
- permitted signing algorithm;
- issuer;
- ID-token audience;
- independently configured access-token audience;
- subject;
- expiration;
- issued-at;
- nonce on the ID token;
- optional authorized-party claim.

The access token and ID token subjects must match.

## Identity vs authorization claims

The ID token establishes identity and protects the authentication flow through the nonce.

The access token supplies tenant/authorization context.

Default claim mapping:

```text
subject       = sub
tenant        = org_id
role          = role
```

All tenant/role claim names are configurable.

For WorkOS Connect, `org_id` is sourced from the validated access token.

If no organization is present and personal workspaces are enabled, XRay derives:

```text
personal:<sub>
```

Set `XRAY_OIDC_ALLOW_PERSONAL_TENANT=false` to require organization membership.

## Opaque session store

OIDC transient state and browser sessions are stored in:

```text
<data_root>/auth.sqlite
```

SQLite operates in WAL mode.

Stored browser session data contains:

- random session ID;
- resolved XRay tenant ID;
- resolved subject ID;
- role slugs;
- auth method;
- expiry.

Provider tokens are not persisted in M16.

## State and PKCE

Each login creates:

- 256-bit-class random state;
- random nonce;
- high-entropy PKCE verifier;
- S256 code challenge.

Pending authorization state is:

- server-side;
- time-limited;
- one-time;
- also bound to an HttpOnly SameSite state cookie.

A callback state mismatch fails closed.

## Open redirect protection

`return_to` accepts only local absolute-path references such as:

```text
/
 /cases
```

External URLs, scheme-relative URLs and absolute third-party URLs collapse to `/`.

## Routes

Public authentication routes:

- `GET /auth/login`
- `GET /auth/callback`
- `GET /auth/logout`

Authenticated API identity:

- `GET /api/v1/session`

Existing private API routes continue to be protected by the identity boundary.

## Configuration

Required in OIDC mode:

```text
XRAY_IDENTITY_MODE=oidc
XRAY_PUBLIC_BASE_URL=https://xray.example.com
XRAY_OIDC_ISSUER_URL=https://<issuer>
XRAY_OIDC_CLIENT_ID=<client-id>
```

Confidential clients additionally require:

```text
XRAY_OIDC_CLIENT_SECRET=<secret>
XRAY_OIDC_TOKEN_AUTH_METHOD=client_secret_post
```

Public clients use PKCE without a client secret:

```text
XRAY_OIDC_TOKEN_AUTH_METHOD=none
```

Provider-dependent access-token audience:

```text
XRAY_OIDC_ACCESS_TOKEN_AUDIENCE=<expected aud>
```

If omitted, it defaults to the OIDC client ID.

Optional:

```text
XRAY_OIDC_SCOPES=openid profile email
XRAY_OIDC_TENANT_CLAIM=org_id
XRAY_OIDC_ROLE_CLAIM=role
XRAY_OIDC_SESSION_TTL_SECONDS=28800
XRAY_OIDC_ALLOW_PERSONAL_TENANT=true
XRAY_OIDC_TOKEN_AUTH_METHOD=client_secret_post
```

Production requires HTTPS for both public base URL and issuer.

## Token endpoint authentication

Supported:

- `client_secret_post`
- `client_secret_basic`
- `none` for public PKCE clients

The default remains `client_secret_post` for backward compatibility. The production
XTF WorkOS Connect application is a public PKCE client and therefore uses `none`.

## Session lifetime

M16 does not persist provider refresh tokens.

The XRay browser session is capped to the earliest of:

- validated provider token expiry;
- configured XRay session TTL.

This is deliberately conservative.

Refresh-token rotation and seamless long-lived session renewal are deferred to the next
session-resilience milestone rather than storing sensitive refresh credentials prematurely.

## Readiness

When OIDC mode is enabled, `/api/v1/ready` additionally verifies:

- OIDC session DB exists and is usable;
- auth DB journal mode is WAL.

It does not make the application's readiness depend on a live provider network request.

## UI

The Web UI now displays:

- authenticated subject;
- active tenant;
- Sign in when unauthenticated;
- Sign out for OIDC sessions.

Desktop/local sessions do not show an unnecessary logout action.

## Explicit non-goals

M16 does not yet add:

- refresh-token rotation;
- provider session revocation on logout;
- organization switching without re-authentication;
- invitation/admin UI;
- fine-grained RBAC enforcement;
- billing/subscriptions;
- customer API keys.

## Gate

M16 is accepted when:

- incomplete OIDC configuration fails closed;
- production OIDC rejects non-HTTPS URLs;
- Authorization Code + PKCE is generated correctly;
- state and nonce validation work;
- state is one-time;
- external return URLs are rejected;
- ID token signature/issuer/audience/nonce validation works;
- access token signature/issuer/audience validation works;
- ID/access token subjects must match;
- tenant context can come from `org_id` access-token claim;
- personal-workspace fallback is controlled;
- opaque session cookie contains no provider credential;
- logout invalidates the XRay session;
- OIDC auth DB participates in readiness;
- full pytest/Ruff/mypy pass;
- Windows CI still builds and installs the desktop product.
