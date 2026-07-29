---
title: Persistent Memory, Genesis Root & Lineage [PARTIALLY BUILT]
acronyms: []
created: 2026-07-29
updated: 2026-07-29
type: concept
tags: [identity, cryptography, compliance]
confidence: high
source_files:
  - contracts/src/oracle/StateAnchor.sol
  - integrity-sdk/integrity_sdk/registration.py
  - integrity-oracle/backend/src/handlers.rs
  - docs/wiki/concepts/agent-primitives.md
---

**`[PARTIALLY BUILT]`.** Source: *Integrity Protocol — Comprehensive Design &
Specification v0.3*, §4.1, §6, §7 and Appendix A gaps 1–2 and 6.

**Persistent memory is a foundational primitive of this protocol — the first one the
spec names (§4.1) — and as of 2026-07-29 it is enforced, not aspirational:** an agent
with no anchored genesis memory root cannot register. What is built and what is still
open are separated precisely below; the "Verified status" table records what was
actually checked against code, rather than restating the spec's own status claims.

## Persistent Memory is a foundational primitive — not an 8th contract

The spec's first foundational primitive (§4.1) is **Persistent Memory**, on the
principle of *continuity of the economic agent*. It is realized through the
**existing** [`StateAnchor`](../entities/contracts.md) — primitive #2 of the
seven — not through a new per-agent contract. The
[PrimitiveSet stays 7 addresses](agent-primitives.md); no factory, registry, or
`resolveDID` change is implied.

The reasoning is the credit-score analogy the whole protocol derives from
(§2): persistent legal identity is what makes a human credit score meaningful,
and its agent analogue is *cryptographic self-sovereignty **plus** persistent
memory*. An agent that cannot carry state across sessions is not a continuing
economic subject, so its [AIS](ais.md) would score a history the agent cannot
itself produce.

**Normative requirement (§4.1):** the agent MUST control a durable **Trust
Vault** whose commitments can be Merkle-anchored on its own `StateAnchor`.
Registration requires `StateAnchor.latestRoot != bytes32(0)`. An
empty-but-initialized vault is valid at birth. The raw vault stays
agent-controlled — only commitments go on-chain.

## Genesis root

| Epoch | Who may anchor | Why |
|---|---|---|
| 0 → 1 (genesis) | Agent only — controller or `SovereignAgent.execute` | Memory is the agent's own state; a privileged party writing an agent's first memory root would repeat the pattern XNS deliberately rejected when it dropped admin-only registration |
| ≥ 2 | MAY use protocol `ANCHOR_ROLE` | Routine oracle anchoring of the Trust Vault, as `StateAnchor` already does |

**Oracle enforcement (§7.1) — built.** After the PrimitiveSet match already performed by
`POST /v1/agent/register`, the oracle reads `StateAnchor.latestRoot` directly from chain
(`ChainClient::memory_state`). Zero → **`400 MemoryNotInitialized`**. Same
independent-read posture as the existing primitive re-verification — the oracle trusts the
chain, not the client's claim. Registration is all-or-nothing: no half-registered agents
(§6).

**Empty vault at birth.** §4.1 allows an empty-but-initialized vault, but `anchorRoot`
reverts on `bytes32(0)`, so "empty" needs a defined non-zero form:
`GENESIS_VAULT_ROOT = keccak256("integrity.trust-vault.genesis.v1")`, pinned as a
cross-package constant in `docs/INTERFACE_CONTRACT.md` §4.4a and derived by hashing in
every package rather than copied as a hex literal. The gate checks only that the root is
non-zero, so an agent with a genuinely non-empty vault at birth is equally valid.

## Verified status (checked against code 2026-07-29, not inherited from the spec)

| Spec requirement | Status |
|---|---|
| §7.1 oracle rejects a zero root with `400 MemoryNotInitialized` | **BUILT.** `ChainClient::memory_state` + `AppError::MemoryNotInitialized`. Covered by e2e `oracle_e2e_register_rejects_missing_genesis_memory_root`, which deploys a real on-chain agent with only the genesis anchor omitted and asserts 400 + no persisted row |
| §6 registration anchors a genesis root before `registerPrimitives` | **BUILT.** `chain.anchor_genesis_root()` + `registration.py` step 8b. The pre-existing full-registration e2e passes with the gate live, which is what proves the ordering satisfies it |
| §7.2 genesis root is agent-authorized | **BUILT, unenforced.** It works today with no Solidity change — `StateAnchor`'s admin *is* the `SovereignAgent`, which the constructor grants `ANCHOR_ROLE`, so `SovereignAgent.execute → anchorRoot` at epoch 0 is a controller-signed genesis. What is missing is *preventing* the alternative (below) |
| §7.2 `ANCHOR_ROLE` restricted to epoch ≥ 2 | **OPEN (Appendix A gap 2).** `anchorRoot` is `onlyRole(ANCHOR_ROLE)` at every epoch, and `registration.py` step 8 grants that role to the oracle signer — so the protocol *could* anchor an agent's genesis root instead of the agent. Blocked on migration, not on design: `StateAnchor` is deployed **per agent, not cloned**, so a contract change reaches only future agents |
| §7.4 lineage attestation | **OPEN (Appendix A gap 6).** Not started |

**Existing agents are non-conformant.** All 7 agents registered before this flow —
including `xibalba.integrity` (`StateAnchor 0x09DCBBd0…`) — report `latestRoot == 0`,
verified live on Base Sepolia and confirmed by the running oracle refusing that DID with
400. They stay registered because the gate runs only at registration. Each needs one
controller-signed `anchorRoot` to conform. See [`PRODUCTION_GAPS.md`](../../../PRODUCTION_GAPS.md) §19.

## Copying, lineage, and similarity

Memory alone confers nothing — §7.3:

| Action | Effect |
|---|---|
| Copy another agent's vault bytes | Does **not** transfer identity, stake, or AIS |
| Claim another's roots/AIS | Rejected — roots are bound to the original `StateAnchor` and registries |
| Steal keys + memory | Ordinary account takeover; recovery via controller rotation where available |

**Lineage (§7.4)** — fork, migration, or recovery — requires an explicit
controller-signed attestation plus an on-chain record. Default: **no automatic
AIS or stake transfer.** A capped partial credit is optional after a challenge
window under `reputation_policy: partial`. The new agent still performs its own
genesis root, and MAY record the lineage hash as a vault leaf.

**Behavioral similarity (§7.5)** is observational only in this version. It MUST
NOT, alone, cause registration rejection or an automatic slash. It MAY later
inform soft AIS ceilings or serve as dispute evidence under versioned rules.
This is the same distinction §14.2 draws: the protocol scores *attributable,
continuous, staked behavior*, not novelty — it is not a copyright office.

## What memory does not change

AIS keeps its four components and their fixed weights (§8.1) — memory adds no
fifth term, and `integrity-oracle/scoring-core` remains the sole computer of
the score. Anchoring cadence carries the same batching tradeoff documented for
telemetry in [Merkle Batching](merkle-batching.md): per-entry anchoring is
prohibitively expensive, and batching leaves a window in which recent memory is
uncommitted.

Related: [Agent Primitives](agent-primitives.md) ·
[BCC](bcc.md) (§4.4 — commitment outcomes SHOULD become vault leaves) ·
[Telemetry Ingestion](telemetry-ingestion.md) ·
[Identity Ceiling](identity-ceiling.md)
