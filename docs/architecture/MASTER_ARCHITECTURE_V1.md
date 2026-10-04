# Master Architecture V1

## Product definition

XRay is an evidence-driven text-forensics engine for watermark detection, linguistic fingerprinting, provenance analysis, document comparison, and AI-text auditing.

The engine is the product core. CLI, REST API, desktop, web, and enterprise surfaces are adapters around it.

## Architectural principles

1. **Original evidence is immutable.**
2. **Derived views are explicit and traceable.**
3. **Evidence families remain semantically separate.**
4. **Detector execution is versioned and reproducible.**
5. **Unknown or unavailable tests are represented honestly.**
6. **Every report conclusion must trace back to concrete evidence.**
7. **Scientific calibration is part of detector validity.**

## Core pipeline

```text
Forensic Ingest
      |
      v
Original Artifact
      |
      +--> raw bytes
      +--> raw Unicode
      +--> derived normalized/tokenized/linguistic views
                    |
          +---------+----------+-----------+
          |                    |           |
      watermark            linguistic   similarity
      detectors             forensics    engines
          |                    |           |
          +---------+----------+-----------+
                    |
                Evidence Store
                    |
                Calibration
                    |
                  Cases
                    |
              Evidence Graph
                    |
              Reports / API
```

## Domain objects

- **Artifact**: immutable original input and cryptographic identity.
- **DerivedView**: deterministic/documented transformation of an Artifact.
- **Evidence**: one typed detector finding.
- **DetectorRun**: versioned execution with parameters and inputs.
- **Case**: investigation grouping artifacts, runs and evidence.
- **Corpus / ReferenceCorpus**: collections for comparison, calibration or benchmarks.

## Evidence families

- WATERMARK
- STYLOMETRY
- UNICODE
- SIMILARITY
- MANIPULATION
- PROVENANCE

These families are intentionally non-interchangeable.

## Storage direction

M0 defines domain models only.

Planned:
- local: SQLite + WAL for transactional metadata;
- analytical matrices: Parquet, optionally DuckDB;
- server: PostgreSQL + object storage + Parquet.

No scientific domain rule may depend on one storage backend.

## Plugin architecture

Each detector declares stable ID, version, evidence family, required inputs/resources, and analysis implementation.

Requirements may include raw bytes, raw Unicode, language, tokenizer, secret key, corpus, or reference corpus.

## V1 scope

V1 includes forensic ingestion, Unicode forensics, corpus/linguistic fundamentals, known-key watermark framework, calibration, case/evidence modelling, and JSON/CLI/API/report outputs.

Advanced topic modelling, full T-LAB-like functionality, generalized sentiment analysis, and provider-attribution claims are explicitly out of V1.
