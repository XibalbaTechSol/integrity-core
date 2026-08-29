---
title: Integrity Protocol Specification
created: 2026-08-04
updated: 2026-08-17
type: concept
tags: [identity, metrics, compliance, infrastructure]
confidence: high
source_files:
  - spec/integrity-protocol-v0.4.md
  - spec/integrity-protocol-v0.5-proposed.md
  - spec/integrity-protocol-v3.2.md
  - spec/archive/integrity-protocol-specification-v0.3.pdf
---

# Integrity Protocol Specification

The Integrity Protocol specification defines the protocol's identity model, behavioral commitments, verifiable telemetry, Agent Integrity Score, persistent memory, governance, and compliance boundaries.

## Table of contents

- [Current normative specification](#current-normative-specification)
- [Proposed specification](#proposed-specification)
- [Whitepaper v3.2](#whitepaper-v3-2)
- [Archived PDF](#archived-pdf)
- [Version policy](#version-policy)
- [Conformance profiles](#conformance-profiles)
- [Shield specification boundary](#shield-specification-boundary)

## Current normative specification

**Version 0.4 is the current normative specification.** It is maintained as version-controlled Markdown at [`spec/integrity-protocol-v0.4.md`](../../../spec/integrity-protocol-v0.4.md), so changes remain reviewable alongside the implementation.

The specification connects the [four foundational primitives](foundational-primitives.md) to the protocol's concrete mechanisms, including the [Behavioral Commitment Chain](bcc.md), [Agent Integrity Score](ais.md), [telemetry ingestion pipeline](telemetry-ingestion.md), and [persistent memory and lineage](agent-memory.md).

## Proposed specification

[`spec/integrity-protocol-v0.5-proposed.md`](../../../spec/integrity-protocol-v0.5-proposed.md)
is the new proposed normative amendment derived from the v3.2 review cycle. It records
identity-interface, AIS admissibility/floor, memory, complete mediation, telemetry-prover
decentralization, availability escrow, grace modes, high-frequency channels/compiler trust, and
attested-host boundary proposals with implementation-status evidence. It is not accepted protocol authority. Phase 0
identity discovery and bounded AIS fail-closed defaults are locally implemented portions; the
remaining clauses stay `[PARTIAL]` or `[PLANNED]` until separately reviewed and accepted.

## Whitepaper v3.2

[`spec/integrity-protocol-v3.2.md`](../../../spec/integrity-protocol-v3.2.md) is the current
explanatory, non-normative whitepaper. It motivates the proposed architecture and roadmap but
does not amend v0.4. Its PDF is a generated publication artifact. Implementation claims must
come from source, tests, deployment observation, the interface contract, and the gap register.

## Archived PDF

The original **v0.3 comprehensive design and specification** is preserved as a historical PDF. It is useful for understanding the protocol's earlier design, but it has been superseded by v0.4 and is not the current normative source.

- [Open the archived v0.3 repository PDF](../../../spec/archive/integrity-protocol-specification-v0.3.pdf)

## Version policy

Use v0.4 when implementing or evaluating accepted protocol behavior. Use v0.5-proposed only
for proposal review, and v3.2 for explanatory context. When the specification and deployed
behavior differ, preserve the difference: source, tests, and deployment observation establish
implementation evidence but do not silently amend normative requirements.

## Conformance profiles

Spec v0.4 now defines conformance profiles and status vocabulary in §23. Implementations must distinguish design-only, local implementation, wire implementation, live-stack implementation, chain-anchored implementation, and operational implementation. Status claims must use precise labels such as VERIFIED, PARTIAL, PLANNED, BLOCKED, DEPRECATED, or REMOVED.

This section exists to prevent silent capability transfer: a dashboard display does not prove backend enforcement, a local log is not cryptographic evidence until exported and anchored, and Shield evidence does not affect AIS until Integrity Oracle consumes it.

## Shield specification boundary

Xibalba Shield is a separate endpoint-security product. The Shield repository owns its detailed product and implementation specification in `SPECIFICATION.md`; integrity-core retains `spec/xibalba-shield-v1.md` as the protocol-facing companion boundary. Integrity Protocol owns DID, BCC, telemetry, Merkle anchoring, AIS, delegation, and externally-supported wire surfaces. Shield consumes those surfaces without becoming a second scoring or anchoring backend.
