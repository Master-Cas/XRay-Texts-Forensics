# M14 — Windows Installer Alpha

## Objective

Turn the M13 portable Windows bundle into an installable per-user application and validate
the complete install/uninstall lifecycle on a real Windows GitHub Actions runner.

## Version contract

The Python package version is the source of truth.

`xray_text_forensics.__version__` is resolved from installed package metadata rather than
a manually maintained constant.

FastAPI reports the same version.

PyInstaller explicitly includes the package distribution metadata in the frozen bundle.

The Windows workflow reads the installer version from `pyproject.toml` and passes it to
Inno Setup.

## Installer technology

M14 uses Inno Setup 6.

Source:

`packaging/windows/installer.iss`

Output:

`XRay-Texts-Forensics-Windows-Setup.exe`

The installer is built only after the portable PyInstaller bundle passes the Windows test
suite.

## Per-user installation

The alpha installer uses:

```text
PrivilegesRequired=lowest
DefaultDirName=%LOCALAPPDATA%\Programs\XRay Texts Forensics
```

This avoids an administrator/UAC requirement for the normal install flow.

The desktop shortcut is optional.

## Forensic-data retention

Application binaries and forensic user data intentionally live in different directories.

Application:

```text
%LOCALAPPDATA%\Programs\XRay Texts Forensics
```

User cases/evidence:

```text
%LOCALAPPDATA%\XRay Texts Forensics
```

The installer contains no `[UninstallDelete]` rule for user evidence.

Windows CI creates a marker inside the user-data directory, installs the application,
uninstalls it, and fails the workflow if that marker disappeared.

This gate exists because silent deletion of forensic cases during uninstall would be a
serious product defect.

## Windows CI lifecycle

The Windows job now performs:

1. Python/desktop dependency installation;
2. Windows-focused test suite;
3. PyInstaller portable build;
4. portable EXE SHA-256;
5. Inno Setup installation;
6. installer build using the package version;
7. silent install into a temporary test directory;
8. installed executable existence check;
9. silent uninstall;
10. application removal check;
11. forensic-data retention check;
12. installer SHA-256;
13. portable artifact upload;
14. installer artifact upload.

## Artifacts

Portable:

`XRay-Texts-Forensics-Windows-alpha`

Installer:

`XRay-Texts-Forensics-Windows-Installer-alpha`

Both contain checksum information generated on the Windows runner.

## Signing boundary

M14 deliberately does not fake code signing.

The installer and executable remain unsigned until an Authenticode code-signing identity is
available.

The next distribution step will need a decision among certificate/signing options such as a
standard code-signing certificate, cloud signing service, or another trusted Windows signing
workflow.

## Gate

M14 is accepted when:

- package/API/project versions agree;
- Linux/Nitro pytest/Ruff/mypy pass;
- GitHub Linux CI passes;
- Windows tests pass;
- portable PyInstaller build passes;
- Inno Setup installer builds;
- silent install succeeds;
- installed EXE exists;
- silent uninstall succeeds;
- installed EXE is removed;
- forensic user-data marker survives uninstall;
- installer checksum is produced;
- both Windows artifacts upload successfully.
