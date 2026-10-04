# M7 — Evidence Graph & Reporting

## Objective

Persist forensic cases and guarantee that report statements remain traceable to concrete
artifacts, views, detector runs, and Evidence IDs.

## Storage split

```text
content-addressed object store
  └── immutable original bytes / derived-view bytes

SQLite + WAL
  └── cases / metadata / runs / evidence / relationships / audit trail
```

SQLite never replaces the immutable content store.

## Append-only behavior

Artifacts, views, runs, evidence, and relationships use insert-only identifiers.

A duplicate identifier fails instead of silently overwriting historical analysis.

## Audit hash chain

Every recorded operation appends an AuditEvent containing:

- case ID;
- action;
- object type/ID;
- timestamp;
- details;
- previous event hash;
- current SHA-256 event hash.

`case-verify` recomputes the chain and detects historical payload tampering.

This is integrity evidence for XRay metadata; it is not a digital signature or trusted
timestamp authority.

## Evidence graph

Graph node types:

- case;
- artifact;
- derived view;
- detector run;
- evidence.

Core relations include:

- CONTAINS;
- DERIVED_AS;
- ANALYZED_BY;
- PRODUCED;
- plus explicit user/system relationships.

An Evidence ID can be traced backwards to its source Artifact.

## Reports

M7 renders:

- machine-readable JSON;
- standalone HTML;
- PDF.

Reports expose Evidence IDs, detector/version, status, finding, artifact hashes, audit
verification status, and graph traceability.

They explicitly avoid a universal AI score.

## CLI

```bash
xray case-create cases.sqlite "Investigation"
xray case-import-unicode cases.sqlite CASE_ID evidence.txt --store .xray-store
xray case-verify cases.sqlite CASE_ID
xray case-report cases.sqlite CASE_ID report.html --format html
xray case-report cases.sqlite CASE_ID report.pdf --format pdf
```

## Gate

M7 is accepted when:

- SQLite operates in WAL mode;
- a complete ingest/detector result round-trips through CaseStore;
- duplicate historical objects cannot be silently overwritten;
- audit verification succeeds before tampering and fails after tampering;
- every tested Evidence node traces to an Artifact;
- JSON/HTML/PDF reports contain Evidence IDs and scientific caveats;
- CLI case workflow passes;
- pytest, Ruff, mypy, and GitHub CI pass.
