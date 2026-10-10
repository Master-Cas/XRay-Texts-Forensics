# XTF Composite v1 runtime integration

## Scope

XTF Composite v1 is a frozen three-state statistical classifier. The web product must not
retrain, recalibrate, sweep thresholds, or reinterpret either child channel.

Decision precedence is immutable:

1. `AI_LIKELY` when the frozen AI channel fires.
2. Otherwise `HUMAN_LIKELY` when the independent frozen human channel fires.
3. Otherwise `INCONCLUSIVE`.

`NOT_AI_LIKELY` never means human. `NOT_HUMAN_LIKELY` never means AI.

Public disclaimer:

> Clasificación estadística, no prueba criptográfica de procedencia.

Provider/model-family attribution, verified watermark checks, reference-corpus similarity and
Unicode forensics remain separate evidence families.

## Frozen identities

The integration pins these control artifacts by SHA-256 before starting the worker:

- composite closure: `85fbf6abb0f800fa4fbcb88fe5930987d50794e2776128d8b6731db9c486d3fa`
- composite freeze: `23a67a9adb85ffef3199d6e2f332a77683a7c2ca3eb3a41ad8ae14de1ad2d20f`
- composite runtime manifest: `bd079d2867a1bdc90a53260759336a34f7fbeba550dc9e4fceef22004cfcd902`
- composite runtime implementation: `057b008d3a4bef67ded868ee237b74a1d35660ec92cce0d039fb4db388ec549f`
- composite self-test report: `38bd99660f3df1a6984e485dbced30359b3816ff6a6a23d75f7896b311ada21b`
- AI runtime NPZ: `eb89527a4d8a866f0987a866f827857555eab874cf28244e3c796577adad6b55`
- AI runtime manifest: `dc13db59df8dea4128b880cab0870760f80c1fe3d3598e9329c88e685f4b3d13`

The loader refuses to start the classifier if any pinned artifact is missing or changed.

## Process isolation

The XRay web environment and the frozen ML environment intentionally stay separate.

The web process starts `xray_text_forensics.web.composite_worker` with the frozen runtime's
`human-likely-v2-runtime/python` wrapper. Communication uses JSON Lines over private stdin/stdout
pipes. The worker loads XLM-R once and stays resident for subsequent scans.

This avoids changing the web dependency graph to satisfy the frozen Torch/Transformers stack and
avoids changing the frozen ML environment to satisfy web dependencies.

The IPC client uses bounded binary pipes with background stdout/stderr readers and a
bounded write queue. Its full-message timeout includes lock acquisition and IPC transfer,
and reserves bounded time for process termination. A reply without a newline is not
accepted. Individual responses are limited to 64 KiB; requests to 32 MiB. A broken
exchange poisons the worker, which is terminated without automatic restart.

A process-local web semaphore permits one full composite scan at a time. Excess
requests receive HTTP 503 with Retry-After rather than waiting in an unbounded queue.
Full scans run in a thread pool so /healthz and /api/v1/health remain responsive.
Each web process has its own worker; horizontal scaling multiplies ML memory demand.
Worker stderr is continuously drained, hashed and byte-counted for operational
diagnosis without storing raw text or user input.

## Configuration

Enable the frozen classifier only by setting:

```text
XRAY_COMPOSITE_ROOT=/absolute/path/to/round3-sourcebalanced-v1
XRAY_COMPOSITE_TIMEOUT_SECONDS=60
```

`XRAY_COMPOSITE_ROOT` must be the directory containing both:

```text
xtf-composite-v1-closure.json
xtf-composite-v1/
```

The currently frozen runtime embeds its Nitro research root. The loader verifies that the
configured root matches that embedded root. A production deployment therefore needs a separate
artifact-placement/deployment gate; do not silently rewrite paths inside the frozen runtime.

## Readiness and failure behavior

When no composite root is configured, the classifier is optional and /api/v1/ready
reports composite_runtime=not_configured; full scans report authorship NOT_TESTABLE.

When a root is configured:

- startup verifies hashes and starts the worker;
- `/api/v1/ready` performs a live `ping` against the worker;
- a failed or dead worker makes readiness return HTTP 503 with `composite_runtime=error`;
- a full scan still preserves the rest of the forensic analysis, but reports
  `authorship_assessment.state=ERROR` rather than converting a runtime failure into negative or
  positive authorship evidence. The same ERROR state applies to configuration-enabled
  initial-load failures, missing artifacts, hash mismatches, malformed protocol frames,
  invalid response schemas and inconsistent channel results. Public responses never
  include internal filesystem paths, stderr text, stack traces or raw exceptions.

Short or technically ineligible text returns `INCONCLUSIVE` and the `ai_authorship` family is
reported as `INSUFFICIENT_DATA`.

## API contract

`POST /api/v1/analyze/full` includes `authorship_assessment` with:

- `state`: `AI_LIKELY`, `HUMAN_LIKELY`, `INCONCLUSIVE`, `NOT_TESTABLE`, or `ERROR`;
- technical eligibility and token count;
- channel booleans;
- frozen diagnostic scores;
- frozen artifact/revision identifiers;
- the public statistical-classification disclaimer.

Diagnostic scores are not presented as a probability of real-world provenance.

## Validation performed before deployment

The integration branch passed:

- the complete Python test suite;
- Ruff;
- strict mypy;
- real FastAPI/TestClient E2E using the frozen worker;
- real Uvicorn loopback HTTP E2E;
- four concurrent HTTP scans through one worker;
- worker liveness/readiness checks;
- deliberate worker termination showing readiness `200 -> 503` and fail-safe
  `authorship_assessment=ERROR` behavior;
- clean application shutdown with no residual worker process.

These operational tests used synthetic text and development-only evidence. They did not rerun the
consumed HVSIA blind or the consumed HUMAN_LIKELY final blind, and they do not create a new
fresh-blind performance claim for the composite.

## Deployment boundary

The JSONL IPC avoids select.select on pipes and can operate on Windows, but the
frozen research wrapper, absolute Nitro root and model dependency installation have
NOT been demonstrated portable to a Windows product runtime. A passing Windows
installer CI job does NOT validate composite runtime compatibility.

Operational diagnostics: inspect readiness's composite_runtime status and structured
web logs (exception class, stderr byte count and stderr SHA256 only). Do not log
raw stderr, uploaded text, paths containing private case data or private model outputs.
After an IPC fault, inspect/restart the whole supervised web process using a separate
deployment procedure; there is no per-request auto-retry.

This document does **not** authorize production deployment. Production remains unchanged until a
separate deployment gate verifies artifact placement, host resources, service supervision,
rollback, observability and public response behavior on the target host.
