# M3 — Corpus & Linguistic Engine

## Objective

Add interpretable corpus statistics that can support linguistic fingerprinting and
reference-corpus comparison without turning stylistic similarity into authorship claims.

The design borrows **public analytical concepts** common to corpus linguistics and T-LAB
documentation, but the implementation is independently written.

## Core units

### Lexical units

M3 begins with deterministic word tokens and n-grams.

### Context units

M3 supports:

- sentence contexts;
- paragraph contexts.

Co-occurrence is based on presence within a context, not arbitrary character distance.

## Association metrics

For a term pair M3 reports:

- context co-occurrence count;
- cosine;
- Dice;
- Jaccard;
- equivalence;
- inclusion;
- pointwise mutual information.

## Second-order similarity

First-order association asks whether two terms occur together.

Second-order similarity compares their **co-occurrence profiles** across the vocabulary,
allowing two terms to be contextually similar even when they rarely occur together.

## Specificity

Two corpora can be compared term by term with:

- raw counts;
- smoothed log2 fold change;
- chi-square;
- direction A/B.

This is descriptive corpus evidence. It is not provider attribution.

## TF-IDF and intertextual distance

Each corpus is represented by the mean of its document TF-IDF vectors built in a shared
feature space.

M3 reports:

```text
cosine similarity
intertextual distance = 1 - cosine similarity
```

These values are meaningful only relative to the corpora, preprocessing, language, and
sampling design used.

## CLI

```bash
xray compare-corpora reference_a/ reference_b/
xray compare-corpora reference_a/ reference_b/ --json
```

Supported files are routed through M1 ingestion before their text enters the corpus engine.

## Scientific boundary

```text
linguistic similarity
       !=
authorship probability
       !=
provider identity
       !=
watermark evidence
```

## Gate

M3 is accepted when:

- tokenizer/context segmentation is deterministic;
- n-grams never cross document boundaries;
- association metrics pass controlled examples;
- second-order similarity recognizes shared context profiles;
- specificity direction is correct in synthetic corpora;
- related corpora score more similar than unrelated corpora;
- CLI corpus comparison is machine-readable;
- pytest, Ruff, mypy, and GitHub CI pass.
