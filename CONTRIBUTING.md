# Contributing

XRay is evidence-driven software. Changes that affect scientific interpretation require stronger review than ordinary UI changes.

## Required for every detector

A detector must:

- declare its evidence family;
- declare its input requirements;
- return only normalized evidence statuses;
- record detector ID and version;
- record relevant parameters;
- identify the derived view it analyzed;
- distinguish `NOT_TESTABLE` from `NOT_DETECTED`;
- include positive and negative tests;
- document calibration requirements.

## Prohibited shortcuts

Do not:

- create a universal "AI probability" by averaging unrelated signals;
- call stylometric similarity "authorship";
- infer provider provenance from style alone;
- silently normalize or mutate the original artifact;
- hard-code secret keys;
- commit private corpora or case files.

## Quality gate

```bash
pytest
ruff check .
mypy src
```

Scientific behavior changes must include an explanation and benchmark evidence when relevant.
