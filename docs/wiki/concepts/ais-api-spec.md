---
title: AIS API — Versioned Wire Spec
acronyms: [AIS]
created: 2026-07-11
updated: 2026-08-29
type: concept
tags: [metrics, sdk, infrastructure]
confidence: high
source_files:
  - spec/README.md
  - spec/ais-api/v1/README.md
  - spec/ais-api/v1/openapi.yaml
  - spec/ais-api/CHANGELOG.md
  - integrity-oracle/backend/src/openapi.rs
  - integrity-oracle/backend/src/bin/gen_openapi.rs
---

The externally-supported, versioned read-side wire protocol for
[integrity-oracle](../entities/integrity-oracle.md)'s HTTP API — distinct
from `docs/INTERFACE_CONTRACT.md`, which stays an internal package-
coordination document. This is the surface a third party can integrate
against without reading the monorepo.

## Table of contents

- [Why this exists, separately from INTERFACECONTRACT.md](#why-this-exists-separately-from-interfacecontract-md)
- [How it's generated](#how-it-s-generated)
- [What shipped in v1 (2026-07-11)](#what-shipped-in-v1-2026-07-11)

## Why this exists, separately from INTERFACE_CONTRACT.md

The project's own founder-level decision (2026-07-10/11 session): "standard"
for Integrity Protocol means the **wire protocol** specifically — the AIS
scoring API (read-side) and the [BCC](bcc.md) intent schema (write-side) —
not a canonical on-chain registry play, and not primarily about redeployable
Solidity interfaces. `spec/README.md` documents the full versioning policy
(additive-only within a major version, semver on shape/semantics not
computed values, RESERVED-field discipline, a lightweight single-vendor
deprecation window — not an RFC/standards-body process, since this remains
primarily Xibalba's own product per that same decision).

## How it's generated

`openapi.yaml` is **not hand-written**. `integrity-oracle/backend/src/
openapi.rs` declares a `utoipa::OpenApi` struct listing every handler/DTO in
`handlers.rs` (which itself carries `#[utoipa::path]`/`#[derive(ToSchema)]`
annotations); `src/bin/gen_openapi.rs` (`cargo run --bin gen_openapi` from
`integrity-oracle/backend/`) serializes that to `spec/ais-api/v1/openapi.yaml`.
This is the direct fix for the exact failure mode `docs/INTERFACE_CONTRACT.md`
§6.3 already documents happening once internally (the `agent_id`/`did`
field-name drift) — a hand-maintained spec can silently diverge from the code
that implements it; a generated one can't.

One deliberate exception: `scoring_core::AisWeights` (used by `AisResponse`)
doesn't itself derive `ToSchema`, because `scoring-core` is intentionally
dependency-free beyond `serde` (see that crate's `Cargo.toml` — "the single
source of truth for the AIS formula must be trivially auditable"). A
hand-maintained mirror struct, `handlers::AisWeightsSchema`, stands in for it
via `#[schema(value_type = AisWeightsSchema)]` — the one place in this spec
where "generated, not hand-authored" has a narrow, documented exception.

## What shipped in v1 (2026-07-11)

- The current generated OpenAPI contains 38 `/v1/*` paths. This is the maintained
  v1 surface; the earlier “10 routes” count was a historical snapshot and is no longer
  an accurate inventory.
- Fixed a real gap in the same pass: `GET /v1/agent/{id}` previously accepted
  `did_document` on registration and silently dropped it (no DB column, never
  returned). Now persisted (`migrations/0003_agent_did_document.sql`) and
  returned.
- `verification_tier` shipped marked RESERVED, then updated same-day when
  [the verification-tier gate](identity-ceiling.md) went from 0%- to
  partially-enforced — see that page and [bcc_middleware](../entities/bcc_middleware.md).
- `A2ACapitalPool` has no read endpoint yet — deferred as additive future
  surface, not a v1 blocker.

Related: [AIS](ais.md), [BCC](bcc.md), [Identity Ceiling & Verification
Ladder](identity-ceiling.md), [integrity-oracle](../entities/integrity-oracle.md).
