# ADR-002 — Licensing & IP Strategy

- **Status:** Accepted
- **Date:** 2026-10-04
- **Decision owners:** XRay project
- **Scope:** Licensing, intellectual-property boundaries, public/private split, and commercial use

## Context

XRay is intended to become a commercial text-forensics product while retaining a public
repository for transparency, scientific credibility, reproducibility, and technical
inspection.

A public repository does not require a permissive open-source license. The project needs
to preserve commercial rights while still allowing reasonable evaluation and
non-commercial research.

## Decision

The XRay Core repository will use a **source-available proprietary commercial license**.

The public repository remains viewable and inspectable, but commercial use, resale,
redistribution, hosted-service use, commercial incorporation, and competing commercial
use require separate written permission.

The governing file is:

`LICENSE` — **XRay Source-Available Commercial License v1.0**

## Licensing model

```text
PUBLIC REPOSITORY
        |
        +-- source visible
        +-- methodology visible
        +-- selected detectors visible
        +-- tests visible
        +-- scientific contracts visible
        |
        +-- commercial rights RESERVED
        +-- redistribution RESTRICTED
        +-- SaaS/hosting RESTRICTED
        +-- competing commercial use RESTRICTED
```

This repository is **not** licensed under MIT, BSD, Apache-2.0, GPL, AGPL, or another
general-purpose open-source license.

## Permitted without separate commercial agreement

Subject to LICENSE:

- source inspection;
- personal evaluation;
- testing and learning;
- non-commercial academic use;
- non-commercial research;
- private modifications for those permitted purposes.

## Requires separate written commercial permission

- SaaS or hosted-service operation;
- paid API operation;
- resale or sublicensing;
- production deployment for third parties;
- OEM/integration into commercial products;
- commercial redistribution;
- commercial derivative offerings;
- competing commercial text-forensics/watermark/provenance products using XRay source.

## Public vs private product boundary

### Public / potentially public

- Core domain contracts;
- evidence/status schemas;
- architecture documentation;
- selected scientific detectors;
- reproducibility tests;
- benchmark methodology;
- public SDKs or formats when deliberately released;
- selected reference implementations.

### Private / commercial by default

- production infrastructure;
- customer data;
- customer-specific integrations;
- billing and anti-abuse systems;
- private corpora;
- commercial detector packs;
- proprietary models;
- secret watermark keys;
- enterprise-only features;
- operational fraud/abuse heuristics;
- internal deployment tooling;
- confidential benchmarks or licensed datasets.

## SDK and interoperability policy

Future SDKs, schemas, or interoperability libraries may use a more permissive license
such as Apache-2.0 or MIT if doing so improves adoption without exposing the commercial
Core.

Such components must live in clearly separated packages or repositories and carry their
own explicit LICENSE files.

## Third-party code

Third-party components retain their own licenses.

No third-party code may be relicensed under the XRay Source-Available Commercial License
unless the applicable third-party license permits it.

`THIRD_PARTY_NOTICES.md` is mandatory for tracking incorporated third-party materials.

## Contributions

External contributions must not silently create ambiguous ownership.

Until a formal CLA/DCO workflow is adopted:

- contributions must only be accepted when the contributor has the right to submit them;
- contribution terms must preserve the project's ability to distribute accepted work in
  commercial XRay offerings;
- substantial outside contributions should receive explicit review before merge.

A formal Contributor License Agreement may be introduced before broader community
contribution is encouraged.

## Commercial licensing

The repository license is not the final customer license for paid products.

Future commercial offerings may have separate agreements for:

- Web/SaaS;
- Windows/macOS Desktop;
- enterprise/on-premise;
- API usage;
- OEM/embedded use;
- private detector packs;
- support and professional services.

## Scientific transparency

Commercial protection must not justify misleading forensic claims.

Licensing does not weaken the Scientific Contract:

- `NOT_TESTABLE != NOT_DETECTED`;
- similarity is not authorship;
- watermark evidence is not automatically provenance;
- detector calibration and uncertainty remain visible.

## Consequences

### Positive

- code can remain publicly inspectable;
- scientific credibility is preserved;
- commercial exploitation remains reserved;
- SaaS and Desktop monetization remain protected;
- future SDKs can be opened independently;
- sensitive commercial assets remain private.

### Costs / risks

- custom source-available licenses require more legal care than standard OSS licenses;
- some open-source communities and package registries may not classify the project as
  open source;
- license compatibility must be checked before incorporating third-party code;
- enforcement is legal, not technical: public source can still be physically copied.

## Revisit triggers

Revisit this ADR if:

- XRay adopts an open-core model;
- a permissively licensed SDK is split into a separate repository;
- external contributions become significant;
- enterprise/OEM licensing begins;
- legal review recommends changes to the source-available license;
- a future version of XRay is intentionally open-sourced.

Until then, ADR-002 is **Accepted**.
