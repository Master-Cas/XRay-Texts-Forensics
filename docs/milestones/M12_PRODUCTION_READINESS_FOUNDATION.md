# M12 — Production Readiness Foundation

## Objective

Prepare the Web alpha for controlled deployment without prematurely choosing identity,
billing, or cloud-vendor architecture.

M12 is an operational foundation, not a declaration that the service is ready for open
Internet exposure.

## Configuration

`WebSettings.from_environment()` centralizes service configuration.

Supported environment variables include:

- `XRAY_ENV=development|test|production`
- `XRAY_DATA_ROOT`
- `XRAY_MAX_UPLOAD_BYTES`
- `XRAY_DOCS_ENABLED`
- `XRAY_MAX_JOB_WORKERS`
- `XRAY_MAX_PENDING_JOBS`
- `XRAY_REQUEST_LOGGING`
- `XRAY_HOST`
- `XRAY_PORT`

In production, interactive Swagger docs are disabled by default unless explicitly enabled.

## Database schema contract

The SQLite case database now contains a singleton `schema_meta` row with a schema version.

Current schema:

```text
CASE_SCHEMA_VERSION = 1
```

Opening a legacy M7–M11 database without `schema_meta`:

1. creates the version metadata;
2. ensures all v1 tables exist;
3. records version 1;
4. preserves existing case payloads.

Opening a database whose version is newer than the running binary fails closed.

Future schema changes must add an explicit migration path. Silently interpreting an unknown
future schema is forbidden.

## Liveness vs readiness

### Liveness

`GET /api/v1/health`

Answers whether the HTTP process is alive.

### Readiness

`GET /api/v1/ready`

Checks:

- case database can open;
- schema is initialized;
- SQLite journal mode is WAL;
- object store can create/read/delete a probe object.

A failed required check returns HTTP 503.

This distinction prevents an orchestrator or reverse proxy from routing real work to a
process that is alive but unable to persist evidence.

## Request correlation

Every product/API response receives:

`X-Request-ID`

A syntactically safe inbound request ID can be propagated. Invalid values are replaced by
a generated ID.

Structured access logs contain:

- event type;
- request ID;
- method;
- path;
- response status;
- duration in milliseconds.

Query strings and request bodies are not written to the access log.

## Background jobs

M12 adds a bounded in-process `JobManager`.

The first asynchronous workflow is:

`POST /api/v1/jobs/compare-transform`

Status can be read at:

`GET /api/v1/jobs/{job_id}`

The queue is deliberately bounded. When process capacity is full, the API returns HTTP 503
with `Retry-After` rather than accepting unbounded work.

Job errors are sanitized in HTTP responses. Internal exception details are not exposed as
the public error field.

## Important job boundary

M12 jobs are **process-local and non-durable**.

They solve:

- request latency;
- bounded concurrency;
- a stable HTTP job contract.

They do not yet solve:

- process restart recovery;
- multi-node dispatch;
- distributed locking;
- durable retries.

Those require a later durable queue/service layer.

## Production boundary after M12

Still required before public SaaS:

- authentication and authorization;
- user/organization isolation;
- quotas tied to an account/plan;
- durable background jobs;
- external object storage where appropriate;
- TLS/reverse proxy;
- backups and restore drills;
- secrets management;
- abuse/rate-limit controls;
- monitoring/alerting;
- privacy/data-retention policy;
- billing.

## Gate

M12 is accepted when:

- legacy case databases are adopted as schema v1 without losing cases;
- future schema versions fail closed;
- production settings disable docs by default;
- readiness verifies DB/WAL/object-store state;
- request IDs propagate and structured access logging is testable;
- invalid request IDs are replaced;
- job capacity is bounded;
- background comparison completes through the HTTP API;
- pytest, Ruff, mypy, and GitHub CI pass;
- a real Uvicorn process returns both healthy and ready.
