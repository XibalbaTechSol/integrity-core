---
title: Integrity Protocol Specification
created: 2026-08-04
updated: 2026-08-06
type: concept
tags: [identity, metrics, compliance, infrastructure]
confidence: high
source_files:
  - spec/integrity-protocol-v0.4.md
  - spec/archive/integrity-protocol-specification-v0.3.pdf
---

# Integrity Protocol Specification

The Integrity Protocol specification defines the protocol's identity model, behavioral commitments, verifiable telemetry, Agent Integrity Score, persistent memory, governance, and compliance boundaries.

## Table of contents

- [Current normative specification](#current-normative-specification)
- [Archived PDF](#archived-pdf)
- [Version policy](#version-policy)
- [Conformance profiles](#conformance-profiles)
- [Shield specification boundary](#shield-specification-boundary)

## Current normative specification

**Version 0.4 is the current normative specification.** It is maintained as version-controlled Markdown at [`spec/integrity-protocol-v0.4.md`](../../../spec/integrity-protocol-v0.4.md), so changes remain reviewable alongside the implementation.

The specification connects the [four foundational primitives](foundational-primitives.md) to the protocol's concrete mechanisms, including the [Behavioral Commitment Chain](bcc.md), [Agent Integrity Score](ais.md), [telemetry ingestion pipeline](telemetry-ingestion.md), and [persistent memory and lineage](agent-memory.md).

## Archived PDF

The original **v0.3 comprehensive design and specification** is preserved as a historical PDF. It is useful for understanding the protocol's earlier design, but it has been superseded by v0.4 and is not the current normative source.

- [View the archived v0.3 PDF in your browser](/integrity-protocol-specification-v0.3.pdf)
- [Open the archived repository copy](../../../spec/archive/integrity-protocol-specification-v0.3.pdf)

## Version policy

Use v0.4 when implementing or evaluating protocol behavior. When the specification and deployed behavior differ, the relevant source code, interface contract, and entity pages document the implemented boundary; the wiki memory loop reconciles those sources as the repository evolves.

## Conformance profiles

Spec v0.4 now defines conformance profiles and status vocabulary in §23. Implementations must distinguish design-only, local implementation, wire implementation, live-stack implementation, chain-anchored implementation, and operational implementation. Status claims must use precise labels such as VERIFIED, PARTIAL, PLANNED, BLOCKED, DEPRECATED, or REMOVED.

This section exists to prevent silent capability transfer: a dashboard display does not prove backend enforcement, a local log is not cryptographic evidence until exported and anchored, and Shield evidence does not affect AIS until Integrity Oracle consumes it.

## Shield specification boundary

Xibalba Shield is a separate endpoint-security product. The Shield repository owns its detailed product and implementation specification in `SPECIFICATION.md`; INTEGRITY-LATEST retains `spec/xibalba-shield-v1.md` as the protocol-facing companion boundary. Integrity Protocol owns DID, BCC, telemetry, Merkle anchoring, AIS, delegation, and externally-supported wire surfaces. Shield consumes those surfaces without becoming a second scoring or anchoring backend.
