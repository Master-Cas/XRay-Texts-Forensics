# M8.1 — Black-box Hardening

## Purpose

M8.1 keeps the M8 cross-prefix context-alignment statistic unchanged and hardens the
surrounding experimental workflow.

## Why M8 core stays unchanged

The M8 statistic tests whether a context-conditioned residual pattern aligns across
independent prompt prefixes.

That is more specific than testing whether each prefix independently has any
context/choice association, so it remains the production core.

## Reproducible CLI stack

The project now pins:

- Typer >= 0.16, < 0.17
- Click >= 8.1, < 8.2

This follows a clean-environment failure in which a much newer Typer release resolved
without a usable Click stack.

CI invokes all gates through the selected interpreter:

- python -m pytest
- python -m ruff
- python -m mypy

This prevents accidental fallback to globally installed tools.

## Same randomness in controlled OFF/ON

Synthetic validation now uses the exact same deterministic random draw for the OFF and ON
conditions.

The ON condition differs only by the keyed context-conditioned logit shift.

That makes the controlled comparison stronger: random sampling differences cannot explain
the observed separation.

## Frozen-design observation binding

Collected observations include the SHA-256 fingerprint of the BlackBoxDesign.

When a fingerprint is present, analysis fails closed if it does not match the design used
for analysis.

## External observation interchange

M8.1 adds:

- frozen design JSON;
- observation JSONL;
- raw output and metadata fields;
- offline provider/model identity;
- offline analysis CLI.

Example:

```bash
xray blackbox-analyze design.json observations.jsonl \
  --provider-id provider-name \
  --model-id model-version \
  --json
```

This means API collection can be implemented separately from statistics.

Provider credentials, retries, rate limiting, and request budget do not need to enter the
statistical core.

## Production boundary

A real provider experiment still requires a frozen record of:

- provider;
- exact model/version;
- API parameters;
- prompt template;
- date/time window;
- retry/error policy;
- sample budget;
- multiple-testing policy;
- preregistration/fresh-confirmation decision.

M8.1 provides the interchange and validation boundaries but does not invent those external
facts.

## Gate

M8.1 is accepted when:

- a fresh venv resolves the pinned CLI stack;
- full tests/Ruff/mypy pass through python -m;
- synthetic OFF/ON still validate with shared random draws;
- design + observations round-trip;
- design fingerprint mismatch fails closed;
- offline CLI analysis preserves explicit provider/model identity;
- GitHub CI passes.
