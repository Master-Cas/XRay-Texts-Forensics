# M9 — Adversarial Robustness Lab

## Objective

Measure how forensic signals behave after controlled text transformations.

M9 is a **stress laboratory**, not a universal watermark-removal claim.

## Reference watermark scope

The first scorer is the known-key XRay reference red/green scheme from M4.

Results therefore describe that reference implementation unless a future scorer explicitly
states otherwise.

They must not be extrapolated directly to secret production watermarks.

## Controlled transformations

The default suite includes:

- Unicode NFKC normalization;
- whitespace canonicalization;
- Unicode case folding;
- punctuation removal;
- deterministic replacement of every third whitespace token;
- deterministic deletion of every fifth whitespace token.

The first four mostly test surface-form invariance.

The latter two are destructive sequence edits used to expose context sensitivity.

## Preservation metrics

M9 reports:

- token-set Jaccard;
- token-sequence similarity;
- 5-gram survival;
- lexical TF-IDF cosine;
- character-length ratio.

These are **lexical/sequence preservation** measures.

XRay deliberately does not call them semantic similarity.

## Detector measurements

For every transform M9 records:

- scored token count;
- green token count/fraction;
- z-score;
- one-sided p-value;
- detector status;
- z-score delta from baseline;
- whether baseline detection was retained.

## External transformations

For paraphrase, translation, or third-party rewrite systems, XRay can compare the original
and transformed files independently:

```bash
xray compare-transform original.txt transformed.txt --json
```

A future model-backed semantic scorer can be added without changing these raw preservation
metrics.

## CLI

```bash
export XRAY_WATERMARK_KEY='...'
xray watermark-stress text.txt --key-env XRAY_WATERMARK_KEY --json
```

Secret bytes are never serialized into the report.

## Gate

M9 is accepted when:

- identity comparison produces perfect preservation;
- destructive replacement lowers 5-gram survival;
- a controlled watermarked baseline is detected;
- surface transformations expected to preserve reference token IDs retain detection;
- destructive replacement lowers the reference watermark score;
- secret bytes never appear in output;
- CLI pair comparison and robustness report work;
- pytest, Ruff, mypy, and GitHub CI pass.
