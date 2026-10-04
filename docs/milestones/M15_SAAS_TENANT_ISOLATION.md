# M15 — SaaS Tenant Isolation & Identity Boundary

## Objective

Prepare the Web product for multi-tenant SaaS without committing the Core to a specific
identity vendor.

M15 introduces a provider-agnostic identity contract and physically isolates forensic
storage by authenticated tenant.

It does **not** yet implement end-user login UX, billing, or RBAC policy.

## Identity modes

### local

Used by:

- Desktop;
- local development;
- current single-user Web workflows.

Principal:

```text
tenant_id  = local
subject_id = local-user
role       = owner
```

The existing local storage layout remains unchanged for backward compatibility:

```text
<data_root>/objects
<data_root>/cases.sqlite
```

### gateway

Used as the first SaaS identity boundary.

A trusted upstream identity gateway authenticates the user, strips any incoming client
`X-XRay-*` identity headers, and injects verified values:

- `X-XRay-Gateway-Secret`
- `X-XRay-Tenant`
- `X-XRay-Subject`
- optional `X-XRay-Roles`

The browser must never know the gateway shared secret.

The backend verifies the secret using constant-time comparison and rejects malformed tenant
or subject identifiers.

## Fail-closed configuration

`XRAY_IDENTITY_MODE=gateway` requires:

`XRAY_GATEWAY_SHARED_SECRET`

The secret must be at least 32 characters.

If the secret is absent or too short, application startup fails.

There is no anonymous fallback in gateway mode.

## Public operational endpoints

These remain unauthenticated so health infrastructure can supervise the process:

- `GET /api/v1/health`
- `GET /api/v1/ready`

Private `/api/v1/*` routes require an authenticated principal.

`GET /api/v1/session` exposes the current verified principal to the product UI.

## Tenant storage model

Authenticated tenant identifiers are never interpolated directly into filesystem paths.

For non-local tenants:

```text
digest = SHA256(tenant_id)
tenant_root = <data_root>/tenants/<first-32-hex>
```

Tenant root contains:

```text
objects/
cases.sqlite
```

This creates physical isolation for:

- immutable artifact bytes;
- derived views;
- cases;
- detector runs;
- evidence;
- reports derived from cases.

The raw tenant identifier does not become a path component.

## Case isolation

A case created by tenant A exists only in tenant A's SQLite database.

A request from tenant B using tenant A's `case_id` receives 404.

Subjects within the same tenant can access the same case in M15. Fine-grained roles and
permissions are a later authorization milestone.

## Job isolation

Background jobs now record an internal owner tenant.

`GET /api/v1/jobs/{job_id}` returns the job only when the requesting tenant matches the
owner tenant.

Cross-tenant access returns 404.

The tenant owner field is internal and is not added to the public `JobResponse`.

## Provider abstraction

The Web application depends on an `IdentityProvider` protocol rather than a named vendor.

Current providers:

- `LocalIdentityProvider`
- `GatewayIdentityProvider`

A later OIDC/JWT/provider-specific adapter can implement the same contract without changing
the forensic Core or tenant storage model.

## Security assumptions for gateway mode

Gateway mode is safe only when deployed behind a trusted boundary that:

1. terminates or preserves authenticated TLS;
2. removes client-supplied XRay identity headers;
3. authenticates the end user;
4. injects verified tenant/subject headers;
5. injects the shared gateway secret server-side;
6. prevents clients from reaching the backend directly.

The shared secret is infrastructure-to-infrastructure material, not an end-user credential.

## Explicit non-goals

M15 does not yet add:

- login/sign-up pages;
- OAuth/OIDC provider selection;
- password storage;
- social login;
- invitations;
- role enforcement;
- organization administration UI;
- billing/subscriptions;
- API keys for customers;
- durable multi-node job queues.

## Gate

M15 is accepted when:

- local Desktop/Web behavior remains backward compatible;
- gateway mode without a valid secret fails closed;
- health/readiness remain public;
- private API without identity returns 401;
- malformed or wrongly authenticated identity returns 401;
- session endpoint returns only the verified principal;
- tenant case isolation returns 404 across tenants;
- object storage roots differ per tenant;
- raw tenant IDs are absent from tenant paths;
- identical artifact bytes can exist independently in two tenant stores;
- background jobs cannot cross tenant boundaries;
- full pytest/Ruff/mypy pass;
- real Uvicorn gateway smoke test passes.
