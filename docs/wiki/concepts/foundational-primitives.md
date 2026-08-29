---
title: The Four Foundational Primitives
created: 2026-07-30
updated: 2026-07-30
type: concept
tags: [identity, metrics, compliance]
confidence: high
source_files:
  - docs/archive/2026-08/primitive-set-coherence.md
  - docs/archive/2026-08/three-foundational-primitives.md
  - docs/archive/2026-08/thesis-extensions-formal.md
  - contracts/src/oracle/StateAnchor.sol
  - contracts/src/oracle/ReputationRegistry.sol
  - contracts/src/health/SmartBAA.sol
---

> **Naming, before anything else.** This repo uses the word *primitive* in three unrelated
> senses, and conflating them is the main source of confusion:
>
> - **Foundational primitives** (this page) — the four **concepts** the protocol rests on.
> - **Agent primitives** ([`agent-primitives.md`](agent-primitives.md)) — the seven
>   **contracts** each agent owns (`PrimitiveSet`, `AgentPrimitivesFactory`).
> - **Kernel primitives** (spec v3.2 §4.4, `IntegrityKernel.sol`) — the three **invariants**
>   (value conservation, monotone rights depletion, replay-domain monotonicity) the
>   verification kernel supplies so adapter authors don't re-derive them. These are
>   guarantees the kernel's constraint-evaluation layer bakes in, not a concept from this
>   page and not one of the seven agent contracts — `IntegrityKernel`/`IntegrityAccount` are
>   deliberately separate from the `PrimitiveSet`/`XibalbaAgentRegistry` model entirely (see
>   `docs/archive/2026-08/plans/2026-08-24-phase1-testnet-deployment-proposal.md`).
>
> They are not different views of one list. `ReputationRegistry` is one of the seven agent
> contracts *and* the storage for one of the four foundational concepts; `StateAnchor`
> likewise. The kernel invariants touch neither — they're a property of the new kernel/hook
> architecture, evaluated inside `IntegrityAccount`'s `preCheck`, not stored in any agent's
> `PrimitiveSet`. The seven are an implementation; the four are the argument; the three
> kernel invariants are guarantees the kernel enforces on adapters' behalf.

## Table of contents

- [The four](#the-four)
  - [1. Persistent Memory](#1-persistent-memory)
  - [2. Agent-Owned Contracts](#2-agent-owned-contracts)
  - [3. Authority](#3-authority)
  - [4. Reputation](#4-reputation)
- [AIS is not the fourth primitive](#ais-is-not-the-fourth-primitive)
- [Why these four, and not others](#why-these-four-and-not-others)
- [Open, and deliberately so](#open-and-deliberately-so)
- [Status of this page](#status-of-this-page)

## The four

Each answers one question a counterparty must resolve before delegating anything of value.
The order is a progression: each presupposes the one above it.

| # | Primitive | Question | Principle |
|---|---|---|---|
| 1 | **Persistent Memory** | Is this the same agent over time? | Continuity of the economic agent |
| 2 | **Agent-Owned Contracts** | Can it act, and can it lose? | Residual control, with consequence |
| 3 | **Authority** | *May* it act, and for whom? | Delegated permission, non-self-granted |
| 4 | **Reputation** | *How* has it acted? | Earned, non-forgeable standing |

### 1. Persistent Memory

The agent controls a durable Trust Vault whose commitments are Merkle-anchored on its own
`StateAnchor`. Registration requires a non-zero genesis root, agent-authorized. Without
continuity there is no subject for anything else to attach to: an agent that cannot carry
state across sessions is a stateless function invoked repeatedly, and any score describes a
history it cannot itself produce.

Detail: [Persistent Memory, Genesis Root & Lineage](agent-memory.md). Status: gate enforced;
contract-level §7.2 restriction open.

### 2. Agent-Owned Contracts

The agent's own key deploys `SovereignAgent` and `StateAnchor`; five EIP-1167 clones take the
`SovereignAgent` as admin. Bonded stake belongs here rather than standing alone — **ownership
and stake are one primitive seen from two sides.** You can only stake what you own, and
ownership only means something when losing it hurts. Ownership without stake is control that
costs nothing to abuse; stake without ownership is a deposit someone else administers.

Detail: [Agent Primitives](agent-primitives.md). Status: ownership built; uniform minimum
stake at registration `[PARTIAL]`.

### 3. Authority

An agent acts under a signed delegation from a principal, within a scope it cannot widen:

```
D = (principal, agent_did, scope, not_before, not_after, revocation_ref, sig_P)
```

The defining property is **A3 — non-authorship**: the agent cannot mint its own delegation.
Note this is structurally identical to what makes reputation meaningful — *owns the contract,
cannot author the content* — which is why the two sit together in the progression without
collapsing into each other.

Status: **built in one vertical, not yet generalized.** `SmartBAA` is already a delegation
instrument (principal = covered entity, agent = business associate, `sign()`, `revoke()`,
dispute/arbitration, posted collateral). Generalizing it is what turns
`covered_entity_address` from a client claim into a resolution — see
[`MAINNET_READINESS.md`](../../MAINNET_READINESS.md) item 8.

Formal invariants A1–A5: [`thesis-extensions-formal.md`](../../archive/2026-08/thesis-extensions-formal.md).

### 4. Reputation

The non-forgeable behavioral record: signed commitments *before* acting (BCC) and re-derived
evidence *after* (observability). A record of only intentions is a promise; a record of only
outcomes has no counterfactual.

The agent owns `ReputationRegistry` while only `ORACLE_ROLE` may write to it. **Ownership
without authorship is the whole trick** — reputation the agent could author would be worth
nothing.

Detail: [BCC](bcc.md), [Telemetry Ingestion](telemetry-ingestion.md).

## AIS is not the fourth primitive

Spec §2 says *"AIS is downstream of primitives — not a replacement for them."* That remains
true, and the distinction has to stay explicit or the two readings contradict:

- **Reputation is the primitive** — the record.
- **AIS is a score** — a weighted composite over that record, computed in exactly one place
  (`scoring-core`), versioned and replaceable.

Change the formula tomorrow and the record stands. Delete the record and no formula means
anything.

## Why these four, and not others

The set is not a catalogue of what happens to be built. It is checked against spec §1's
definition of an Economic Sovereign, which is the closure condition:

| Thesis clause | Entailed by |
|---|---|
| ① owns its smart contracts | Agent-Owned Contracts |
| ② remembers via anchored memory | Persistent Memory |
| ③ can bind future behavior | Reputation (before-acting) |
| ④ holds material value at risk | Agent-Owned Contracts (stake) |
| ⑤ produces checkable evidence | Reputation (after-acting) |
| ⑥ cannot rewrite after finality | *medium property* (§3.1), not a primitive |
| ⑦ acts under delegated authority | Authority *(added in v0.4 §1)* |

**Cryptographic self-sovereignty is not on this list**, and its absence is deliberate. Keys
are the substrate all four are *expressed in* — memory roots are anchored by a
controller-signed transaction, contracts are owned because a key deployed them, delegations
are signed by a principal, evidence is attributable because it is signed. A substrate present
in all four belongs beside attribution as a property of the medium (§3.3), not repeated as a
peer of the things it enables.

Two of the old six were likewise **not independent** and were absorbed rather than dropped:
bonded stake into ownership, and BCC + observability into reputation. Full derivation:
[`primitive-set-coherence.md`](../../archive/2026-08/primitive-set-coherence.md).

## Open, and deliberately so

**Termination** — how an agent's standing *ends* — is formalized (invariants T1–T5) but not
adopted, because it requires registry mutability, which is the same question the
[upgradeability decision](../../archive/2026-08/upgradeability-decision.md) faces. Settling them
separately would risk two incompatible answers to one question. Today an agent can be
abandoned but not ended.

**Counterparty symmetry** is a generalization rather than a new primitive: BCC's
`covered_entity_address` becomes `counterparty_did`, giving bilateral evidence for A2A.

## Status of this page

The four-primitive framing is **normative as of spec v0.4**
([`integrity-protocol-v0.4.md`](../../archive/2026-08/integrity-protocol-v0.4.md) §4), which
supersedes the v0.3 PDF's six-item list. This page is the wiki-side statement of it; the spec
is authoritative and the derivation lives in `docs/design/`.
