# M6 — Reference Corpus & Stylometry

## Objective

Compare suspect text with **versioned reference corpora** while keeping style, character
patterns, and topical/content similarity separate.

M6 does not implement provider attribution.

## Reference layout

A reference root contains one subdirectory per reference set:

```text
references/
├── human-news/
│   ├── .xray-reference.json
│   ├── 001.txt
│   └── 002.txt
└── model-a/
    ├── .xray-reference.json
    ├── 001.txt
    └── 002.txt
```

Optional metadata can record:

- provider;
- model/model version;
- language;
- topic;
- source;
- license.

The metadata file is never treated as corpus text.

## Reference manifest

Every set receives an order-independent SHA-256 manifest based on:

- reference metadata;
- document IDs;
- SHA-256 of exact reference text;
- document metadata.

This makes comparison results traceable to a concrete corpus version.

## Three deliberately separate signals

### Style similarity

Interpretable structural features include sentence/paragraph lengths, lexical diversity,
punctuation rates, digits, and uppercase usage. Features are standardized against the
reference collection and compared to each reference centroid.

### Character-SVD similarity

Character 3–5 gram TF-IDF is projected with a deterministic truncated SVD when the
reference matrix is large enough.

This captures orthographic and local sequence patterns without pretending they are
watermarks.

### Content similarity

Word TF-IDF cosine similarity is reported separately.

A high content similarity warns that topic/content may be a confound when interpreting
other similarities.

## No silent fusion

M6 explicitly does **not** calculate provider probability, authorship probability, or
a universal AI probability.

The three signals remain separate.

## CLI

```bash
xray stylometry-compare suspect.txt references/ --json
```

## Dataset adapters

HC3 and other external datasets may later be imported as reference datasets when their
license/provenance is recorded. M6 does not vendor external corpus content.

## Gate

M6 is accepted when:

- style fingerprints are deterministic;
- reference manifests are order-independent;
- style and content similarity can disagree on controlled data;
- metadata files are excluded from corpus text;
- reports contain no authorship-probability field;
- pytest, Ruff, mypy, and GitHub CI pass.
