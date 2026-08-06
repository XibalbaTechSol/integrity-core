---
title: ComplianceGate & Integrity Health
created: 2026-07-07
updated: 2026-07-15
type: concept
tags: [compliance, layer-2]
confidence: high
source_files:
  - contracts/src/health/ComplianceGate.sol
  - contracts/src/health/EHRGate.sol
  - contracts/src/health/SmartBAAFactory.sol
  - contracts/src/health/CoveredEntityRegistry.sol
---

**Integrity Health** is the HIPAA/healthcare vertical — the flagship proof that
the Integrity Protocol works in the most heavily regulated industry there is. It
is not a side feature; it is the demonstration that makes the rest of the
protocol credible.

`ComplianceGate` is the per-agent [primitive](agent-primitives.md) (an EIP-1167
clone) that connects a single agent to that vertical.

## What it does

Each agent's `ComplianceGate` declares its regulated vertical
(`None` | `Healthcare`) and exposes one live read the
[oracle](../entities/integrity-oracle.md) and
[dashboard](../entities/integrity-dashboard.md) can call without knowing Integrity Health's
internals:

```solidity
function isHealthcareCompliant(address coveredEntity) external view returns (bool);
```

It **never fakes a `true`.** For a `Healthcare`-vertical agent it does a live
read: `CoveredEntityRegistry.isActiveCoveredEntity(coveredEntity)` **and**
`SmartBAAFactory.isBAAActive(coveredEntity, agent)`. Self-declared compliance
flags (mirroring the SDK's `integrity.compliance.*` telemetry attributes) are
stored separately and are *never* consulted by this live-verified boolean — a
dishonest agent cannot self-declare its way to compliance.

## The Integrity Health stack (shared singletons)

- `CoveredEntityRegistry` — registry of HIPAA covered entities and business
  associates (admin-vetted; being listed is a claim of real legal status).
- `SmartBAAFactory` / `SmartBAA` — one on-chain Business Associate Agreement
  escrow per (covered entity, agent) pair; the agent posts $ITK collateral,
  slashable to the covered entity on an arbitrated breach. See
  [Smart BAA](smart-baa.md) for the full state machine and what the old
  wiki overstated (no on-chain EIP-712 signing, no dispute-window timer,
  no controller recovery — corrected there).
- `HIPAAGuardrailRegistry` — anchors which OPA policy version governed each PHI
  access decision.
- `EHRGate` — the real PHI-access enforcement boundary: requires patient consent
  **and** an active `SmartBAA` **and** a minimum [AIS](ais.md), resolving the
  agent's own `ReputationRegistry` clone live via `XibalbaAgentRegistry`.

`ComplianceGate` does **not** replace `EHRGate` as the enforcement point — it is
the read-optimized summary surface. `EHRGate` still performs its own live checks
at access time.

## The closed loop

The [BCC middleware](../entities/bcc_middleware.md) enforces the same BAA on-chain
before an agent even acts: a clinical [BCC commitment](bcc.md) carries a signed
`covered_entity_address`, OPA flags it `requires_baa`, and the middleware calls
`SmartBAAFactory.isBAAActive(coveredEntity, agent)` — failing closed if it can't
positively confirm.

```mermaid
flowchart TB
    BCC["BCC commitment<br/>(covered_entity_address, requires_baa)"]
    MW["bcc_middleware<br/>(pre-execution gate)"]
    CG["ComplianceGate.isHealthcareCompliant<br/>(read-optimized summary)"]
    EHR["EHRGate.checkAccess<br/>(real-time PHI-access enforcement)"]
    BAA["SmartBAAFactory.isBAAActive(coveredEntity, agent)"]

    BCC --> MW --> BAA
    CG --> BAA
    EHR --> BAA
    EHR -->|also checks| Consent["patient consent"]
    EHR -->|also checks| AIS["minimum AIS<br/>(live ReputationRegistry read)"]
```

All three consult the same underlying `isBAAActive` read rather than caching
their own copy of BAA status — a lapsed BAA is invisible to none of them.

PHI never reaching the oracle in the first place is a separate, SDK-side
concern from this on-chain compliance gate — see
[Observability & PHI Safety](observability-vtl.md) for the client-side
`Redactor` design.

Related: [agent primitives](agent-primitives.md),
[BCC](bcc.md), [Smart BAA](smart-baa.md), [contracts](../entities/contracts.md).
