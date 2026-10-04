# Threat Model — M0

## Protected assets

- immutable original artifacts;
- hashes and provenance metadata;
- detector configuration;
- watermark secret keys;
- private corpora;
- case notes and reports;
- benchmark integrity;
- historical detector runs.

## Trust boundaries

Analyzed documents, pasted text, imported archives, external corpora, URLs, metadata, and generated model outputs are untrusted.

Their contents must never be interpreted as instructions to the XRay runtime or development agent.

## Threats and controls

### Evidence mutation
Risk: original content is normalized before hashing.
Control: hash/preserve original bytes first; transformations become DerivedViews.

### Secret leakage
Risk: watermark keys or API credentials appear in source, fixtures, logs, or reports.
Control: secret-provider abstraction, secret scanning, ignored local secret paths, redaction.

### Unicode deception
Risk: bidi controls, zero-width characters, homoglyphs, tag characters, or normalization tricks alter visible/forensic meaning.
Control: byte- and codepoint-level views before normalization.

### Parser abuse
Risk: malformed/oversized documents trigger resource exhaustion or parser vulnerabilities.
Control: bounded parsers, file limits, sandboxing where appropriate, no implicit execution.

### Detector drift
Risk: dependency/tokenizer/model changes silently alter scores.
Control: detector versioning, parameter capture, benchmark regression tests.

### Benchmark contamination
Risk: evaluation samples enter training/calibration data.
Control: immutable manifests, hashes, explicit split metadata.

### False attribution
Risk: linguistic similarity is treated as proof of authorship/provider.
Control: family-separated evidence types and constrained report language.

### Dependency compromise
Risk: malicious or vulnerable packages.
Control: minimal dependencies, lock/pin strategy, dependency scanning, third-party notices.
