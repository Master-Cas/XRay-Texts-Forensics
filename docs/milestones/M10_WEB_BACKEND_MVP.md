# M10 — Web Backend MVP

## Objective

Expose the existing XRay core through a typed HTTP API without duplicating forensic logic.

The main product strategy is Web, but M10 is intentionally a **single-node backend MVP**.

It is not yet an Internet production deployment.

## Stack

- FastAPI
- Uvicorn
- existing Pydantic domain models
- existing SQLite/WAL case store
- existing content-addressed object store

## API v1

### Health

`GET /api/v1/health`

### Forensic ingest

`POST /api/v1/ingest`

Multipart upload. Original bytes are preserved before parsing.

### Unicode analysis

`POST /api/v1/analyze/unicode`

Returns sanitized artifact/view metadata plus Evidence records.

### Transformation comparison

`POST /api/v1/compare-transform`

Accepts original + transformed documents and returns M9 preservation metrics.

### Cases

- `POST /api/v1/cases`
- `GET /api/v1/cases/{case_id}`
- `POST /api/v1/cases/{case_id}/analyze/unicode`
- `GET /api/v1/cases/{case_id}/report?format=json|html|pdf`

## Data boundary

The core preserves local storage URIs for forensic reproducibility.

The HTTP API deliberately strips:

- `storage_uri`;
- `source_declared`;
- local `file://` paths.

Public response models expose IDs, hashes, analysis metadata, and Evidence, not server
filesystem topology.

## Upload boundary

Uploads are read in bounded chunks.

The default maximum is 25 MiB and can be configured with `WebSettings`.

Oversized uploads return HTTP 413.

The browser-provided filename is reduced to a basename before it enters Artifact metadata.

## Network boundary

`xray-web` binds to `127.0.0.1:8080` by default.

M10 deliberately does not enable permissive CORS.

A public deployment still requires:

- authentication/authorization;
- tenant isolation;
- CSRF/session policy if cookies are used;
- request rate limits;
- quotas;
- reverse proxy/TLS;
- background job queue for expensive analyses;
- object-store lifecycle policy;
- database migrations/backups;
- operational audit/monitoring.

## Run

```bash
xray-web
```

Optional environment:

```bash
XRAY_DATA_ROOT=/path/to/data
XRAY_HOST=127.0.0.1
XRAY_PORT=8080
```

## Gate

M10 is accepted when:

- health endpoint works;
- upload ingest works through the real M1 service;
- Unicode analysis detects a controlled invisible codepoint;
- oversized upload returns 413;
- transform comparison works;
- case create/analyze/fetch works;
- JSON/HTML/PDF report routes work;
- HTTP responses do not expose internal storage URIs;
- pytest, Ruff, mypy, GitHub CI pass;
- a real local Uvicorn process responds to an HTTP health request.
