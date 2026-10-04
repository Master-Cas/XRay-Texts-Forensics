# M5 — Calibration & Benchmarking

## Objective

Make detector thresholds and reported performance reproducible, versioned, and resistant
to test-set leakage.

## Non-negotiable split

```text
development negative controls
          |
          v
     CALIBRATION
          |
        fixed threshold
          |
          v
held-out positive + negative test
          |
          v
      EVALUATION
```

The held-out test set may never be used to choose or adjust the threshold.

## Threshold rule

Calibration uses **negative controls only**.

For a target FPR, XRay chooses the most permissive observed threshold whose empirical
false-positive count does not exceed:

`floor(target_fpr * number_of_controls)`

Ties are handled conservatively.

When the detector interprets lower scores as stronger evidence, the inequality is reversed.

## Calibration manifest

Each calibration records:

- detector ID/version;
- dataset ID/version;
- target FPR;
- score direction;
- selected threshold;
- number of development controls;
- development false positives and empirical FPR;
- SHA-256 fingerprint of the exact development-control score records.

## Held-out report

M5 reports:

- TP / FP / TN / FN;
- TPR / FPR;
- precision / recall;
- ROC-AUC when both classes exist;
- Wilson confidence intervals for TPR and FPR;
- performance buckets by sample length.

## JSONL interchange

Each score record contains:

```json
{
  "sample_id": "sample-001",
  "label": false,
  "score": 1.234,
  "length": 200,
  "metadata": {}
}
```

## CLI

```bash
xray calibrate-scores controls.jsonl heldout.jsonl \
  --detector-id watermark.redgreen.reference \
  --detector-version 1.0.0 \
  --dataset-id reference-benchmark \
  --dataset-version v1 \
  --target-fpr 0.01 \
  --json
```

## Scientific boundary

A theoretical z threshold can be useful as a reference, but production claims should
prefer empirical calibration against versioned controls when possible.

## Gate

M5 is accepted when:

- calibration rejects positive-labelled development inputs;
- empirical development FPR never exceeds the requested target;
- calibration fingerprints are reproducible and order-independent;
- held-out evaluation cannot modify the selected threshold;
- both higher-is-positive and lower-is-positive directions work;
- ROC-AUC and confidence intervals are reported;
- length buckets are reported;
- pytest, Ruff, mypy, and GitHub CI pass.
