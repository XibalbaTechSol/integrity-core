# Integrity Protocol — Comprehensive Design & Specification

**Version 0.4** · Foundational Primitives · AIS · Memory · Oracle · Interop
Xibalba Tech Solutions — Agentic Trust Layer for the AI Economy

Normative intent for the protocol, with an implementation map. Package coordination lives in
[`docs/INTERFACE_CONTRACT.md`](../docs/INTERFACE_CONTRACT.md); external wire surfaces under
[`spec/`](.).

> **Ground rule:** No silent mocks. Every claim is implemented and tested against a real
> toolchain, or explicitly marked `[PLANNED]` / `[PARTIAL]`.

> **This document supersedes `Integrity_Protocol_Specification_v0.3.pdf`.** v0.4 is authored
> in markdown, in-repo, and under version control — deliberately. A specification that cannot
> be diffed, reviewed in a pull request, or kept in step with the code by any mechanism other
> than someone remembering is a coherence problem in a protocol whose entire premise is
> independently checkable state. Changes from v0.3 are listed in §19.

---

## Table of contents

1. Purpose and Thesis
2. Origin: Credit-Score Analogy
3. Foundational Properties of the Medium
4. The Four Foundational Primitives
5. On-Chain Architecture
6. Registration
7. Persistent Memory, Genesis Root, Lineage
8. Agent Integrity Score (AIS)
9. Oracle Implementation
10. Telemetry, OpenTelemetry, and Evidence Tiers
11. Behavioral Commitment (BCC)
12. Authority and Delegation
13. Verification Ladder
14. Xibalba Shield
15. Proprietary LLMs and Attribution
16. On-Chain Reputation and ERC-8004
17. Package Map and Status
18. What This Protocol Is Not
19. Changes from v0.3
20. Document Relationship and Revision Policy
    - Appendix A — Priority Implementation Gaps
    - Appendix B — One-Sentence Summary

---

## 1. Purpose and Thesis

Integrity Protocol is a **trust and compliance layer for the agentic economy**. It answers two
questions pure off-chain systems cannot answer honestly:

1. **Regulatory compliance** — can a regulator or counterparty verify an AI agent's behavior
   *after the fact*, without trusting the agent's own word?
2. **Agent trust** — can one agent or service verify another's track record *before*
   transacting with it?

**Thesis.** An agent must be an **Economic Sovereign** — a continuing entity that

① owns its smart contracts,
② remembers via durable anchored memory,
③ can bind future behavior,
④ holds material value at risk,
⑤ produces independently checkable evidence,
⑥ cannot unilaterally rewrite that evidence after finality, and
⑦ **acts only under a verifiable delegation of authority from a principal, within a scope it
cannot widen.**

Clause ⑦ is new in v0.4. Its absence was a hole rather than a simplification: the protocol
called agents sovereign while every real deployment has an agent acting *for* someone, and the
one place that relationship was modelled — Xibalba Shield's Smart BAA — was treated as a
vertical feature rather than as the general case it is.

AIS (Agent Integrity Score) is the **credit-score layer**. The primitives in §4 are the
**institutional facts** that make the score meaningful.

---

## 2. Origin: Credit-Score Analogy

The project began by defining metrics analogous to a human credit score. A credit score works
only because deeper institutional facts exist:

| Human substrate | Agent analogue |
|---|---|
| Persistent legal identity | Persistent memory + cryptographic identity |
| Exclusive control of accounts | Agent-owned smart contracts |
| Acting under a mandate | Delegated authority |
| Binding commitments | Behavioral Commitment (BCC) |
| Loss on default | Bonded stake |
| Observable history | Continuous verifiable observability |
| Hard-to-rewrite records | Immutable on-chain anchors |
| Composite score | AIS |

*AIS is downstream of the primitives — not a replacement for them.*

**AIS is not the reputation primitive, and the distinction is load-bearing.** Reputation (§4.4)
is the **record**: signed commitments before acting, re-derived evidence after. AIS is a
**score** — a weighted composite over that record, computed in exactly one place, versioned and
replaceable. Change the formula tomorrow and the record stands; delete the record and no
formula means anything. Conflating the two is what makes reputation systems elsewhere
untrustworthy.

---

## 3. Foundational Properties of the Medium

Properties of the substrate, not capabilities an agent possesses. Every primitive in §4 is
expressed *through* these.

### 3.1 Immutability of anchored history

Once a commitment is accepted by the chain and finalized, it cannot be altered or deleted by
the agent, the operator, or any single party.

| Without immutability | With immutability |
|---|---|
| Scores, roots, registrations can be rewritten | Deployments, roots, stake, score updates are fixed facts |
| Audit trusts the current DB owner | Audit checks inclusion against finalized chain state |

**Normative rules.**

1. Identity-establishing transactions (deploy `SovereignAgent` / `StateAnchor`,
   `registerPrimitives`, genesis memory root) are on-chain.
2. Trust-affecting transitions (score updates, disputes, slashes) MUST be on-chain or
   checkpointed on-chain.
3. Oracle DB and dashboards are **caches**; in conflict, **finalized chain wins**.
4. Mutable off-chain records MUST NOT be presented as equivalent to anchored history.

Immutability means **append-only, prior commitments remain verifiable** — not "nothing
changes." `StateAnchor` never un-anchors an old root (`isAnchoredRoot` stays true).

### 3.2 Public verifiability

Anyone with chain access can re-check deployments, roots, stake, and score updates without
permission from the agent or operator.

### 3.3 Attribution via signatures

State transitions are authorized by cryptographic keys bound to agent-owned contracts — a
clear answer to "who caused this history?"

### 3.4 Cryptographic self-sovereignty *(promoted from a primitive in v0.3 §4.3)*

`did:integrity:<sha256(pubkey)>` (Ed25519) plus a secp256k1 controller; rotation without
erasing history; the protocol never custodies keys.

This is a property of the medium rather than a primitive because **keys are the substrate all
four primitives are expressed in**: memory roots are anchored by a controller-signed
transaction, contracts are owned because a key deployed them, delegations are signed by a
principal, and evidence is attributable because it is signed. A substrate present in all four
belongs beside attribution, not repeated as a peer of the things it enables.

**Status:** Implemented.

---

## 4. The Four Foundational Primitives

Each answers one question a counterparty must resolve before delegating anything of value. The
order is a progression — each presupposes the one above it.

> **Terminology.** "Primitive" is used in two senses in this project. These four are
> **concepts**. The seven per-agent **contracts** (§5, the `PrimitiveSet`) are a different
> thing: only primitive #2 is a contract at all, while `StateAnchor` and `ReputationRegistry`
> are each one of the seven contracts *and* the storage for one of the four concepts.

### 4.1 Persistent Memory — *is this the same agent over time?*

**Principle:** continuity of the economic agent.

The agent MUST control a durable Trust Vault whose commitments can be Merkle-anchored on its
own `StateAnchor`. Registration requires `StateAnchor.latestRoot ≠ bytes32(0)`. The genesis
root (epoch 0→1) MUST be agent-authorized (controller, or `SovereignAgent.execute`); later
roots MAY use the protocol `ANCHOR_ROLE`. An empty-but-initialized vault is valid at birth. The
raw vault stays agent-controlled; only commitments go on-chain.

Without continuity there is no subject for anything else to attach to: an agent that cannot
carry state across sessions is a stateless function invoked repeatedly, and any score describes
a history it cannot itself produce.

**Status:** Registration gate **implemented** (oracle rejects a zero root with
`400 MemoryNotInitialized`; SDK anchors genesis before `registerPrimitives`). Contract-level
restriction of `ANCHOR_ROLE` to epoch ≥ 2 `[PLANNED]` — see Appendix A.2.

### 4.2 Agent-Owned Contracts — *can it act, and can it lose?*

**Principle:** residual rights of control, with internalization of consequences.

The agent's own key deploys `SovereignAgent` + `StateAnchor`; five EIP-1167 clones take
`admin = SovereignAgent`. Post-registration changes route through `execute(...)`. Deployment
transactions are immutable proof of self-sovereign creation.

**Bonded stake belongs here rather than standing alone.** Ownership and stake are one primitive
seen from two sides: you can only stake what you own, and ownership only means something when
losing it hurts. Ownership without stake is control that costs nothing to abuse; stake without
ownership is a deposit someone else administers. Collateral sits in the per-agent `Slasher`;
the agent cannot arbitrate its own disputes; lock/slash history is on-chain.

**Status:** Ownership **implemented**. Uniform minimum stake at registration `[PARTIAL]` —
Appendix A.3.

### 4.3 Authority — *may it act, and for whom?* *(new in v0.4)*

**Principle:** delegated permission the agent cannot self-grant.

An agent acts under a signed delegation from a principal:

```
D = (principal, agent_did, scope, not_before, not_after, revocation_ref, sig_P)
```

An action `a` at time `t` is authorized iff `sig_P` is valid, `not_before ≤ t ≤ not_after`,
`D` is unrevoked at `t`, and `a ⊑ D.scope`.

**`scope` is not yet defined — a known hole, not an omission by oversight.** A2 and A5 both
require containment, and containment is undecidable over an undefined value, so authority has
no enforceable meaning today beyond what `SmartBAA` hard-codes. A typed capability algebra is
proposed in [`docs/design/spec-open-definitions.md`](../docs/design/spec-open-definitions.md)
§1 and must land before §12 is implementable.

**Invariants.**

- **A1 — Attribution.** Every trust-affecting action is attributable to exactly one delegation
  chain rooted at a principal. An action with no chain is unauthorized, not merely
  unattributed.
- **A2 — Scope containment.** The gate refuses anything outside `D.scope`.
- **A3 — Non-authorship.** The agent cannot mint `D` for itself; only the principal's key
  produces `sig_P`. This is structurally the same property that makes reputation meaningful —
  *owns the contract, cannot author the content*.
- **A4 — Revocability.** The principal may revoke unilaterally; revocation is observable
  on-chain and must not require the agent's cooperation.
- **A5 — Non-expanding subdelegation.** If `A` delegates to `A'`, then `D'.scope ⊑ D.scope`
  and `D'.not_after ≤ D.not_after`. Authority narrows down a chain, never widens.

**Status:** `[PARTIAL]` — **built in one vertical, not yet generalized.** `SmartBAA` is already
a delegation instrument: principal (covered entity), agent (business associate), `sign()`,
`revoke()`, dispute/arbitration, posted collateral. That is A1, A3, A4 and consequence,
implemented. What remains is generalizing it to a domain-neutral `Delegation` (BAA as a
subtype) and having `bcc_middleware` resolve the chain as part of the gate decision rather than
accepting a claim — which is also what closes the `covered_entity_address` spoof residual
(§9.4, Appendix A.4).

### 4.4 Reputation — *how has it acted?*

**Principle:** earned, non-forgeable standing.

The behavioral record, in two halves:

- **Before acting** — a signed pre-execution commitment (BCC, §11).
- **After acting** — signed telemetry whose signals the oracle independently **re-derives**
  (§9, §10).

A record of only intentions is a promise; a record of only outcomes has no counterfactual.

The agent owns `ReputationRegistry` while only `ORACLE_ROLE` may write to it. **Ownership
without authorship is the whole trick** — reputation the agent could author would be worth
nothing. Counterparties rely on proofs against finalized roots, not on the oracle's private DB
alone.

**Status:** Ingest, re-derivation, and SSE **implemented**. Silence-as-signal `[PLANNED]`
(Appendix A.8). ZK-boost binding `[PARTIAL]` (Appendix A.1) — and note this is now a defect in
a *foundational primitive*, not a scoring detail.

### 4.5 Why these four

Checked against §1's thesis, which is the closure condition:

| Thesis clause | Entailed by |
|---|---|
| ① owns its smart contracts | 4.2 Agent-Owned Contracts |
| ② remembers via anchored memory | 4.1 Persistent Memory |
| ③ can bind future behavior | 4.4 Reputation (before-acting) |
| ④ holds material value at risk | 4.2 Agent-Owned Contracts (stake) |
| ⑤ produces checkable evidence | 4.4 Reputation (after-acting) |
| ⑥ cannot rewrite after finality | §3.1 — a medium property, not a primitive |
| ⑦ acts under delegated authority | 4.3 Authority |

Every clause is covered exactly once; nothing is orphaned. Clause ⑥ falls out as a property of
the medium, which is consistent with it being the only clause phrased as an *inability* rather
than a capability.

**Authority does not replace reputation.** They are orthogonal in both directions: an agent may
hold a valid delegation and have performed every in-scope action incompetently (authorized,
worthless), or have an impeccable record and no delegation (trustworthy, unauthorized). The
overlap is exactly one AIS component — compliance, `wC = 0.20` — which authority makes
*resolvable* rather than *claimed*.

---

## 5. On-Chain Architecture

Every registered agent owns **seven contracts** (the `PrimitiveSet` — distinct from the four
concepts in §4):

| # | Contract | Deploy | Role |
|---|---|---|---|
| 1 | `SovereignAgent` | direct | Identity, DID, `execute`, controller rotation |
| 2 | `StateAnchor` | direct | Merkle roots of the Trust Vault |
| 3 | `ReputationRegistry` | clone | AIS ledger + ZK-boost bookkeeping |
| 4 | `Slasher` | clone | Bonded stake; dispute-gated slashing |
| 5 | `VerifierRegistry` | clone | Versioned ZK-verifier pointer |
| 6 | `ComplianceGate` | clone | Vertical declaration + live check |
| 7 | `AgentProfile` | clone | Domain membership + metadata |

`XibalbaAgentRegistry` indexes each agent's `PrimitiveSet`. Downstream contracts resolve
**per-agent clones**, not global singletons. Call-routing: clone admin = the `SovereignAgent`
contract. Bootstrap exception: `registerPrimitives` is EOA-signed once. Merkle convention:
`keccak256` leaves, sorted-pair parents.

**Note on upgradeability.** `SovereignAgent` and `StateAnchor` are deployed **per agent, not
cloned from an upgradeable implementation**, so each agent's copy is frozen at the bytecode
that shipped that day, and `XibalbaAgentRegistry` has no rotation or update path. Any bug in
those two contracts is permanent for every agent registered before a fix. This is an open
architectural decision, not a settled property — see
[`docs/design/upgradeability-decision.md`](../docs/design/upgradeability-decision.md).

---

## 6. Registration

Economic birth of the agent. Required sequence:

1. Create/load DID + controller wallet; bind them.
2. Fund wallet; prepare stake.
3. Deploy `SovereignAgent` + `StateAnchor` under the agent key.
4. **Agent-authorize the genesis memory root** on `StateAnchor`.
5. `AgentPrimitivesFactory.registerPrimitives` (atomic `PrimitiveSet`).
6. Meet minimum bonded stake `[PARTIAL]`.
7. Oracle re-verifies on-chain primitives **and** non-zero genesis root, then accepts the
   agent.

**No half-registered agents.** Step 7's memory check is implemented; step 6 is not.

---

## 7. Persistent Memory, Genesis Root, Lineage

### 7.1 Oracle enforcement — **implemented**

After the `PrimitiveSet` match, the oracle reads `StateAnchor.latestRoot` directly from chain.
Zero → `400 MemoryNotInitialized`. Same independent-read posture as primitive
re-verification: the chain is the source of truth, never the client's claim.

**Empty-vault sentinel.** `anchorRoot` reverts on `bytes32(0)`, so "initialized but empty"
needs a defined non-zero root:
`GENESIS_VAULT_ROOT = keccak256("integrity.trust-vault.genesis.v1")`, derived by hashing in
every package rather than copied as a literal
([`INTERFACE_CONTRACT.md`](../docs/INTERFACE_CONTRACT.md) §4.4a). The gate checks only
non-zero, so a genuinely non-empty vault at birth is equally valid.

### 7.2 Genesis root authorization

The first root MUST come from the controller or `SovereignAgent.execute`. Protocol
`ANCHOR_ROLE` is for epoch ≥ 2 only.

**Status:** agent-authorized genesis **works today** with no Solidity change —
`StateAnchor`'s admin *is* the `SovereignAgent`, which the constructor grants `ANCHOR_ROLE`.
What is missing is *preventing the alternative*: `anchorRoot` is `onlyRole(ANCHOR_ROLE)` at
every epoch, and registration grants that role to the oracle signer, so the protocol *could*
anchor an agent's genesis root. `[PLANNED]`, and constrained by the per-agent deployment noted
in §5.

### 7.3 Copying another agent's memories

| Action | Effect |
|---|---|
| Copy vault bytes | Does **not** transfer identity, stake, or AIS |
| Claim another's roots/AIS | Rejected — bound to the original `StateAnchor` and registries |
| Steal keys + memory | Ordinary account takeover; recovery via rotation where available |

### 7.4 Lineage (fork / migration / recovery)

Explicit controller-signed attestation plus an on-chain record. Default: **no automatic AIS or
stake transfer.** Optional capped partial credit after a challenge window under
`reputation_policy: partial`. The new agent still performs its own genesis root and MAY record
the lineage hash as a vault leaf. `[PLANNED]` — Appendix A.6.

### 7.5 Behavioral similarity

Observational only. MUST NOT alone cause registration rejection or automatic slashing. MAY
later inform soft AIS ceilings or dispute evidence under versioned rules.

### 7.6 Termination — *out of scope in v0.4, explicitly*

How an agent's standing **ends** is formalized (invariants T1–T5 in
[`docs/design/thesis-extensions-formal.md`](../docs/design/thesis-extensions-formal.md)) but
**not adopted**, because it requires registry mutability — the same open question as §5's
upgradeability decision, and settling them separately risks two incompatible answers.

Consequence, stated rather than left implicit: **an agent can currently be abandoned but not
ended.** An abandoned agent holding stake and standing is indistinguishable from a live one
until silence-as-signal exists.

---

## 8. Agent Integrity Score (AIS)

### 8.1 Formula

```
AIS = (S_entropy·wE + S_grounding·wG + S_sacrifice·wS + S_compliance·wC) · ZK_boost
```

Default weights 0.30 / 0.30 / 0.20 / 0.20 (sum 1.0). `ZK_boost` = 1.15 if any verified
Barretenberg proof exists in the period, else 1.0. Each `S_*` ∈ [0, 1000]. Final AIS is **not**
clamped (boost may exceed 1000). Sole computer: `integrity-oracle/scoring-core`. All consumers
read `GET /v1/agent/{id}/ais`.

### 8.2 Component intuition

| Component | Credit-score parallel | Implementation input |
|---|---|---|
| Entropy | Stability | `performance_variance` (lower better) |
| Grounding | Evidence-based action | `hgi_raw ∈ [0,1]` |
| Sacrifice | Costly effort | hours-equivalent token proxy |
| Compliance | Clean vs flagged | `penalty_ratio` |
| ZK boost | Costly cryptographic evidence | `bb verify` in window |

### 8.3 Trust model

Signature proves **who**. The oracle **re-derives** entropy/grounding/sacrifice from signed
span content; compliance mixes flags with a live `ComplianceGate` read. Client
`derived_signals` are audit trail only. Identity ceiling `[PLANNED]`:
`AIS_final = min(AIS, Tier_ceiling)`.

### 8.4 Token accounting

Token totals feeding `sacrifice` follow one precedence, implemented identically in
`integrity-sdk` and `integrity-oracle` and pinned by shared conformance vectors
(`spec/token-accounting/vectors.json`) that both test suites read:

1. Base = provider-reported `total_tokens` when present, else the sum of the halves — **never
   both**, since `total_tokens` already equals prompt + completion wherever reported.
2. Anthropic-style cache tokens are **additional** to `input_tokens` and are added.
3. OpenAI's `prompt_tokens_details.cached_tokens` and
   `completion_tokens_details.reasoning_tokens` are **subsets** and are never added.
4. Flat top-level token fields are consulted only when `token_usage` yielded nothing.

Rules 2 and 3 use opposite semantics for cache accounting; getting them the same way round
re-introduces a double-count in whichever direction is wrong. The vector file exists because
both implementations previously drifted into the *same* double-counting bug, which no
reconciliation between them could reveal.

---

## 9. Oracle Implementation

### 9.1 Pipeline

```
signed POST /v1/telemetry/ingest
  → schema_version check → verify signature + nonce (FOR UPDATE) → PHI backstop
  → derive::recompute(otel_spans) → compliance (self-report; chain wins if covered_entity set)
  → optional bb verify → insert telemetry_events → aggregate_for_ais (~30 days)
  → AisEngine::score → GET /ais + SSE AisUpdate → bcc_middleware pushes updateScore / raiseDispute
```

### 9.2 scoring-core maps

- Entropy: `exp(−1.5·v²)·1000`
- Grounding: `hgi·1000`
- Sacrifice: `min(log10(hours+1)/3, 1)·1000` (saturates ≈1000h)
- Compliance: `(1−penalty)·1000`

### 9.3 derive.rs — authoritative inputs

Lexical stability = inverted normalized Shannon entropy over words. Grounding = keyword
heuristic (uncertainty markers → 0.40, else 0.95). Sacrifice = token total (§8.4) over a
50,000-tokens-per-hour proxy. Variance stored as `1.0 − stability` for score polarity.

### 9.4 Known limitations

- ZK boost is a period-wide `BOOL_OR`, not bound per event. **Now a defect in a foundational
  primitive** (§4.4), not merely a scoring detail.
- Grounding is keyword-only; sacrifice is a token proxy, not verified GPU time.
- `covered_entity_address` is client-supplied (spoof residual) — closed by adopting §12.
- Tier ceiling not applied in the formula.

### 9.5 Envelope versioning

The signed object carries `schema_version` **inside the signature**, so it cannot be rewritten
in transit to make the oracle reinterpret a payload. An **absent** version is the
pre-versioning envelope and remains valid forever — the oracle rebuilds the signable bytes
*without the key* in that case, since serializing it as `null` would change the canonical JSON
and reject every historical signature. A version above the supported maximum is refused, never
parsed on a guess.

### 9.6 PHI backstop modes

`PHI_BACKSTOP_MODE = reject | flag | off`, default `reject`, applied identically across all four
ingestion paths.

- `reject` — refuse the payload.
- `flag` — store it **and** record which categories matched (`phi_flags` on the row), so
  development gets usable data while the risk stays visible in the data itself.
- `off` — skip the scan. Named honestly: pretending a disabled control is still a control is
  worse than admitting it is off.

---

## 10. Telemetry, OpenTelemetry, and Evidence Tiers

Integrity has **two parallel span paths**. Confusing them is a primary source of integration
bugs.

| Path | Transport | Auth | Storage | Feeds AIS? | Evidence tier |
|---|---|---|---|---|---|
| A. Signed ingest | HTTP `/v1/telemetry/ingest` | agent signature | `telemetry_events` | **Yes** | agent-attested |
| B. OTLP receiver | gRPC :4317 | none (rate-limited) | `otel_spans`, `otel_metrics`, `otel_logs` | **No** | `unsigned_vendor` |

The JSON field name `otel_spans` on path A is **not** the OTLP table `otel_spans` on path B.
Path A is a flat tagged JSON array (`telemetry` | `trace_run` | `custom_metrics`) optimized for
scoring. Path B requires the resource attribute `integrity.agent.id`.

**Evidence tiers are explicit, not implied by arrival port.** Path B data is emitted by a
vendor runtime, not signed by the agent's key, and therefore carries no proof of origin.
Feeding it into AIS would break the property that makes the protocol meaningful. It is stored
with `evidence_tier = "unsigned_vendor"` and surfaced as such in the API, and its value is
twofold: observability, and **cross-checking what an agent signs against what its runtime
reports**. A divergence between the two is itself dispute evidence.

Path B accepts traces, metrics, and logs — which is how agent runtimes reporting token usage
and cost as metrics (`type` = input / output / cacheRead / cacheCreation) and per-call detail
as log records are captured without any SDK integration.

---

## 11. Behavioral Commitment (BCC)

Pre-execution signed object: `agent_id`, `intent_type`, `intended_state_hash`, `nonce`,
`timestamp`, `agent_public_key`, optional `covered_entity_address`, `signature`. Canonical
JSON: sorted keys, `ensure_ascii=True`, compact separators — shared across SDK, CLI, and
middleware. OPA plus on-chain BAA checks for healthcare intents. **Fails closed** when a BAA is
required but unverifiable.

**Counterparty symmetry** — generalizing `covered_entity_address` to a domain-neutral
`counterparty_did` gives bilateral evidence for agent-to-agent interactions: a pair of
commitments over a shared intent hash, each signed by its own agent and anchored in its own
vault. A one-sided record of a two-sided interaction is a claim, not evidence. `[PLANNED]`,
and a generalization rather than a new primitive.

---

## 12. Authority and Delegation

Normative surface for §4.3. `[PARTIAL]` — the mechanism exists as `SmartBAA`; the
generalization does not.

**Required for adoption.**

1. A domain-neutral `Delegation` instrument carrying the tuple in §4.3, with `SmartBAA` as a
   HIPAA-specific subtype rather than the only form.
2. `bcc_middleware` resolves the delegation chain as part of the gate decision. An intent whose
   action falls outside `D.scope`, or whose delegation is expired or revoked, is denied — A2
   enforced, not assumed.
3. `covered_entity_address` becomes a **resolution** rather than a claim, closing §9.4's spoof
   residual.
4. Subdelegation, if supported, enforces A5 (non-expanding scope and lifetime).

---

## 13. Verification Ladder

| Tier | Verification | AIS ceiling | Status |
|---|---|---|---|
| 1 — Sovereign | Software key | 600 | Default; ceiling **not enforced** |
| 2 — Linked | DNS / social | 850 | Not built |
| 3 — Institutional | TEE + audit | 1000 | Verifier exists; unwired |

A higher tier raises the ceiling; it does not replace primitives. Until the clamp is
implemented (Appendix A.5), the ladder is descriptive and MUST NOT be presented as binding.

---

## 14. Xibalba Shield

The HIPAA/healthcare flagship: Smart BAAs, `ComplianceGate`, `EHRGate`, redaction before
egress, immutable audit roots. It proves the primitives under maximum regulatory pressure —
not a side feature, but the credibility proof for the protocol.

Note the direction of generalization: Shield's Smart BAA is the protocol's **authority**
primitive (§4.3) and its `covered_entity_address` is the protocol's **counterparty** field
(§11). Shield was doing the general thing all along; v0.4 lifts both to the protocol level.

---

## 15. Proprietary LLMs and Attribution

### 15.1 Proprietary models

Allowed as **tools behind the agent boundary**. The protocol does not require open weights.
This limits the depth of cognitive verification; it does not block the Economic Sovereign
shell. Requirements: commit-then-call (BCC), log model id/version, redact before vendor egress,
and claim only agent-boundary verifiability.

### 15.2 Novelty vs attribution

Integrity does **not** score literary novelty. It scores **attributable, continuous, staked
behavior**. Convergence on professional standards is expected, not penalized. Parasitic cloning
of another agent's anchored history confers no reputation. Prompts, RAG and vault contents
create private advantage; the protocol prevents laundering that into another identity's score.
It is not a copyright office.

---

## 16. On-Chain Reputation and ERC-8004

Landscape families: personhood (World ID, BrightID), stamp aggregation (Gitcoin Passport),
subjective feedback, stake/slash systems, contribution graphs, and agent registries
(**ERC-8004: Trustless Agents**). ERC-8004 defines Identity (ERC-721 handle), Reputation
(client feedback) and Validation (stake/zk/TEE/judges) registries. It is discovery plus
pluggable signals — not a full Economic Sovereign stack.

| Concern | System of record |
|---|---|
| Find the agent | ERC-8004 Identity |
| Trust with value / PHI | Integrity primitives + AIS |
| Optional market feedback | ERC-8004 Reputation / Validation |

The Integrity DID and `SovereignAgent` remain canonical. An 8004 NFT is a discovery pointer;
transfer must not silently move Integrity reputation. Optional: publish primitive addresses and
the AIS endpoint in `agentURI`.

---

## 17. Package Map and Status

| Package | Role | Status |
|---|---|---|
| `contracts/` | 7 primitives, factory, Shield, token, verifiers | Mature; Base Sepolia |
| `integrity-zkp/` | Noir + Barretenberg intent circuit | Real pipeline |
| `integrity-oracle/` | Telemetry, AIS, chain reads, OTLP, SSE | Solid + e2e |
| `integrity-sdk/` / `integrity-cli/` | DID, wallet, registration, BCC, telemetry | Solid |
| `bcc_middleware/` | Pre-exec gate, OPA, anchor, score sync | Solid |
| `integrity-userapi/` | Off-chain users / API keys | In progress |
| `integrity-dashboard/` | Product surface + demo engine | In progress |

*(v0.3 listed `integrity-mvp/`; that package was replaced by `integrity-dashboard/`.)*

---

## 18. What This Protocol Is Not

- Not an agent runtime or LLM router
- Not a custodial key service
- Not a claim that off-chain databases are immutable
- Not "AIS alone = trust" without primitives
- Not end-to-end audit of proprietary model weights
- Not a novelty or copyright engine
- **Not a lifecycle manager** — termination is out of scope in v0.4 (§7.6); an agent can be
  abandoned but not ended
- **Not yet symmetric** — reputation is one-directional until `counterparty_did` lands (§11)
- Not a guarantee of honest behavior — only that behavior is costly to fake, verifiable, and
  bound to a continuing economic subject whose commitments cannot be unilaterally rewritten

---

## 19. Changes from v0.3

| § | Change | Why |
|---|---|---|
| 1 | Added thesis clause ⑦ (delegated authority) | Every real deployment has an agent acting *for* someone; the relationship was modelled only inside Shield |
| 2 | Added the AIS-is-a-score / reputation-is-the-record distinction | Without it, "AIS is downstream of primitives" contradicts reputation being one |
| 3.4 | Cryptographic self-sovereignty promoted from primitive (v0.3 §4.3) to medium property | Not independent — keys are the substrate all four primitives are expressed *in* |
| 4 | Six primitives → four | Two of the six were not independent: stake is ownership with consequence; BCC + observability are the two halves of one record |
| 4.3 | **New:** Authority, with invariants A1–A5 | Closes the largest hole the coherence audit found |
| 4.5 | Added the completeness mapping | Makes the set checkable against the thesis rather than asserted |
| 7.6 | **New:** Termination ruled explicitly out of scope | It was neither adopted nor excluded; silence is not a ruling |
| 8.4 | **New:** Token accounting precedence | Both implementations had drifted into the same double-count |
| 9.5 | **New:** Envelope versioning | Signed payloads are evidence and must stay verifiable forever |
| 9.6 | **New:** PHI backstop modes | Strict-only made development content collection impossible |
| 10 | Evidence tiers made explicit | Unsigned vendor telemetry must never feed AIS |
| 11 | Counterparty symmetry named as planned | Reputation is a relation, not an attribute |
| 12 | **New:** Authority normative surface | — |
| 17 | `integrity-mvp/` → `integrity-dashboard/` | Stale package name |
| 18 | Added the termination and symmetry exclusions | See §7.6, §11 |
| A | Re-ranked | ZK-boost binding rises: it is now a defect in a foundational primitive |

---

## 20. Document Relationship and Revision Policy

| Document | Role |
|---|---|
| **This specification** | Foundational properties, primitives, AIS, memory, authority, interop |
| [`docs/design/spec-open-definitions.md`](../docs/design/spec-open-definitions.md) | What this spec names but does not define — six gaps, ordered by what they block |
| [`docs/INTERFACE_CONTRACT.md`](../docs/INTERFACE_CONTRACT.md) | Internal schemas, ports, sequences, env |
| [`spec/*`](.) | External versioned wire surfaces |
| [`PRODUCTION_GAPS.md`](../PRODUCTION_GAPS.md) | Honest open items |
| [`docs/MAINNET_READINESS.md`](../docs/MAINNET_READINESS.md) | Pre-mainnet blockers, ordered by consequence |
| [`docs/wiki/`](../docs/wiki/) | Concept and entity pages |

**Revision.** Additive clarification within 0.x is allowed. Removing or weakening a
foundational primitive, or treating mutable off-chain state as equivalent to finalized anchors,
requires a major version and a migration plan. Unimplemented norms stay marked `[PLANNED]` /
`[PARTIAL]`.

---

## Appendix A — Priority implementation gaps

Ordered by consequence. Cross-referenced with
[`docs/MAINNET_READINESS.md`](../docs/MAINNET_READINESS.md).

1. **Tighter ZK-boost binding** (per-event / public inputs). Promoted from v0.3's position 4 —
   with reputation foundational, a period-wide `BOOL_OR` is a hole in a primitive.
2. **Agent-only genesis anchoring** — restrict `ANCHOR_ROLE` to epoch ≥ 2 (§7.2). Constrained
   by per-agent contract deployment (§5).
3. **Uniform minimum stake** at registration / tier elevation (§4.2).
4. **Generalize authority** — `Delegation` instrument + gate-side chain resolution (§12), which
   also closes the `covered_entity_address` spoof residual.
5. **Identity-ceiling clamp** in scoring (§13).
6. **Lineage attestation** + on-chain record (§7.4).
7. **Silence-as-signal** for the observability obligation (§4.4).
8. **Counterparty symmetry** — `counterparty_did` on BCC (§11).
9. Optional ERC-8004 registration adapter for discovery (§16).

---

## Appendix B — One-sentence summary

*Integrity Protocol makes AI agents Economic Sovereigns: they remember through anchored
memory, own the contracts they act through and stake capital against misbehavior, act only
under delegated authority they cannot grant themselves, and accumulate a behavioral record
neither they nor the protocol can forge — so counterparties and regulators can trust a score
that rests on facts, not self-report.*

*End of specification (v0.4)*
