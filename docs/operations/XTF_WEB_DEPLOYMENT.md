# XTF Web Production Deployment

This runbook describes the production release contract for the public XTF Web service at
`https://xtf.technolution.cl`.

## Production topology

The production host is `51.161.113.154` and the deployment is intentionally split into
an XTF application stack and a separate Caddy reverse-proxy stack.

XTF uses these paths:

- active release symlink: `/opt/xtf/current`
- immutable releases: `/opt/xtf/releases/<SHA>`
- base Compose file: `/opt/xtf/deploy/compose.yaml`
- runtime release override: `/opt/xtf/deploy/compose.release.yaml`
- environment file: `/opt/xtf/deploy/xtf.env`
- persistent application data: `/var/lib/xtf`
- global reference library: `/opt/xtf/reference-data/library`, mounted read-only
- deployment backups: `/opt/xtf/backups/<UTC timestamp>`

Caddy is not part of the XTF Compose project. Normal XTF releases do **not** restart,
reload, or modify Caddy, DNS, TLS, or OIDC configuration.

The XTF service is expected to be reachable by Caddy as `xtf:8080`.

## Release identity

Production releases expose the deployed Git commit through `XRAY_BUILD_SHA`.

- the value must be exactly 40 lowercase hexadecimal characters;
- `/api/v1/health` exposes it as `build_sha`;
- `/api/v1/ready` exposes the same field;
- local development remains valid when `XRAY_BUILD_SHA` is absent, in which case
  `build_sha` is `null`;
- invalid configured values fail application configuration validation.

The deployment script injects the requested SHA into the XTF container using a Compose
runtime override. It does not edit `xtf.env`.

## Normal deployment

Run from an authenticated checkout of this repository:

```bash
scripts/deploy_xtf_web.sh <40-hex-main-sha>
```

The requested SHA must exactly match the current `origin/main` SHA both on the operator
checkout and again on the VPS. This double check prevents deploying a stale SHA if main
moves between preparation and cutover.

The script then:

1. acquires `/opt/xtf/deploy/.deploy.lock` so only one release can run at a time;
2. prepares `/opt/xtf/releases/<SHA>` as a clean detached checkout;
3. builds `xtf:<SHA>` using `/opt/xtf/deploy/Dockerfile`;
4. runs an image smoke test with `XRAY_BUILD_SHA=<SHA>`;
5. records the previous symlink, image, base Compose file, and any prior runtime override;
6. stops **only** the XTF container;
7. creates a consistent tar backup of `/var/lib/xtf`;
8. writes the runtime override containing the exact image tag and `XRAY_BUILD_SHA`;
9. updates `/opt/xtf/current`;
10. recreates only the XTF service with `docker compose ... up -d --no-deps xtf`;
11. waits for Docker health to become healthy;
12. verifies public `/api/v1/health` and `/api/v1/ready` through
    `https://xtf.technolution.cl`, requiring the expected status and exact
    `build_sha`.

The global reference library and application data remain separate bind mounts and are
not copied into the image.

## Dry run

Use dry-run before a production release:

```bash
scripts/deploy_xtf_web.sh --dry-run <40-hex-main-sha>
```

Dry-run validates the SHA and verifies it against `origin/main`, then prints the
production plan. It exits **before opening any SSH connection**, so it does not touch the
VPS.

## Automatic rollback

After XTF has been stopped for the consistent backup, any failing command activates the
rollback handler.

Rollback restores:

- the previous `/opt/xtf/current` target;
- the previous `compose.release.yaml`, or removes it if none existed;
- the previous XTF container definition/image by running Compose for the XTF service only.

The rollback waits for the restored XTF container to become healthy. Caddy is not
restarted.

The data backup is retained for disaster recovery but is **not automatically restored**
during a normal application rollback. Automatic restoration of the database/data tree
could erase writes made after cutover; restoring `xtf-data.tgz` is therefore a separate,
explicit recovery operation.

## Secrets policy

The deployment script must never print or copy secret values.

In particular:

- `/opt/xtf/deploy/xtf.env` is required but never rewritten or printed;
- OIDC client secrets, tokens, cookies, private keys, and passwords are not logged;
- container environment dumps are not part of the procedure;
- backups created by the script contain application data and deployment metadata, not a
  duplicate of `xtf.env`;
- logs contain release SHA, image tag, paths, health state, and backup location only.

## Idempotency

If the requested SHA is already the active symlink, the running container uses
`xtf:<SHA>`, Docker reports it healthy, and both public health endpoints report the same
`build_sha`, the script exits successfully without rebuilding, backing up, or restarting
the service.

If the SHA matches but the build identity is missing or the service is unhealthy, the
script performs a normal safe redeploy.

## Manual verification after release

A successful release should be followed by these non-secret checks:

```bash
curl -fsS https://xtf.technolution.cl/api/v1/health
curl -fsS https://xtf.technolution.cl/api/v1/ready
```

Both payloads must report the deployed 40-character SHA. The authenticated UI should
also be smoke-tested with a non-sensitive document, and `/api/v1/references/status`
should confirm that the deployment-wide baseline remains active.

## Recovery evidence

Each deployment backup directory records:

- `compose.yaml` — base Compose snapshot;
- `current.target` — prior release target;
- `previous-image.txt` — prior XTF image reference;
- `compose.release.yaml` — prior runtime override, when one existed;
- `xtf-data.tgz` — consistent persistent-data backup.

Do not delete previous releases or images as part of the normal deploy path. Retention
and pruning are separate maintenance operations.
