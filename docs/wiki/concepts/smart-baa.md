---
title: Smart BAA (On-Chain Business Associate Agreement Escrow)
acronyms: [BAA]
created: 2026-07-09
updated: 2026-07-15
type: concept
tags: [compliance, tokenomics]
confidence: high
source_files:
  - contracts/src/health/SmartBAA.sol
  - contracts/src/health/SmartBAAFactory.sol
---

This page merges and corrects the old wiki's `hybrid-escrow.md` and
`smart-baa-technical-guide.md` — both described the same subject
(HIPAA Business Associate Agreements represented on-chain) with
overlapping and, in places, aspirational detail. This page documents only
what `contracts/src/health/SmartBAA.sol` actually implements; the
"what's not built" section at the bottom lists the old pages' extras
explicitly so nothing here is silently dropped.

## Table of contents

- [The real mechanism](#the-real-mechanism)
- [The closed loop with BCC/OPA](#the-closed-loop-with-bcc-opa)
- [What's NOT built (correcting the old wiki's extras)](#what-s-not-built-correcting-the-old-wiki-s-extras)

## The real mechanism

One `SmartBAA` instance per `(coveredEntity, businessAssociate)` pair,
deployed by `SmartBAAFactory` — never constructed directly, so the
"who may even become a covered entity" gate is checked once at the
factory, not re-checked (or forgotten) per instance. A Covered Entity
(hospital) and a Business Associate (the agent, acting as `businessAssociate`)
post a `bytes32 agreementHash` — a hash of their off-chain legal agreement —
plus the agent's $ITK collateral (`requiredCollateral`), and a single
named `arbitrator` address resolves disputes:

```solidity
enum Status { Proposed, Active, Disputed, Terminated }

function sign() external onlyBA;                    // BA posts collateral, Proposed -> Active
function raiseDispute() external onlyCE;             // CE flags a breach, Active -> Disputed (freezes revoke)
function arbitrate(bool slash) external onlyArbitrator; // Disputed -> Terminated (slash=true, collateral to CE)
                                                          //         or -> Active (slash=false, dismissed)
function revoke() external;                          // either party, Active -> Terminated, collateral returns to BA
```

```mermaid
stateDiagram-v2
    [*] --> Proposed: SmartBAAFactory deploys<br/>(agreementHash, requiredCollateral, arbitrator)
    Proposed --> Active: sign() — BA posts collateral
    Active --> Disputed: raiseDispute() — CE flags a breach
    Active --> Terminated: revoke() — either party
    Disputed --> Terminated: arbitrate(slash=true)<br/>collateral to CE
    Disputed --> Active: arbitrate(slash=false)<br/>dismissed
    Terminated --> [*]
    note right of Disputed
        revoke() is blocked while Disputed —
        no dodging arbitration by exiting
    end note
```

**Collateral is isolated per agreement** (a single ITK balance held by this
one contract) — a deliberate departure from a shared/pooled staking vault
design, so a slash on one BAA can never be starved by withdrawals against
an unrelated one. `revoke()` cannot be called while `Disputed`, so a party
under active accusation can't dodge arbitration by unilaterally exiting.

## The closed loop with BCC/OPA

[BCC middleware](../entities/bcc_middleware.md) enforces the same BAA
on-chain *before* an agent even acts, not just after a dispute: a clinical
[BCC commitment](bcc.md) carries a signed `covered_entity_address`, OPA
flags the intent `requires_baa`, and the middleware calls
`SmartBAAFactory.isBAAActive(coveredEntity, agent)` — failing closed if it
can't positively confirm. [ComplianceGate](compliance-gate.md)'s
`isHealthcareCompliant` performs the equivalent read for the read-optimized
compliance summary surface; [EHRGate](compliance-gate.md) performs its own
independent live check at actual PHI-access time. All three consult the
same underlying `SmartBAAFactory.isBAAActive`.

## What's NOT built (correcting the old wiki's extras)

The old `smart-baa-technical-guide.md` described several mechanisms that do
**not** exist in `SmartBAA.sol` today — flagged here explicitly, not
silently dropped, per the schema's `[PLANNED]` rule:

- **`[PLANNED]` 72-hour dispute window.** The old guide described a
  `initiateSlash()` "soft slash" with a 3-day evidence window before
  `finalizeSlash()`. The real contract has no time-based logic at all:
  `arbitrate(bool)` can be called immediately after `raiseDispute()`, with
  no minimum delay.
- **`[PLANNED]` On-chain EIP-712 typed signing.** The old guide described
  parties signing the `documentHash` via EIP-712 typed data in-wallet. The
  real contract takes `agreementHash` as a plain constructor argument (set
  by `SmartBAAFactory` at deploy time) — there is no on-chain signature
  verification step; `sign()` just transfers collateral and flips status.
- **`[PLANNED]` `recoverBusinessAssociate()` / controller recovery.** No
  such function exists — there is no key-recovery pathway if a party loses
  its private key.
- **`[PLANNED]` Nested/subcontractor BAAs.** No support for one BAA
  requiring a downstream agent to stake its own collateral.
- **Corrected: single arbitrator, not a 3-party multi-sig.** The old
  `hybrid-escrow.md` described a multi-signature wallet of "Hospital
  Administrator + Neutral Third-Party Auditor + AI Vendor." The real
  contract has one `arbitrator` address, set once at deployment
  (`SmartBAAFactory`, expected to be a neutral/governance address, not
  either party) — not a multi-sig of the three parties themselves.
- **Not evidenced anywhere in this repo**: an IPFS-pinned legal document,
  an OPA-linked `baaId`, a "Compliance Officer Command Center" UI, or a
  `slashAndRevoke()` combined function. `arbitrate(true)` is the real
  slashing path; there is no dashboard UI for BAA proposal/review built yet
  (see [integrity-dashboard](../entities/integrity-dashboard.md)'s "What's built").

Related: [ComplianceGate](compliance-gate.md), [BCC](bcc.md),
[contracts](../entities/contracts.md).
