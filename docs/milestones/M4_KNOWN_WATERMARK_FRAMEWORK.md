# M4 — Known Watermark Framework

## Objective

Provide a safe, typed framework for watermark tests that require secret material and an
exact tokenizer/configuration.

## Reference detector

M4 ships:

`watermark.redgreen.reference`

It is a deterministic XRay reference implementation used to validate:

- secret-provider boundaries;
- tokenizer requirements;
- repeated-context masking;
- null statistics;
- z-score reporting;
- `NOT_TESTABLE` and `INSUFFICIENT_DATA` semantics;
- positive/negative controlled corpora.

**It is not SynthID.**

No result from this detector may be described as Claude, Gemini, Google, Anthropic, or
other provider provenance.

## Secret handling

Detector code receives only a `SecretProvider` and a secret reference.

M4 includes:

- `EnvironmentSecretProvider` for CLI/development;
- `InMemorySecretProvider` for tests.

Secret bytes are never added to Evidence parameters.

Future production providers may use OS keyrings, Vault, HSMs, or enterprise secret
managers.

## Tokenizer contract

Known-key detection is only valid when the correct tokenizer is available.

The M4 reference tokenizer is:

`xray.stable-word-sha256.v1`

It exists only for XRay controlled tests and does not pretend to be a production-model
tokenizer.

## Statistical score

For eligible tokens:

```text
green_count ~ Binomial(n, gamma)

z = (green_count - n*gamma)
    / sqrt(n*gamma*(1-gamma))
```

The detector reports a one-sided normal-tail p-value as descriptive metadata.

The threshold is configurable and **will be empirically calibrated in M5**.

## Repeated contexts

Repeated context tuples may be masked so duplicate local context does not repeatedly
contribute identical keyed evidence.

## CLI

The key is supplied by environment-variable reference, not as a command-line value:

```bash
export XRAY_WATERMARK_KEY='...'
xray watermark-redgreen document.txt --key-env XRAY_WATERMARK_KEY
```

## SynthID boundary

A future SynthID-compatible adapter must provide the exact algorithm/configuration,
tokenizer, and authorized key material needed for a valid test.

Until then:

```text
SynthID without required configuration/key
=> NOT_TESTABLE
```

not:

```text
=> NOT_DETECTED
```

## Gate

M4 is accepted when:

- missing key => `NOT_TESTABLE`;
- short text => `INSUFFICIENT_DATA`;
- controlled keyed ON corpus is detected;
- the same corpus under the wrong key is not detected;
- repeated contexts are maskable;
- secret values never appear in Evidence/CLI output;
- pytest, Ruff, mypy, and GitHub CI pass.
