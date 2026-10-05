# M17 — Full Forensic Scan & Human Interpretation

## Objective

Expose XRay as one forensic product instead of presenting the Unicode detector as if it
were the whole system.

M17 orchestrates the evidence families that are currently usable in a single Web/API scan
while preserving the scientific boundary between them.

## Full scan endpoint

```text
POST /api/v1/analyze/full
```

The endpoint:

1. preserves and ingests the original artifact;
2. runs deterministic Unicode forensics;
3. extracts a linguistic corpus snapshot;
4. extracts an interpretable style fingerprint;
5. compares the suspect text with versioned reference corpora when configured;
6. reports provider-specific watermark testing as unavailable unless a real authorized
   detector/tokenizer/key is available;
7. returns a plain-language family summary without producing a universal AI score.

## Evidence families

### Unicode

The existing M2 detectors remain unchanged. Unicode evidence describes representation,
format controls, mixed scripts and related properties.

Unicode evidence is **not AI-authorship evidence**.

### Linguistic profile

M17 exposes descriptive properties of the suspect document, including token/context counts
and the M6 style fingerprint.

A profile can exist without any origin conclusion.

### Reference stylometry

If `XRAY_REFERENCE_ROOT` points to a valid M6 reference library, XRay returns the three
existing M6 signals separately:

- style similarity;
- character-SVD similarity;
- content similarity.

The UI never converts these into an authorship/provider probability.

If no reference library is configured:

```text
REFERENCE STYLOMETRY => NOT_TESTABLE
```

not:

```text
=> NOT_DETECTED
```

### Watermark

The M4 reference red/green detector is an architecture/test detector and is not SynthID,
Claude provenance, ChatGPT provenance, Gemini provenance or another production-provider
watermark.

Until an authorized provider-specific detector, exact tokenizer/configuration and required
key material exist, the Full Scan reports:

```text
VERIFIED WATERMARK => NOT_TESTABLE
```

## Reference corpus configuration

Reference corpora are optional and versioned using the existing M6 layout:

```text
references/
├── human/
│   ├── .xray-reference.json
│   └── sample-001.txt
├── claude/
│   ├── .xray-reference.json
│   └── sample-001.txt
└── ...
```

Production configuration:

```text
XRAY_REFERENCE_ROOT=/path/to/versioned/references
```

Reference metadata should identify source, provider/model when known, language, model
version when known, topic/sampling constraints and licensing/provenance.

## Tenant reference library

The Web product also provides an authenticated tenant-scoped library for known-origin
reference samples:

```text
GET  /api/v1/references
POST /api/v1/references
POST /api/v1/references/{set_slug}/documents
```

Reference sets and their raw samples are stored under the tenant's opaque storage root.
They are never shared with another tenant.

A tenant reference library takes precedence over the optional deployment-wide
`XRAY_REFERENCE_ROOT` when running a Full Scan.

The UI exposes this as **References**, where a user can create sets such as:

- Human writing;
- Claude stories;
- ChatGPT answers;
- Gemini essays;
- Dola stories;

and upload multiple known-origin samples to each set.

Reference uploads are content-deduplicated by SHA-256.

## Product interpretation

The Web UI presents:

1. an overall forensic result;
2. one card per evidence family;
3. reference-corpus similarities when available;
4. a separate plain-language Unicode explanation;
5. expandable technical Unicode evidence.

The top-level result explicitly says when origin is not testable.

## Scientific boundary

```text
closest reference corpus
        !=
provider identity
        !=
authorship probability
        !=
universal AI probability
```

M17 deliberately prefers an honest `NOT_TESTABLE` result to a visually persuasive but
unsupported verdict.

## Gate

M17 is accepted when:

- `/api/v1/analyze/full` runs Unicode + linguistic/style analysis in one request;
- no reference corpus produces an explicit origin `NOT_TESTABLE` assessment;
- configured versioned reference corpora produce separate M6 similarities;
- watermark is not reported as negative when no provider-specific test exists;
- the Web Quick Scan calls the full endpoint rather than the Unicode-only endpoint;
- raw detector evidence remains available for forensic traceability;
- pytest, Ruff, mypy and Windows packaging CI pass.
