# M8 — Black-box Watermark Protocol

## Objective

Detect repeatable **context-dependent forced-choice bias** without access to a provider's
secret watermark key.

This implements the experimental architecture inspired by public black-box watermark
research, independently written for XRay.

## Design

A balanced experiment crosses:

- multiple prompt prefixes;
- multiple fixed-shape contexts;
- one forced-choice vocabulary;
- repeated samples per prefix/context cell.

The default validation contexts are unique non-repeating 15-digit strings.

## Why prefix control matters

A model may strongly prefer different words under different prompt phrasings even when no
watermark exists.

XRay therefore does **not** pool all prompts into one naive contingency table.

It calculates context/choice association **within each prefix**, sums the Pearson
statistics, then permutes context labels only within the same prefix.

This preserves prefix-level choice bias in the null distribution.

## Statistic

For each prefix, XRay constructs:

```text
context × forced-choice counts
```

and calculates a Pearson association statistic.

The experiment statistic is the sum across prefixes.

The p-value is empirical:

```text
p = (1 + permutations with statistic >= observed)
    / (1 + number of permutations)
```

## Controlled validation

M8 includes a synthetic endpoint with one shared base sampler:

- **OFF**: prefix-driven choice preferences only;
- **ON**: identical base sampler plus a keyed context/choice tilt.

The gate requires OFF to remain non-significant while ON becomes significant.

This is stronger than merely showing that the test can fire.

## External collection

The endpoint contract is deliberately separated from the analysis.

Real API collectors can later produce the same JSONL observation records without changing
the statistical method.

Each record preserves:

- experiment ID;
- prefix/context IDs;
- repeat index;
- allowed choices;
- parsed choice;
- validity/raw response;
- optional metadata such as provider/model/version.

## Interpretation boundary

A significant result means:

> repeatable context-dependent forced-choice bias remains after controlling for
> prefix-level preferences.

It may be **compatible with keyed sampling behavior**.

It does **not** mean:

- the provider secret key was recovered;
- the exact production watermark algorithm was identified;
- provider authorship/provenance was proven.

## CLI

```bash
xray blackbox-validate --permutations 499 --json
xray blackbox-analyze observations.jsonl --permutations 999 --json
```

## Gate

M8 is accepted when:

- experiment design is balanced and deterministic;
- duplicate contexts are rejected;
- same-base OFF/ON validation separates at alpha=0.01;
- strong prefix bias alone does not automatically trigger the test;
- permutation results are deterministic for a fixed seed;
- JSONL observation interchange round-trips;
- pytest, Ruff, mypy, and GitHub CI pass.
