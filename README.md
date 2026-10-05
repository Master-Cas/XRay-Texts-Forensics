# XRay Texts Forensics

Evidence-driven text forensics platform for watermark detection, linguistic fingerprints, provenance analysis, and AI-generated text auditing.

> Status: **M17 — Full Forensic Scan & Human Interpretation**

## What XRay is

XRay treats text as forensic evidence. It preserves the original artifact, derives explicit analysis views, runs independent detector families, and records every result as traceable evidence.

XRay does **not** collapse all signals into a single “AI score”.

```text
watermark evidence
      !=
stylometric evidence
      !=
Unicode evidence
      !=
similarity evidence
      !=
manipulation evidence
      !=
provenance evidence
```

## Scientific status vocabulary

Every detector result must use exactly one of these states:

- `DETECTED`
- `NOT_DETECTED`
- `INCONCLUSIVE`
- `NOT_TESTABLE`
- `INSUFFICIENT_DATA`
- `ERROR`

**NOT_TESTABLE is not equivalent to NOT_DETECTED.**

## Architecture

```text
FORENSIC INGEST
      |
      v
ORIGINAL ARTIFACT
      |
      +--> immutable bytes
      +--> derived views
                |
       +--------+---------+
       |        |         |
   watermark  linguistic  similarity
       |        |         |
       +--------+---------+
                |
             EVIDENCE
                |
          CALIBRATION
                |
          EVIDENCE GRAPH
                |
        +-------+-------+
        |               |
      REPORT            API
```

See [Master Architecture V1](docs/architecture/MASTER_ARCHITECTURE_V1.md), [ADR-001 — Platform Strategy](docs/architecture/ADR-001-PLATFORM-STRATEGY.md), [ADR-002 — Licensing & IP Strategy](docs/architecture/ADR-002-LICENSING-IP-STRATEGY.md), and the [Scientific Contract](docs/methodology/SCIENTIFIC_CONTRACT.md).

## Platform strategy

XRay is a **multiplatform engine whose primary product is Web**.

Current priority:

1. Core Python + CLI — required
2. Web / SaaS — primary product
3. Windows Desktop — required
4. macOS Desktop — planned target, pending packaging validation
5. Linux Desktop — secondary / best-effort
6. Enterprise/on-premise — future
7. Android/iOS native — future decision; Web/PWA covers mobile initially

All product surfaces use the same scientific Core. Detector semantics are never reimplemented per platform.

## Development roadmap

- M0 — Foundation & Scientific Contract
- M1 — Forensic Ingestion
- M2 — Unicode Forensics
- M3 — Corpus & Linguistic Engine
- M4 — Known Watermark Framework
- M5 — Calibration & Benchmarking
- M6 — Reference Corpus & Stylometry
- M7 — Evidence Graph & Reporting
- M8 — Black-Box Audit Lab
- M9 — Adversarial Robustness Lab
- M10 — Web Backend MVP
- M11 — Web UI Alpha
- M12 — Production Readiness Foundation
- M13 — Windows Desktop Alpha
- M14 — Windows Installer Alpha
- M15 — SaaS Tenant Isolation & Identity Boundary
- M16 — Managed OIDC Accounts & Login
- M17 — Full Forensic Scan & Human Interpretation

## Development

Requires Python 3.12+.

```bash
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check .
python -m mypy src
```

## Web service

Local development:

```bash
xray-web
```

Operational endpoints:

- `GET /api/v1/health` — process liveness
- `GET /api/v1/ready` — database/object-store readiness
- `GET /api/v1/session` — authenticated principal
- `POST /api/v1/analyze/full` — multi-family forensic scan with explicit NOT_TESTABLE states

The default bind is `127.0.0.1:8080`.

Identity modes:

- `local` — single-user development/Desktop compatibility
- `gateway` — SaaS boundary behind a trusted authentication gateway
- `oidc` — managed identity using standards-based OIDC Authorization Code + PKCE

Gateway mode requires `XRAY_GATEWAY_SHARED_SECRET` and authenticated identity headers
injected by the upstream gateway. Browsers must never receive the gateway secret.

OIDC mode uses a server-side BFF session. The browser receives only an opaque HttpOnly
cookie; provider access/ID tokens and client secrets are never stored in JavaScript or
Local Storage.

The initial managed provider is WorkOS AuthKit, but XRay consumes standard OIDC discovery,
JWKS, issuer/audience validation, PKCE, and configurable claims so the forensic Core remains
provider-independent.

Tenant case databases and object stores are physically isolated under opaque hashed
directories. A tenant cannot fetch another tenant's cases or background jobs.

## Windows Desktop alpha

The desktop product reuses the same Web/API/Core stack inside a native window.

Development install:

```bash
python -m pip install -e ".[desktop]"
xray-desktop
```

Windows CI builds a portable PyInstaller bundle and publishes it as a workflow artifact.
The desktop backend binds only to loopback and protects private UI/API routes with an
ephemeral per-launch session token.

M14 also builds a per-user Windows installer with Inno Setup. It installs without
administrator privileges under `%LOCALAPPDATA%\Programs\XRay Texts Forensics`.

Uninstall removes the application but deliberately preserves forensic cases/evidence stored
under `%LOCALAPPDATA%\XRay Texts Forensics`.

The alpha installer is currently unsigned; Authenticode signing is a later release step.

## License

XRay Texts Forensics is **source-available proprietary software**.

The source can be inspected and used for limited personal evaluation and non-commercial
academic/research purposes under the terms of the
[XRay Source-Available Commercial License v1.0](LICENSE).

Commercial use, SaaS/hosting, resale, redistribution, commercial incorporation, and
competing commercial use require prior written permission from the Licensor.

This is **not an OSI-approved open-source license**.
