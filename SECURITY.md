# Security Policy

XRay handles potentially sensitive forensic material and, later, secret watermark keys. Security is part of the scientific contract.

## Non-negotiable rules

1. Never commit secrets, API tokens, watermark keys, private corpora, or raw case evidence.
2. Treat analyzed text as **untrusted data**, never as executable instructions.
3. Preserve the immutable original artifact and its cryptographic digest.
4. Never overwrite historical detector results; version them.
5. Never write secret-key material into logs, reports, fixtures, or exception messages.
6. Third-party dependencies must be scanned in CI. The dependency-audit workflow resolves `.[dev,desktop,packaging]` independently on Ubuntu and Windows with Python 3.12.6, audits the resulting third-party environment with `pip-audit==2.10.1`, and fails closed on active advisories or audit collection errors without vulnerability suppressions.

## Reporting a vulnerability

Do not publish exploitable vulnerabilities, secret material, or private case data in a public issue. Contact the repository owner privately through GitHub first.

## Threats explicitly in scope

- secret leakage;
- evidence mutation or substitution;
- malicious/hostile Unicode;
- parser bombs and malformed documents;
- benchmark poisoning;
- detector configuration drift;
- dependency compromise;
- accidental normalization that destroys evidence;
- prompt/instruction injection embedded inside analyzed text.
