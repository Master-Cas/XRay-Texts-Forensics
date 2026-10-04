# M11 — Web UI Alpha

## Objective

Turn the M10 HTTP backend into a usable same-origin web product without duplicating
forensic logic or committing prematurely to a heavy frontend framework.

## Architecture

```text
Browser UI
  |
  | same-origin fetch
  v
/api/v1/*
  |
  v
existing XRay Python core
```

The browser contains presentation and workflow logic only.

All forensic ingestion, detection, storage, case integrity, and metrics remain server-side.

## UI workspaces

### Quick Scan

- choose a document;
- preserve + analyze via the Unicode endpoint;
- show artifact SHA-256, size, media type, encoding, view count;
- show typed Evidence rows.

### Cases

- create a case;
- reopen a case by ID;
- add an artifact and Unicode analysis;
- show artifact/run/evidence/audit counts;
- show audit verification;
- open JSON, HTML, or PDF reports.

### Compare

- select original + transformed documents;
- show M9 lexical/sequence preservation metrics;
- repeat the warning that lexical similarity is not semantic equivalence.

## Frontend dependency strategy

M11 uses plain HTML/CSS/JavaScript packaged with Python.

That is deliberate:

- no Node/npm supply chain yet;
- no separate frontend build;
- no second deployment unit;
- same-origin API by construction;
- fast product iteration while API semantics are still moving.

A future React/Vue/Svelte frontend can replace the shell without changing `/api/v1`.

## Browser security

Product UI/API responses receive:

- `X-Content-Type-Options: nosniff`;
- `Referrer-Policy: no-referrer`;
- restrictive Permissions-Policy;
- Cross-Origin-Opener-Policy;
- strict same-origin Content-Security-Policy for product routes.

The UI has:

- no inline scripts;
- no inline event handlers;
- no third-party scripts/fonts/CDNs;
- no `innerHTML` rendering of forensic/user values;
- DOM values inserted using `textContent`.

Swagger docs are excluded from the product CSP because their built-in renderer has its own
asset requirements. Production deployment may disable docs entirely.

## Packaging

Static HTML/CSS/JS are declared as Python package data so installed wheels retain the UI.

## Product boundary

M11 is still a local/single-user alpha.

It does not add:

- authentication;
- billing;
- organizations/tenants;
- cloud object storage;
- asynchronous jobs;
- provider API credentials.

Those belong to the production service layer, not the UI.

## Gate

M11 is accepted when:

- root UI loads;
- static JS/CSS load same-origin;
- CSP/security headers are present;
- UI script does not use `innerHTML`;
- Quick Scan API workflow remains tested by M10;
- Case API workflow remains tested by M10;
- Compare API workflow remains tested by M10;
- static assets are included in package metadata;
- full pytest/Ruff/mypy pass;
- real Uvicorn serves the UI and API.
