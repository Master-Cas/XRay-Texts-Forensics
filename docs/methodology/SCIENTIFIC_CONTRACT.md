# Scientific Contract

This document defines interpretation rules that implementation and UI code must not silently weaken.

## 1. No universal AI score

XRay must not average unrelated signals into one "probability that AI wrote this".

A watermark test, Unicode anomaly, stylometric similarity, semantic similarity, and provenance record answer different questions.

## 2. Frozen result vocabulary

Detector status is exactly one of:

- DETECTED
- NOT_DETECTED
- INCONCLUSIVE
- NOT_TESTABLE
- INSUFFICIENT_DATA
- ERROR

### Critical distinction

`NOT_TESTABLE` means the detector could not validly perform the test, for example because a secret key, tokenizer, model configuration, or minimum text length is unavailable.

It must never be rendered or aggregated as `NOT_DETECTED`.

## 3. Attribution discipline

- Stylometric similarity is not authorship proof.
- AI-likeness is not watermark evidence.
- Watermark evidence is not automatically provider attribution.
- Absence of detectable evidence is not proof that no watermark ever existed.
- A paraphrased text may lose a detectable watermark while remaining derived from a watermarked source.

## 4. Immutable originals

Every analysis begins from a cryptographically identified original. Normalization, decoding, extraction, tokenization, lemmatization, and cleanup create derived views.

The original is never rewritten in place.

## 5. Traceability

Every Evidence record identifies artifact, detector ID/version, evidence family, status, analyzed view when applicable, relevant parameters, creation time, and reason when testing is unavailable or insufficient.

## 6. Calibration

A statistical detector is not production-valid solely because its code runs.

Where applicable it must report empirical behavior on versioned datasets, including false-positive rate, true-positive rate, ROC-AUC, TPR at fixed FPR targets, confidence intervals, length sensitivity, language/topic sensitivity, and robustness after transformation.

## 7. Benchmark hygiene

Train/dev/test separation must be explicit. Thresholds are calibrated on development controls and evaluated on held-out data.

Benchmark metadata must track model/provider/version/date, language, topic, length, sampling configuration, source, license, and hashes where available.

## 8. Explainability

A report should expose the concrete evidence behind a finding: locations, contexts, statistics, matched features, or calibration metadata.

"Because the model said so" is not sufficient forensic justification.
