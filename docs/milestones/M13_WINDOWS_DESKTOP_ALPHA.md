# M13 — Windows Desktop Alpha

## Objective

Deliver the first Windows desktop product surface without duplicating the forensic engine.

The desktop application embeds the existing same-origin Web UI in a native window and
runs the same FastAPI/Core stack on an ephemeral loopback port.

## Architecture

```text
Native desktop window (pywebview)
          |
          v
http://127.0.0.1:<ephemeral-port>
          |
          v
FastAPI / Web UI / Core
          |
          +--> SQLite/WAL case DB
          +--> content-addressed object store
```

No detector, evidence model, or scientific rule is reimplemented specifically for Windows.

## Desktop data location

Windows stores local application data below:

```text
%LOCALAPPDATA%\XRay Texts Forensics
```

The launcher also has platform fallbacks for development on macOS/Linux.

## Ephemeral port

The launcher reserves an actual loopback socket on port 0, allowing the operating system
to choose an available port.

Uvicorn receives that already-bound socket.

This avoids:

- fixed-port collisions;
- race-prone "find free port, close it, reopen later" behavior;
- accidental non-loopback binding.

## Loopback authorization

Binding to localhost is not considered sufficient authorization.

Each desktop launch generates a cryptographically random token.

The initial UI URL includes the token only for the launch request:

```text
/?desktop_token=<ephemeral-secret>
```

The server exchanges it for a cookie with:

- HttpOnly;
- SameSite=Strict;
- Path=/.

The browser UI immediately removes the token query parameter from the visible URL with
`history.replaceState`.

Private UI/API routes require the cookie.

Unauthenticated loopback access is limited to:

- static product assets;
- `/api/v1/health`;
- `/api/v1/ready`.

The request logger records paths only, not query strings, so the launch token is not written
to the normal access log.

## Native window

The optional desktop dependency is `pywebview`.

The runtime import is lazy so Core/Web installations do not require desktop GUI
dependencies.

Entry point:

```bash
xray-desktop
```

Closing the native window shuts down the embedded Uvicorn server.

## Windows packaging

M13 uses PyInstaller in onedir mode for the alpha.

Build specification:

```text
packaging/windows/xray-desktop.spec
```

The build collects:

- XRay Python package code;
- packaged Web UI HTML/CSS/JS;
- pywebview runtime files;
- Uvicorn runtime modules.

## Windows CI

`.github/workflows/windows-desktop.yml` runs on `windows-latest`.

The workflow:

1. installs Python 3.12;
2. installs XRay desktop/build dependencies;
3. runs Windows-focused tests;
4. builds the PyInstaller bundle;
5. verifies that the executable exists;
6. calculates SHA-256;
7. uploads the portable directory as a workflow artifact.

Artifact name:

`XRay-Texts-Forensics-Windows-alpha`

## Alpha boundary

M13 is not yet a signed installer.

Still deferred:

- Authenticode code signing;
- MSI/MSIX/installer UX;
- auto-update;
- crash reporting;
- Windows shell/file associations;
- installer/uninstaller data-retention choices;
- release-channel policy;
- EV/standard code-signing certificate decision.

Those belong to the release/distribution milestone after the executable build itself is
validated on Windows CI.

## Gate

M13 is accepted when:

- M12 behavior remains intact;
- desktop access without token returns 403;
- valid launch token creates the session cookie;
- private API works with the cookie;
- token is removed from visible UI URL;
- loopback desktop server starts on an ephemeral port;
- server stops cleanly;
- Linux/Nitro pytest/Ruff/mypy pass;
- GitHub Linux CI passes;
- GitHub Windows workflow passes its tests;
- PyInstaller produces `XRay-Texts-Forensics.exe`;
- Windows artifact includes a SHA-256 checksum.
