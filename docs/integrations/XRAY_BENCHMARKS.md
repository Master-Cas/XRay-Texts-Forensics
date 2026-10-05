# XRay Benchmarks integration

XRay keeps application source and reference/benchmark data in separate repositories.

## Repositories

- Application: `Master-Cas/XRay-Texts-Forensics`
- Reference data: `Master-Cas/XRay-Benchmarks` (private)

The benchmark repository stores versioned source snapshots, provenance manifests,
third-party notices and reproducible builders. Production does not depend on a user's
private reference library being populated.

## Production reference root

The Web service loads a deployment-wide reference library from:

```text
XRAY_REFERENCE_ROOT=/reference-data
```

The production container mounts the generated benchmark library read-only.

Tenant/private reference sets remain separate. They can override the global comparator for
that tenant once their corpus readiness gate is met.

## Initial Spanish baseline

Snapshot: `sloptotal-spanish-v1`

Upstream:

```text
pablocaeg/sloptotal
5d1750b7a275452069ccc0da1ec0ded5c2a5549e
```

Reference sets:

| Set | Class | Samples |
| --- | --- | ---: |
| Humano · Gutenberg ES clásico | human | 20 |
| Humano · Wikipedia ES 2018 | human | 40 |
| IA · DeepSeek Chat ES 2026-09-30 | AI / DeepSeek | 40 |

Total: **100** reference samples.

The source snapshot, provenance and build script live in `XRay-Benchmarks`. Third-party
licensing/attribution is preserved there.

## Scientific boundary

This baseline enables reference comparison; it does **not** make XRay a universal
human-vs-AI classifier.

The three existing M6 comparison spaces remain separate:

- style fingerprint similarity;
- character n-gram/SVD similarity;
- lexical/content similarity.

A nearest reference set is not an authorship probability. Genre can be a major confounder:
for example, literary AI prose may resemble human Gutenberg prose in character patterns.

Therefore:

```text
closest corpus != provider identity
closest corpus != proof of AI authorship
small score margin != meaningful evidence
```

Calibration and held-out benchmarks must be used before a similarity margin is promoted
to an origin claim.

## Rebuilding production data

Clone `XRay-Benchmarks` and run:

```bash
python scripts/build_sloptotal_spanish.py --output /desired/reference/root
```

Then mount that directory read-only and set `XRAY_REFERENCE_ROOT` to the container path.

Do not use blind evaluation samples as reference/training material.
