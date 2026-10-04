# ADR-001 — Platform Strategy

- **Status:** Accepted
- **Date:** 2026-10-04
- **Decision owners:** XRay project
- **Scope:** Product surfaces, deployment targets, and platform priorities

## Context

XRay is being designed as an evidence-driven text-forensics platform. Its scientific engine must remain independent from any one user interface or operating system.

The product needs to satisfy two competing requirements:

1. **Broad accessibility and monetization** through a low-friction web product.
2. **Local/private analysis** for users who cannot upload sensitive material to a third-party cloud.

The platform strategy must therefore avoid duplicating detector logic across Web, Windows, macOS, Linux, Android, and iOS.

## Decision

XRay will be developed as a **multiplatform forensic engine whose primary commercial product is Web**.

The authoritative scientific implementation lives in **XRay Core**. User-facing products are adapters around the same engine and evidence model.

```text
                         XRAY CORE
                    Python / scientific engine
                              |
               +--------------+--------------+
               |                             |
              CLI                         Service/API
               |                             |
               |                 +-----------+-----------+
               |                 |                       |
               v                 v                       v
            Local use          Web/SaaS              Desktop
                                                    local/hybrid
                                                        |
                                           +------------+------------+
                                           |            |            |
                                        Windows       macOS        Linux
```

No platform may introduce an independent implementation of detector semantics.

## Platform priorities

### 1. Core Python + CLI — REQUIRED / FIRST

**Decision:** categorical yes.

The Core and CLI are the first implementation surface and the source of truth for:

- forensic ingestion;
- immutable artifact handling;
- derived views;
- detector execution;
- calibration;
- corpus analysis;
- evidence objects;
- report data;
- benchmark behavior.

The CLI is not merely a developer convenience. It is the first reproducible interface to the engine and a permanent automation/debugging surface.

### 2. Web — PRIMARY PRODUCT

**Decision:** categorical yes.

Web is the principal commercial and user-facing product.

Primary goals:

- lowest onboarding friction;
- SaaS monetization;
- account/billing support;
- document and corpus upload;
- case management;
- report generation;
- remote detector updates;
- API-backed integrations;
- immediate access from Windows, macOS, Linux, Android, and iOS browsers.

The Web application must consume the same XRay service contracts used by other clients.

### 3. Desktop

#### Windows — REQUIRED

**Decision:** categorical yes.

Windows is a first-class commercial desktop target.

Rationale:

- expected institutional/professional adoption;
- strong relevance to universities, businesses, legal/professional environments, and general users;
- enables local/offline/private workflows;
- can serve as a bridge to hybrid analysis.

Windows support must influence architecture from the beginning even if the desktop shell is built after Web.

#### macOS — TARGET / HIGH PROBABILITY

**Decision:** target platform, approximately 75–85% commitment pending packaging validation.

macOS must not be blocked by architecture choices.

Technical feasibility is considered good if the Desktop layer uses a cross-platform shell and the Python scientific runtime is packaged independently.

Remaining validation items include:

- signing and notarization;
- Python/runtime bundling;
- native scientific dependencies;
- Apple Silicon support;
- local-service lifecycle;
- update strategy.

Unless a material blocker appears, macOS should follow Windows as Desktop priority 2.

#### Linux — SECONDARY / COMMUNITY-DEVELOPER TARGET

**Decision:** not a primary commercial market.

Linux remains strategically useful because:

- XRay development and CI naturally run well on Linux;
- researchers and technical users may prefer it;
- maintaining a build may have low marginal cost if Desktop remains cross-platform;
- it improves reproducibility and credibility.

Linux should therefore be supported on a **best-effort/community/developer** basis when technically inexpensive, but it must not delay Windows, Web, or macOS.

### 4. Enterprise / On-Premise — FUTURE PRODUCT, ARCHITECTURALLY RESERVED

**Decision:** future project, not current implementation scope.

XRay will not build a complete Enterprise product during the initial milestones.

However, current architecture must preserve the ability to deploy later as:

```text
customer infrastructure
        |
        +-- XRay service/API
        +-- local database/object storage
        +-- workers
        +-- private detector keys
        +-- private corpora
```

Core scientific logic must never require XRay SaaS to function.

### 5. Android / iOS / iPadOS Native — FUTURE DECISION

**Decision:** defer native mobile applications.

During early product phases, mobile users are served by the responsive Web application/PWA.

A native mobile project should only begin when it provides clear additional value such as:

- OS share-sheet integration;
- local file acquisition;
- camera/document capture;
- offline case review;
- local lightweight analysis;
- push notifications;
- device-native workflows unavailable to a PWA.

Android and iOS are therefore **not discarded**, but are explicitly outside initial scope.

## Delivery order

The intended sequence is:

```text
1. XRay Core + CLI
       |
2. XRay Web / SaaS
       |
3. XRay Desktop
       +-- Windows  [mandatory]
       +-- macOS    [probable / validation pending]
       +-- Linux    [secondary / best effort]
       |
4. Enterprise / On-Premise
       |
5. Native Android / iOS / iPadOS if justified
```

## Deployment modes

The architecture should eventually support three analysis modes.

### Cloud

```text
artifact -> XRay Cloud -> analysis -> report
```

Best for convenience, centralized updates, and SaaS use.

### Local

```text
artifact -> local XRay Core -> analysis -> report
```

Best for confidentiality, offline use, and sensitive evidence.

### Hybrid

```text
private artifact
      |
local extraction / sensitive analysis
      |
approved derived features or hashes
      |
XRay Cloud services
```

Hybrid mode must never imply that raw evidence is uploaded unless the user explicitly chooses that behavior.

## Architectural consequences

### Mandatory

- one scientific codebase;
- one evidence/status vocabulary;
- one detector contract;
- one benchmark/calibration methodology;
- UI-independent domain models;
- service/API boundaries around the engine;
- local execution must remain technically possible;
- no SaaS-only assumptions in XRay Core.

### Preferred

- Web frontend: modern web stack;
- Desktop shell: cross-platform technology such as Tauri, subject to later validation;
- Desktop scientific execution: packaged XRay Core/service rather than reimplemented detectors;
- Web/desktop clients share schemas generated from the same API/domain contracts.

### Prohibited

Do not create:

```text
web_detector.py
windows_detector.py
mac_detector.py
android_detector.py
```

for the same scientific method.

Platform-specific code may handle UI, acquisition, filesystem integration, packaging, IPC, authentication, or lifecycle — **not divergent scientific semantics**.

## Commercial positioning

Current priority for monetization:

1. **Web/SaaS**
2. **Windows Desktop**
3. **macOS Desktop**
4. **Commercial API**
5. **Enterprise/on-premise**
6. Native mobile only if product demand justifies it

Linux is valuable technically but is not currently treated as a principal revenue target.

## Consequences

### Positive

- Web reaches users immediately across platforms.
- Windows/local mode gives XRay a strong privacy story.
- macOS remains feasible without forcing an early parallel implementation.
- Linux can remain available to researchers without driving product priorities.
- Mobile is covered by Web/PWA before native investment.
- Enterprise remains possible without contaminating the first milestones.
- Detector bugs and scientific improvements are fixed once in Core.

### Costs / risks

- Packaging Python/scientific dependencies for desktop may be non-trivial.
- macOS requires signing/notarization and Apple Silicon validation.
- Local/cloud parity requires disciplined service contracts.
- Hybrid privacy guarantees must be explicit and testable.
- A cross-platform desktop shell still requires OS-specific QA.

## Revisit triggers

This ADR should be reconsidered only if one of these becomes true:

- macOS packaging proves materially impractical;
- Linux develops meaningful commercial demand;
- native mobile workflows become strategically important;
- browser/PWA limitations block required forensic acquisition;
- Enterprise demand arrives earlier than expected;
- the chosen Desktop shell cannot reliably host/control the scientific runtime.

Until such evidence appears, this ADR is **Accepted** and should guide M1 onward.
