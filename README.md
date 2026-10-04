# XRay Texts Forensics

Evidence-driven text forensics platform for watermark detection, linguistic fingerprints, provenance analysis, and AI-generated text auditing.

> Status: early architecture / M0 foundation.

## Core principle

XRay does **not** collapse all signals into a single “AI score”.

Watermark evidence, stylometric evidence, Unicode evidence, similarity evidence, manipulation evidence, and provenance evidence remain separate and traceable.

## Scientific status vocabulary

Every detector result must use one of these states:

- `DETECTED`
- `NOT_DETECTED`
- `INCONCLUSIVE`
- `NOT_TESTABLE`
- `INSUFFICIENT_DATA`
- `ERROR`

In particular, **NOT_TESTABLE is not equivalent to NOT_DETECTED**.

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
- M9 — Adversarial Lab

License decision is intentionally pending during the architecture phase.
