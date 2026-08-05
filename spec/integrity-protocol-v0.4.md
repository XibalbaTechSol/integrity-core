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
14. Integrity Health
15. Proprietary LLMs and Attribution
16. On-Chain Reputation and ERC-8004
17. Package Map and Status
18. What This Protocol Is Not
19. Changes from v0.3
20. Document Relationship and Revision Policy
21. Financial Action & Payment-Protocol Interop *(added 2026-08-01)*
22. Session Integrity, Drift & Autonomous Termination *(added 2026-08-01)*
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
one place that relationship was modelled — Integrity Health's Smart BAA — was treated as a
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
AIS_raw = (S_entropy^wE · S_grounding^wG · S_sacrifice^wS · S_compliance^wC) · ZK_boost
AIS_final = min(AIS_raw, Tier_ceiling)
```

Default weights 0.30 / 0.30 / 0.20 / 0.20 (sum 1.0). `ZK_boost` = 1.15 if any verified
Barretenberg proof exists in the period, else 1.0. Each `S_*` ∈ [0, 1000]. This is a
weighted **geometric** mean: any zero component makes `AIS_raw` zero, so strength on one
axis cannot hide total failure on another. The effective identity tier caps the final score
at 300 / 600 / 850 for Tiers 0 / 1 / 2; Tier 3 returns the raw score, which may exceed 1000
after a ZK boost. Sole computer: `integrity-oracle/scoring-core`. All consumers read
`GET /v1/agent/{id}/ais`; they do not reconstruct the formula from component fields.

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
`derived_signals` are audit trail only. The identity ceiling is built and enforced by
`scoring-core::AisEngine::score_with_tier`; the backend resolves the agent's effective
verification tier before computing `AIS_final`.

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
| 1 — Sovereign | Software key + on-chain primitive match | 600 | Registration floor; enforced |
| 2 — Linked | DNS TXT or GitHub namespace proof | 850 | Built; expiring evidence |
| 3 — Institutional | AWS Nitro remote attestation | No post-boost cap | Built; expiring evidence |
| 3 — Institutional KYC | Provider-signed document + liveness + sanctions/PEP receipt | No post-boost cap | Built; expiring, provider-neutral evidence |

A higher tier raises the ceiling; it does not replace primitives. Effective tier is
derived from the registration floor plus active, unexpired, unrevoked evidence on every
read. Agents MAY revoke evidence using a fresh Oracle nonce and a signature from their
registered Ed25519 key; the evidence row remains as an audit record and the tier drops
immediately. A KYC receipt grants Tier 3 only when it is nonce-bound, signed by an
operator-configured Ed25519 provider key, uses the `open_source_kyc_v1` assurance profile,
and affirms document authenticity, biometric liveness, and sanctions/PEP screening. The
Oracle stores only opaque receipt evidence and MUST NOT receive or persist raw PII.

---

## 14. Integrity Health

The HIPAA/healthcare flagship: Smart BAAs, `ComplianceGate`, `EHRGate`, redaction before
egress, immutable audit roots. It proves the primitives under maximum regulatory pressure —
not a side feature, but the credibility proof for the protocol.

Note the direction of generalization: Integrity Health's Smart BAA is the protocol's **authority**
primitive (§4.3) and its `covered_entity_address` is the protocol's **counterparty** field
(§11). Integrity Health was doing the general thing all along; v0.4 lifts both to the protocol level.

### 14.1 Two products, one stack *(decision, 2026-08-01)*

As of 2026-08-01, the name "Xibalba Shield" named two things that could not be conflated;
the split below was executed to resolve that:

1. **The HIPAA/healthcare vertical above** — renamed **Integrity Health**
   (`contracts/src/health/*`), the on-chain BAA gate, healthcare `intent_type`s in
   `policies/bcc.rego`. Lives **in this repo**, always has.
2. **A planned device/network security product** — an endpoint agent (kernel/OS sensor, policy
   engine, LLM/agent guardrail hooks) that discovers and constrains AI agents on a machine, and
   *produces* the telemetry Integrity Core scores. This does not exist yet in any repo.

They compose vertically and must live in **separate repositories**:

```
┌──────────────────────────────────────────┐
│  Integrity Protocol (this repo)           │  Trust, compliance, AIS, anchoring,
│  contracts/ · integrity-oracle/ · zkp/    │  audit export. Vertical-agnostic.
│  integrity-sdk/ · bcc_middleware/         │
├──────────────────────────────────────────┤
│  xibalba-shield (new repo)                │  Device/network enforcement.
│  endpoint agent + kernel sensor           │  Imports integrity-sdk to emit
│  + policy engine + guardrail hooks        │  signed evidence into Core.
└──────────────────────────────────────────┘
```

**Why separate repos, not a monorepo package.** Integrity Core's job is defining primitives and
computing AIS; a change to the Merkle convention or the AIS formula must never silently change
because someone was iterating on kernel-sensor code in the same tree. The two also have
genuinely different build/release cadences, threat models, and — per §14.2 — different
compliance postures (Core never touches raw PHI or process telemetry; Shield's endpoint agent
necessarily observes far more of a device than anything in this repo does today). This mirrors
the healthcare vertical's own existing shape: `contracts/src/health/*` already sits **above**
`contracts/src/oracle/*`, consuming primitives rather than reimplementing them, and never the
reverse.

**What Shield consumes from Integrity Core, and how.** The endpoint agent imports
`integrity-sdk` the same way any other agent runtime does — DID assignment, BCC signing, Merkle
batching (§11) — with no privileged access and no new primitive. Its events are ordinary BCC
commitments whose `intent_type` falls in the security-event taxonomy (§21.2); its evidence is
ordinary reputation (§4.4); its audit export is the existing evidence-export path
(`docs/design/evidence-export.md`), not a new mechanism. The `bcc_middleware` design already
anticipated a kernel-telemetry hook point — see
[`docs/ENTERPRISE_ADOPTION.md`](../docs/ENTERPRISE_ADOPTION.md) Lever 1's egress-sidecar form
factor, which is the same shape Shield's endpoint agent needs.

**What Shield must build that Core does not provide**, because it is a different class of
concern entirely: kernel/OS sensors (eBPF on Linux; ETW/native APIs on Windows/macOS), a local
policy engine capable of running offline, LLM/agent guardrail hooks at inference boundaries, and
device-level enforcement (block, contain, isolate). None of this belongs in `bcc_middleware`,
which authorizes and anchors — it has never enforced anything at the OS level and should not
start.

**Status (updated 2026-08-04):** `XibalbaTechSol/xibalba-shield` exists and is no longer
`[PLANNED]` in full. Real and tested: event schemas, policy rule schema, Policy Engine, Agent
Core, all 6 guardrail hooks, the Integrity Exporter (live-verified against a real
`bcc_middleware` — real signed BCC commitment, real Merkle-batch admission), the CLI
(`shield run` is a real sensor-to-exporter entry point), and local policy/device config loading
with hot-reload — 63 tests passing. Of the three planned Linux eBPF sensors, 2 of 3
(process-exec, file-write) are live-verified on real kernel probes; the third (TCP-connect) is
blocked on a confirmed BCC/kernel version-skew problem, not a code defect. Not yet built:
Windows/macOS sensors, the network sensor (deferred past v1 by this product's own spec §9),
PHI-tagging/content classification (§6), and compliance reporting (blocked upstream on this
repo's own `docs/design/evidence-export.md`). Full technical specification:
[`spec/xibalba-shield-v1.md`](xibalba-shield-v1.md) — that document's own top-of-file status
banner still says `[PLANNED]`/"no code... exists in any repository," which is now stale; it
predates this update and hasn't been revised to match. Current implementation status lives in
`xibalba-shield`'s own `README.md`, not duplicated further here. Product/roadmap framing:
[`docs/ENTERPRISE_ADOPTION.md`](../docs/ENTERPRISE_ADOPTION.md) Lever 7.

### 14.2 Privacy posture, stated precisely

Because this section previously described only the healthcare-vertical Shield, one fact is
worth stating explicitly now that a device agent is planned: **Integrity Core's PHI backstop
(§9.6) governs telemetry submitted to the oracle — it says nothing about what an endpoint agent
is permitted to observe on a device.** That is Shield's own design obligation
(`spec/xibalba-shield-v1.md` §6), not something this protocol enforces or can enforce from the
oracle side. Conflating "the oracle rejects raw PHI in ingest payloads" with "the device agent
never sees PHI" would be exactly the kind of silent-mock claim this repo's ground rule forbids.

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
| `contracts/` | 7 primitives, factory, Integrity Health, token, verifiers | Mature; Base Sepolia |
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
| 1 | Added thesis clause ⑦ (delegated authority) | Every real deployment has an agent acting *for* someone; the relationship was modelled only inside Integrity Health |
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

**Post-publication additions (2026-08-01).** §21 (Financial Action & Payment-Protocol Interop)
and §22 (Session Integrity, Drift & Autonomous Termination) were added after v0.4's initial
publication, under this section's own revision policy below: both are additive — no primitive
is removed, weakened, or reinterpreted, and everything added is `[PLANNED]` — so they land as
in-place amendments to v0.4 rather than a version bump. §14 was expanded (§14.1, §14.2) to
record the Xibalba Shield repo-split decision; no other existing section changed.

**Normative correction (2026-08-04).** §8.1's initial in-repo transcription retained
the superseded arithmetic AIS expression even though `integrity-oracle/scoring-core`,
`docs/INTERFACE_CONTRACT.md` §4.3, and the compiled AIS wiki had already moved to the
weighted geometric volume model. §8.1 now names the executable geometric form and the
built Verification Ladder ceiling. This is a coherence correction: it makes the spec
describe the already-authoritative implementation and does not introduce a new scoring model.

---

## 20. Document Relationship and Revision Policy

| Document | Role |
|---|---|
| **This specification** | Foundational properties, primitives, AIS, memory, authority, interop |
| [`spec/xibalba-shield-v1.md`](xibalba-shield-v1.md) | Xibalba Shield technical specification (§14) |
| [`docs/INTERFACE_CONTRACT.md`](../docs/INTERFACE_CONTRACT.md) | Internal schemas, ports, sequences, env |
| [`spec/*`](.) | External versioned wire surfaces |
| [`PRODUCTION_GAPS.md`](../PRODUCTION_GAPS.md) | Honest open items |
| [`docs/MAINNET_READINESS.md`](../docs/MAINNET_READINESS.md) | Pre-mainnet blockers, ordered by consequence |
| [`docs/ENTERPRISE_ADOPTION.md`](../docs/ENTERPRISE_ADOPTION.md) | Adoption roadmap — strategic levers, incl. Shield-as-product and payment interop |
| [`docs/wiki/`](../docs/wiki/) | Concept and entity pages |

**Revision.** Additive clarification within 0.x is allowed. Removing or weakening a
foundational primitive, or treating mutable off-chain state as equivalent to finalized anchors,
requires a major version and a migration plan. Unimplemented norms stay marked `[PLANNED]` /
`[PARTIAL]`.

---

## 21. Financial Action & Payment-Protocol Interop *(added 2026-08-01, all `[PLANNED]`)*

### 21.1 What this section is and is not

External research into agentic-commerce protocols (AP2, ACP, x402, MPP, Coral) and financial
regulatory expectations (EU AI Act, SR 11-7, GDPR Art. 22, BSA/AML, DORA) converges on a
structural gap: **these protocols standardize *how* an agent pays; none of them decides
*whether it is allowed to*, under whose authority, or produces regulator-grade evidence that it
did.** That gap is exactly what §4.3 (Authority) and §4.4 (Reputation) already exist to close —
this section is a **mapping and taxonomy**, not a new primitive. Nothing here adds a fifth
foundational primitive; nothing here is required for the protocol's own correctness. It exists
so a financial `intent_type` has a stable vocabulary before ad hoc strings proliferate.

**Vocabulary reconciliation, stated once so it is not restated per subsection:** what external
literature calls a "Mandate" is this protocol's **Delegation** (§4.3, §12) composed with a
**BCC commitment** (§11) whose `intended_state_hash` commits to the mandate's terms — not a new
object. What external literature calls an "Action Receipt" is the **existing pairing** of a
`bcc_middleware` policy decision and its resulting `anchor_events` row, already linked by leaf
hash (`docs/design/evidence-export.md`) — formalized here as a named concept, not a new
mechanism. Reusing existing primitives under new names would be the wrong move; naming what
already exists so it interoperates with external schemas is the right one.

### 21.2 Financial action taxonomy (extends `intent_type`, §11)

`BCC Commitment.intent_type` is already a free-form string (§4.2 of
[`docs/INTERFACE_CONTRACT.md`](../docs/INTERFACE_CONTRACT.md)); healthcare intent types
(`EMR_WRITE`, `DISPENSE_MEDICATION`, …) are the existing precedent for a domain-specific
subtaxonomy living in that one field rather than a new schema field. Financial actions follow
the same pattern with a stable, versioned enum so audit exports (§21.4) and policy packs
(`docs/ENTERPRISE_ADOPTION.md` Lever 3) can pattern-match reliably:

| `intent_type` | Meaning |
|---|---|
| `payment_authorize` | Hold / auth only, no capture |
| `payment_capture` | Capture a prior authorization |
| `payment_transfer` | Push payment (ACH, wire, RTP, card) |
| `payment_stablecoin` | On-chain stablecoin payment (x402-class) |
| `payment_escrow_lock` | Escrow deposit (Coral-class) |
| `payment_escrow_release` | Escrow release on condition |
| `payment_refund` | Full/partial reversal |
| `payment_dispute` | Chargeback / dispute-side event |
| `fx_convert` | Currency conversion |
| `limit_reserve` / `limit_release` | Internal spending-limit ledger movement |
| `wallet_sign` | Raw signing without broadcast |

`intended_state_hash` commits to the amount, asset, rail, and counterparty reference — the
receiving system decodes and validates it against the claimed `intent_type`; the oracle does
not parse payment semantics, matching its existing posture toward every other vertical.

### 21.3 Interop table: protocols this composes with

Integrity Protocol is not a settlement rail and does not compete with any row below. It is the
authorization and evidence layer a settlement action passes through first — the same relation
`ComplianceGate` already has to a healthcare action (§14).

| Protocol | What it provides | How it composes with Integrity |
|---|---|---|
| **AP2** (Google, A2A/MCP extension) | Cryptographically signed Mandates (Intent/Cart/Payment) | An AP2 Payment Mandate references this protocol's Action Receipt ID; Integrity's Delegation (§12) is the authority layer underneath the mandate, not a replacement for it |
| **ACP** (OpenAI/Stripe) | Merchant-controlled checkout orchestration | Checkout session creation is gated by a BCC commitment's policy decision before the session is created |
| **x402** (Coinbase) | HTTP 402 stablecoin micropayments | A short-lived Integrity-authorized capability accompanies the 402 flow; `payment_stablecoin` is the corresponding `intent_type` |
| **MPP** (Stripe/Tempo) | Pre-authorized spending sessions | Session spend ceilings are the same shape as Delegation's `scope` (§4.3) — a session is a bounded, revocable authorization |
| **Coral** | On-chain escrow, DIDs, immutable ledger | Escrow release condition includes a valid Integrity decision, not only Coral's own task-completion signal — `payment_escrow_lock`/`_release` |

### 21.4 Action Receipt (formalized, not new)

An **Action Receipt** is the pairing already produced today: the `bcc_middleware` policy
decision for a commitment, joined to its `anchor_events` row by leaf hash once that commitment
is anchored. `docs/design/evidence-export.md` Phase A already builds exactly this linkage.
Naming it here is what lets it map onto external audit-trail expectations (the IETF
`draft-sharif-agent-audit-trail` shape, referenced by the source research) without inventing a
parallel schema: `agent_id` → `session_id`/identity layer, `intent_type` → `action_type`,
the BCC signature + policy decision → the AAT `outcome` and reasons, the anchor tx →
non-repudiable settlement evidence. **No new field is required on the existing schemas** for
this mapping to hold — it is already there, unnamed.

### 21.5 Compliance-by-construction, mapped to what exists

| Regulatory concern | Protocol mechanism already normative |
|---|---|
| Liability / accountability chain | Delegation §4.3 (A1 Attribution, A3 Non-authorship) |
| Bounded agency / spending limits | Delegation `scope` (§4.3) — enforcement is `[PARTIAL]`, tracked in Appendix A.4 |
| Non-repudiable authorization | BCC signature + canonical JSON (§11) |
| Audit trail / traceability | Action Receipt (§21.4) via existing anchor + reputation pipeline |
| Explainability (GDPR Art. 22) | `bcc_middleware`'s `reason` field on every deny (already ships; see its module docstring) |
| KYC/AML surrogate for non-human actors | DID + continuous AIS (§8) as a behavioral baseline, not a one-time check |
| Human-in-the-loop escalation | `[PLANNED]` — no step-up/escalation channel exists in `bcc_middleware` today; distinct from shadow mode (`docs/ENTERPRISE_ADOPTION.md` Lever 2), which observes but never escalates |

**What this table is not claiming:** that the protocol is compliant with any named regime today.
Every right-hand cell not marked `[PARTIAL]`/`[PLANNED]` is an existing mechanism that a
regulated deployment's own compliance program would still need to map and attest to — this
table is a starting inventory, not a certification.

### 21.6 Status and non-goals

`[PLANNED]` in full: no payment-protocol adapter exists in any package. The taxonomy (§21.2) can
be adopted immediately since it costs nothing (`intent_type` already accepts any string); the
interop adapters (§21.3) and human-in-the-loop escalation (§21.5) require real implementation
work tracked in `docs/ENTERPRISE_ADOPTION.md`.

**Explicit non-goal:** Integrity Protocol will not become a payment rail, hold funds, or
custody keys on an agent's behalf (consistent with §18's existing "not a custodial key
service"). Settlement always happens on one of the rails in §21.3, never inside this protocol.

---

## 22. Session Integrity, Drift & Autonomous Termination *(added 2026-08-01, all `[PLANNED]`)*

### 22.1 Scope and relationship to existing gates

This section specifies **runtime, within-session** risk monitoring for long-running agent
sessions — a different timescale from everything else in this document:

| Mechanism | Timescale | Answers |
|---|---|---|
| BCC (§11) | Per-action, pre-execution | Is *this specific action* authorized? |
| AIS (§8) | Longitudinal (~30-day window) | Has this agent behaved well *over time*? |
| **Session integrity (this section)** | Continuous, within one session | Is *this session, right now*, still the session that was authorized? |

A session can pass every individual BCC check and still have drifted — its plan, tool
selection, or peer coordination diverging from what was authorized — because BCC verifies each
action in isolation and says nothing about the trajectory connecting them. This section closes
that gap. It does **not** replace BCC or Delegation as the authority mechanism (§22.6
Non-goals is explicit about this): a session with a perfect drift score but no valid Delegation
is still unauthorized, and a terminated session's prior anchored evidence remains valid under
§3.1's append-only rule.

**Design principle, stated because it is easy to violate by accident:** the LLM context window
and conversation trace are untrusted, lossy buffers. Authority for any trust-affecting action
remains in the signed Delegation and BCC commitment — never in free-form context, and never
reconstructed from a post-compaction summary.

### 22.2 Definitions

| Term | Definition |
|---|---|
| **Session** | A bound execution context: `session_id` + agent DID + active Delegation references + ephemeral scopes |
| **Termination** | Server-side end of a session: revoke ephemeral credentials, deny further BCC commitments under that `session_id`, isolate any queued work |
| **Semantic drift** | Progressive deviation of a session's goals, plan, tool use, or peer coordination from its frozen starting anchors |
| **Context contamination** | Untrusted or compacted content that dilutes or overrides pinned governance constraints |
| **`R_session`** | Calibrated composite session risk in `[0, 1]` |
| **Constraint pin** | A governance block re-asserted every turn and after every context compaction, never passed through a lossy summarizer |

### 22.3 Session risk score and action ladder

Composite risk over calibrated component scores `s̃ᵢ ∈ [0, 1]`:

```
R_session = 1 − ∏ᵢ(1 − wᵢ·s̃ᵢ)          (noisy-OR form)
```

| Component | Default weight band |
|---|---|
| Semantic / drift (§22.4) | 0.25–0.35 |
| Behavioral baseline break | 0.15–0.25 |
| Economic / rate anomaly | 0.15–0.25 |
| Auth/attestation posture | 0.10–0.15 |
| Idle / absolute session age | 0.05–0.10 |
| Policy severity (may force `R = 1.0`) | 0.20–0.40 |

**Hard overrides** (force termination regardless of `R`): a forbidden action sequence, an
explicit Delegation revocation (§4.3 A4), a missing constraint pin after compaction, or a
detected mismatch between declared and actual tool/OS-level effect ("semantic–physical gap").

**Action ladder**, gated on both risk `R` and a confidence score `C` so a low-confidence high-risk
reading does not itself trigger the most disruptive response:

| Code | Action | Trigger |
|---|---|---|
| M — Monitor | Log, raise sampling | `R ≥ τ_M` |
| S — Step-up | Require re-authorization before any settlement action | `R ≥ τ_S` |
| H — Throttle | Cut rate/notional; dry-run side effects | `R ≥ τ_H, C ≥ c_H` |
| T — Terminate session | Revoke ephemeral scope; deny further commitments | `R ≥ τ_T, C ≥ c_min` |
| K — Kill agent | T, plus identity/queue-level containment | `R ≥ τ_K, C ≥ c_min`, or hard override |

Thresholds `τ_M < τ_S < τ_H < τ_T ≤ τ_K` are tenant-calibrated, not fixed protocol constants —
a wire/on-chain/high-notional action lowers the effective terminate threshold; a read-only
action raises it. Every threshold set used for a decision MUST be recorded (its id and content
hash) on the resulting Action Receipt (§21.4) extension in §22.7, so a termination decision is
itself auditable evidence, not an opaque runtime event.

### 22.4 Semantic drift measurement

**Frozen anchors**, versioned and never silently updated: the governing charter/policy, the
session's `intent_hash` (from its BCC commitment), hard invariants, and — where available —
golden reference traces for the task class.

**Metric tiers**, cheapest-first (mirrors the existing `bcc_middleware` gauntlet's
cheapest-and-most-certain-first ordering, §9.4 of `docs/INTERFACE_CONTRACT.md`):

1. Embedding-distance to the frozen intent anchor (cosine); population-level distributional
   drift via Sliced Wasserstein or an online/windowed MMD variant — never full quadratic MMD
   against a full-day log, which does not scale.
2. Structured checks: does the current plan still entail the original intent (NLI-style
   adherence); has the tool-call graph diverged from what was declared.
3. A composite **Agent Stability Index**, `ASI = 1 − R_drift`, over the same noisy-OR form as
   §22.3, one term per drift dimension (intent, plan, tool use, memory, multi-agent
   coordination, generation timing, semantic–physical gap).
4. A judge/LLM pass, invoked **only** on a tier-1 alert to classify cause — never the sole
   authority to terminate, consistent with §22.6.

Drift crossing a warn threshold triggers Monitor; crossing a block threshold on a
settlement-class action denies that specific tool call (`BLOCK_ACTION`) without necessarily
terminating the session; sustained drift above the terminate threshold, with sufficient
confidence, terminates.

### 22.5 Context contamination mitigation

Mandatory controls for any implementation of this section:

1. **Constraint pinning** — governing policy, the session's `intent_hash`, and any kill flags
   are re-concatenated into context every turn and after every compaction; a summarizer MUST
   NOT be permitted to rewrite the pin. A missing pin post-compaction is a hard override to
   Terminate (§22.3).
2. **Typed trust labels** on every context span (`PINNED_TRUSTED`, `USER_TRUSTED`,
   `RETRIEVED_QUARANTINE`, `TOOL_OBSERVATION`, `PEER_AGENT`, `UNTRUSTED_INGRESS`) so a
   contaminated span cannot be silently treated as governance.
3. **Execution-path independence** — settlement-affecting values (amounts, counterparties) are
   read from the signed Delegation/BCC commitment, never re-derived from natural-language
   context, however persuasive. This is the session-level restatement of A3 (§4.3):
   authorization content the agent could talk itself into is authorization the agent
   authored, and A3 already forbids that.

### 22.6 Non-goals

- **Does not replace** Delegation, BCC, or their cryptographic guarantees (§4.3, §11). A
  perfect drift score never substitutes for a valid, unrevoked Delegation.
- **Not a real-time full-precision statistical method in the hot path** — approximate,
  windowed drift estimators are the normative expectation; exact per-token computation is
  explicitly out of scope for production.
- **An LLM judge is never the sole authority to terminate** — it classifies cause after a
  deterministic tier has already alerted (§22.4 tier 4).
- **Does not itself store raw untrusted tool payloads long-term** in the Action Receipt
  extension (§22.7) — hashes and summaries only, matching §9.6's PHI-backstop posture toward
  raw content generally.

### 22.7 Action Receipt extension (normative, additive)

An optional `session_integrity_v1` object MAY accompany an Action Receipt (§21.4):

```json
{
  "risk_threshold_profile_id": "session_term_v1",
  "R_session": 0.0,
  "action_ladder": "M|S|H|T|K",
  "drift_score": 0.0,
  "pin_hash": "0x...",
  "hard_override": null
}
```

Additive per §20's revision policy: absent on every commitment today, and its absence MUST NOT
be interpreted as a passing session-integrity check — only as "this control is not yet
implemented for this commitment."

### 22.8 Status

`[PLANNED]` in full. No component described in this section exists in any package today. It is
recorded now because the risk of documenting it later, after ad hoc implementations diverge, is
exactly the coherence problem this specification exists to prevent (see the ground rule at the
top of this document). Priority and sequencing belong in
[`docs/ENTERPRISE_ADOPTION.md`](../docs/ENTERPRISE_ADOPTION.md), not here — this section fixes
vocabulary and invariants, not a build order.

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
