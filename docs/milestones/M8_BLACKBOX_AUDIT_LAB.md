# M8 — Black-Box Audit Lab

## Objective

Detect repeatable context-conditioned forced-choice effects through a black-box API
without claiming that any significant effect automatically identifies a watermark.

The implementation is independently written from public statistical concepts.

## Frozen design

An experiment freezes prompt prefixes, context strings, candidate output words, samples
per cell, permutation count, alpha, and a random seed. The complete design receives a
SHA-256 fingerprint.

## Within-prefix control

A model may naturally prefer different candidates for different prompt phrasing.

M8 first centers candidate probabilities within each prefix across contexts. This removes
stable prefix-level candidate preference.

It then asks whether the same context-conditioned residual pattern aligns across
independent prefixes.

## Statistic and null

Observed candidate probabilities are centered within prefix. Residual vectors are averaged
across prefixes for each context. The statistic is the sum of squared aligned residuals.

For the null distribution, context labels are independently permuted within each prefix.
This preserves prefix preference, observed cell distributions, sample size, and marginal
choice behavior while destroying cross-prefix context identity.

The empirical p-value is one plus the number of null statistics greater than or equal to
the observed statistic, divided by permutations plus one.

## Controlled ON/OFF self-test

M8 includes a synthetic same-base provider.

OFF contains prefix-specific preferences but no keyed context effect.
ON adds a keyed context-conditioned candidate preference.

Validation requires OFF non-significant and ON significant under the same frozen design.

## Scientific interpretation

A significant result means repeatable context-conditioned choice bias is present under
this design.

It does not by itself mean SynthID was detected, a secret key was recovered, a provider
was identified, all outputs are watermarked, or that an effect is intentional.

## Production boundary

Real provider adapters require a separately frozen provider/model/version, exact prompts,
API parameters, audit date, request budget, retry/error policy, multiple-testing policy,
and preregistration decision.

Credentials must enter through a secret provider or environment. They must never be
committed to Git or copied into reports.

## Gate

M8 is accepted when the design is fingerprinted, prefix preference alone does not trigger
significance, synthetic OFF is non-significant, synthetic ON is significant under the
same design, results are reproducible, invalid provider choices fail closed, and all
project gates pass.
