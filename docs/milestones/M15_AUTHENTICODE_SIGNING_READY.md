# M15 — Authenticode Signing-Ready Pipeline

## Objective

Prepare Windows release artifacts for real Authenticode signing without storing a private
key, certificate password, or signing identity in the repository.

M15 does not claim that the current alpha is signed.

## Secret contract

The Windows workflow recognizes exactly three signing inputs:

- `XRAY_SIGNING_PFX_B64`
- `XRAY_SIGNING_PFX_PASSWORD`
- `XRAY_SIGNING_TIMESTAMP_URL`

The PFX is expected as base64-encoded secret material.

If none of the three inputs is configured, the alpha build remains unsigned.

If only part of the secret set is configured, the Windows workflow fails closed.

## Signing order

When all signing inputs exist:

1. PyInstaller builds the portable desktop bundle.
2. The inner `XRay-Texts-Forensics.exe` is signed.
3. `signtool verify /pa /all /v` verifies the executable.
4. Windows `Get-AuthenticodeSignature` must report `Valid`.
5. Inno Setup builds the installer using the already-signed inner executable.
6. The outer `XRay-Texts-Forensics-Windows-Setup.exe` is signed.
7. The same two verification layers validate the installer.

This order ensures the installer contains a signed application executable and is itself
signed as a distribution artifact.

## Cryptographic profile

The generic helper uses:

- SHA-256 file digest;
- RFC-3161 timestamp URL supplied externally;
- SHA-256 timestamp digest;
- Windows Authenticode policy verification.

No timestamp provider is hardcoded in the repository.

## Tool discovery

`packaging/windows/sign-authenticode.ps1` locates `signtool.exe` from:

1. current PATH; or
2. the installed Windows SDK x64 tool directory.

The Windows workflow runs the helper in `-ProbeOnly` mode even for unsigned alpha builds.

This validates that the hosted Windows image contains the required signing tool before a
real certificate is introduced.

## Artifact transparency

Every Windows artifact contains a file named:

`SIGNING-STATUS.txt`

Its value is one of:

- `SIGNED_AUTHENTICODE`
- `UNSIGNED_ALPHA`

This avoids ambiguous release artifacts.

## Temporary key material

When signing is enabled, the PFX is decoded only into the GitHub runner temporary directory.

A final cleanup step removes the temporary PFX whether later steps succeed or fail.

The repository never receives the certificate bytes or password.

## Remaining external dependency

M15 can validate the unsigned branch and the availability of Windows signing tooling.

A true signed-build gate cannot be completed until a real Authenticode signing identity is
provided.

That requires an external business/security decision and signing credential.

## Gate

M15 is accepted as *signing-ready* when:

- package version is 0.14.0 and remains internally consistent;
- signing helper is covered by static contract tests;
- Windows runner successfully probes `signtool.exe`;
- unsigned Windows tests/build/install/uninstall continue to pass;
- unsigned artifacts explicitly contain `UNSIGNED_ALPHA`;
- partial signing-secret configuration is designed to fail closed;
- the workflow contains verified signing paths for both inner EXE and installer;
- no certificate/private key is committed;
- Linux/Nitro pytest/Ruff/mypy pass;
- GitHub Linux and Windows workflows pass.

M15 does **not** satisfy the separate gate:

`real Windows artifact has a Valid Authenticode signature`

until signing credentials are available.
