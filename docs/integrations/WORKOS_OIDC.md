# WorkOS AuthKit — XRay OIDC Integration

## Status

WorkOS AuthKit is XRay's initial managed identity provider.

XRay integrates through OIDC/OAuth standards rather than a WorkOS-specific authentication
SDK.

## WorkOS setup

Create a WorkOS environment and an OAuth Application intended for XRay.

Use the authorization-code flow.

For the Web product, configure the redirect URI as:

```text
https://<your-xray-domain>/auth/callback
```

Use the AuthKit domain as the OIDC issuer.

The issuer exposes standard discovery at:

```text
https://<authkit-domain>/.well-known/openid-configuration
```

## XRay environment

```bash
XRAY_ENV=production
XRAY_IDENTITY_MODE=oidc

XRAY_PUBLIC_BASE_URL=https://xray.example.com
XRAY_OIDC_ISSUER_URL=https://your-domain.authkit.app
XRAY_OIDC_CLIENT_ID=<workos-oauth-application-client-id>
XRAY_OIDC_CLIENT_SECRET=<workos-oauth-application-client-secret>

# Configure this if the WorkOS access-token aud differs from the OAuth app client ID.
XRAY_OIDC_ACCESS_TOKEN_AUDIENCE=<expected-access-token-audience>

XRAY_OIDC_SCOPES="openid profile email"
XRAY_OIDC_TENANT_CLAIM=org_id
XRAY_OIDC_TOKEN_AUTH_METHOD=client_secret_post
```

Never commit the client secret.

Use your deployment platform's secret manager for:

```text
XRAY_OIDC_CLIENT_SECRET
```

## Access-token audience

XRay validates the ID token against `XRAY_OIDC_CLIENT_ID`.

The access token has an independent audience check. WorkOS Connect documents that the
access-token `aud` is the requested resource indicator, or the environment client ID when
no resource is requested.

Set:

```bash
XRAY_OIDC_ACCESS_TOKEN_AUDIENCE=<expected aud>
```

If omitted, XRay conservatively expects the OAuth client ID. A mismatched audience fails
closed.

## Organization mapping

WorkOS Connect access tokens can contain the organization selected during authorization as:

```json
{
  "sub": "user_...",
  "org_id": "org_..."
}
```

XRay maps:

```text
org_id -> Principal.tenant_id
sub    -> Principal.subject_id
```

That tenant ID then enters the M15 tenant-storage resolver.

## Roles

WorkOS Connect access tokens do not need to include role information for M16 because M16
does not enforce fine-grained RBAC.

If role slugs are added to WorkOS tokens through a JWT template, configure the matching
claim, for example:

```bash
XRAY_OIDC_ROLE_CLAIM=roles
```

XRay accepts either a single string role or a list of role strings.

## Personal workspaces

By default, a user without `org_id` receives:

```text
personal:<sub>
```

For a strictly B2B deployment:

```bash
XRAY_OIDC_ALLOW_PERSONAL_TENANT=false
```

A login without organization context will then be rejected.

## WorkOS token exchange

The initial WorkOS integration uses:

```text
XRAY_OIDC_TOKEN_AUTH_METHOD=client_secret_post
```

XRay still sends PKCE S256 even though the Web app is a confidential client.

## Production HTTPS

XRay refuses to start OIDC mode in production unless:

- `XRAY_PUBLIC_BASE_URL` uses HTTPS;
- `XRAY_OIDC_ISSUER_URL` uses HTTPS.

Local/fake-provider tests may use HTTP outside production.

## Current session boundary

M16 validates both WorkOS ID and access tokens at login and then creates an opaque XRay
session.

Refresh tokens are deliberately not persisted yet.

Consequently, XRay session lifetime cannot exceed the validated provider token lifetime.

A later milestone will add refresh-token rotation and provider-session revocation using
encrypted server-side secret storage.

## What not to put in Git

Never commit:

- WorkOS client secret;
- WorkOS API keys;
- production refresh tokens;
- private signing material;
- copied production JWTs.

Only non-secret identifiers and documentation belong in the repository.
