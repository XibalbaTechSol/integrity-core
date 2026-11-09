# Navigational autonomy: a graph-reasoning agent with on-chain integrity enforcement

**Status:** design, approved in conversation; expanded 2026-11-08 to span both the
off-chain Cortex reasoning engine and the on-chain enforcement layer. Not yet
implemented. **Supersedes** the narrower first draft of this file (on-chain token
modules only).
**Author:** brainstormed with Claude Code, 2026-11-08.

## One-paragraph thesis

An LLM in an unconstrained latent space spends the same compute to assert a true
relationship as a false one, so nothing in its physics makes the true path
cheaper. This architecture makes the agent's action space the **edges of a
verified graph**: a step that does not correspond to an edge is not penalized, it
is *unavailable* (masked out of the policy's action distribution off-chain, and
unprovable against the anchored graph root on-chain). On top of that structural
floor, the agent's reward is the **Agent Integrity Score (AIS) as a multiplier on
task progress** — a technically-successful but low-integrity path is worth near
zero, not "a little less." The on-chain layer anchors intent, the traversed path,
and the AIS checkpoint for audit in regulated domains (healthcare, finance), and
freezes stake when integrity craters. "Compliance is physics, not a guardrail"
is the design goal; the sections below are what it takes to make that literally
true rather than a slogan.

## Scope, and two plans

This is **one architecture across two repos**, and per the brainstorming/
writing-plans scope rule it becomes **two implementation plans**, each producing
working, testable software on its own:

1. **On-chain enforcement & settlement** — six singleton contracts in
   `integrity-core/contracts/src/trust/`. Design is complete below; its plan is
   `docs/superpowers/plans/2026-11-08-integrity-token-v2.md` (to be revised to
   match this spec's fixes before execution).
2. **Off-chain navigational engine** — the graph-reasoning RL agent in
   `xibalba-cortex`. Its design choices (reward signal, RL algorithm, first action
   space, package home) were **settled with the owner on 2026-11-08** — see Part C
   "Settled decisions"; the first action space is the agent tool-call graph (the
   dogfooded thesis), not the clinical domain.

`xibalba-shield` (the OS-level PHI/boundary sensor) is named where it is load-
bearing but is **not** redesigned here.

## Honesty grounding (read before trusting any detail)

- The research that motivated this rewrite is a design conversation with a model
  that **could not access the repositories** (it said so). Its description of
  `xibalba-cortex` as a "neuro-symbolic knowledge graph" describes a system it
  never read. In this environment the real `xibalba-cortex` is the agent
  **memory/provenance store** (the `memory_*` tooling). The RL reasoning engine
  is therefore a **new subsystem**, and its exact home in that repo must be
  confirmed against the real repo at plan time — if it does not fit, its location
  is an open question for the owner, not something to invent.
- MIMIC-IV requires a PhysioNet credentialed data-use agreement and **cannot live
  in the repo or run in CI**. The engine is specced and tested against
  **Synthea** synthetic FHIR data; MIMIC is a later, out-of-repo evaluation.
- The research's code snippets use **additive** reward math (`R_bio + λ·AIS`, a
  `-100` terminal penalty, AIS in `[-1,1]`). This spec **rejects that** — see
  "Reward." It is the exact additive failure mode the owner already decided to
  fix. The research's *logit masking* is kept; it is the structural gate.

---

# Part A — The seam (the part that makes the thesis true)

Everything distinctive lives here: the off-chain policy and the on-chain gate
must enforce the **same graph**, or the on-chain "it's structurally absent" claim
is theater.

### A1. One anchored graph root, two readers

`PolicyRegistry.graphRootOf[domainId]` (on-chain, Part B) is a Merkle root over
the domain's allowed edges. The off-chain RL environment derives its **action
mask from the same root / same leaf set**. The on-chain gate and the off-chain
mask are then provably the same graph; neither can drift from the other without
changing the anchored root.

### A2. The edge claim must bind to the call

The first draft had a hole: `SovereignAgent.execute(target, value, data)` had no
slot for *which edge* is being exercised, and the plan only ever called the
generic `checkCompliance`, never the graph check. So an agent could prove the
cheapest valid edge and then call anything. Fix:

- The graph leaf commits to **what the action does**, at minimum
  `(fromNode, relation, toNode, targetSelector, riskWeightBps)`, where
  `targetSelector` is the 4-byte function selector of the call (`bytes4(data)`)
  and `toNode`/`fromNode`/`relation` are the ontology triple the action asserts.
- `execute` gains an **edge-claim path**: a variant / an extra argument carrying
  `(fromNode, relation, toNode, riskWeightBps, proof)`; it calls
  `PolicyRegistry.checkGraphEdge(...)`, which both verifies the Merkle proof
  against `graphRootOf[domainId]` **and** checks `bytes4(data) == targetSelector`
  committed in the leaf. A mismatch fails. "Structurally absent" now means the
  specific call, not a generic allow.

### A3. Canonicalization, pinned with golden vectors

Python (Cortex) and Solidity (core) must agree **byte-for-byte**:

- Leaf = `keccak256(abi.encode(bytes32 fromNode, bytes32 relation, bytes32 toNode, bytes4 targetSelector, uint16 riskWeightBps))`.
- Merkle tree uses OpenZeppelin **sorted-pair** hashing (same as today's
  `StateAnchor`).
- **Ontology IDs → `bytes32`:** a UMLS CUI / MeSH / LOINC code string maps to a
  node id by `keccak256(bytes(canonicalCodeString))`, canonical string fixed
  once (system prefix + code, lowercased, e.g. `"loinc:718-7"`). Pinned.
- **A single golden-vector test exists in BOTH repos** asserting identical leaf
  and root bytes for the same inputs. This repo already paid for the float-
  canonicalization trap once; integers and a pinned string form avoid a repeat.

### A4. No PHI on a public chain

`evidenceRoot` (the anchored commitment over a traversed path) leaves over
low-entropy patient identifiers are brute-forceable. Every leaf that could
contain a patient/subject id is **HMAC-keyed with a device/tenant key**, exactly
as `gate_receipts` already does (`hmac_identifier`), never a raw id or a bare
hash of one. A regulator verifies a leaf with the key; the public chain stores
only keyed commitments.

### A5. What crosses the seam, concretely

Per-hop, the off-chain `CortexEnvironment.step()`:
- **reads** `AISRegistry.latest(agent).score` (last anchored integrity) and the
  masked action set (from A1's root);
- **does not** write per hop (too expensive);
- at window/episode close, the oracle (SCORER) **writes** one
  `AISRegistry.postCheckpoint(agent, score, windowEnd, evidenceRoot)` where
  `evidenceRoot` is the A4-keyed commitment over the episode's traversed path.
  That single on-chain write is the audit anchor and the freeze trigger.

---

# Part B — On-chain enforcement & settlement (integrity-core)

Six singleton contracts, **zero clones**, each `mapping(agent => ...)`,
replacing today's six per-agent EIP-1167 clone templates and the duplicated AIS
write path (`SovereignAgent.updateAIS` *and* `ReputationRegistry.updateScore`).
Clean-slate: today's Base Sepolia deployment is testnet-only (245,299/100,000,000
ITK, no value), redeployed fresh, not migrated. `XibalbaAgentRegistry` and
`SovereignAgent` (minus `updateAIS`) are reused, not redesigned.

| Module | Replaces | Job |
|---|---|---|
| `ITK` | `IntegrityToken` | dumb capped ERC20, the stake asset |
| `AISRegistry` | `ReputationRegistry` clones + `SovereignAgent.updateAIS` | one checkpoint per agent/window: score + evidence root; settles the off-chain RL reward on-chain |
| `StakeVault` | `Slasher` clones | stake, per-action lock (action ceiling), **latching** freeze, dispute/slash |
| `PolicyRegistry` | `ComplianceGate`/`EHRGate`/`HIPAAGuardrailRegistry` clones | hard gate: graph-Merkle edge (primary) or generic module (fallback) + risk pricing bound to the call |
| `RewardRegistry` | *(new)* | pluggable positive payoff for compliant goal-progress |
| `ActionAnchor` | `StateAnchor` clones | audit trail; the agent's memory-DAG / traversed-path root anchor |

### ITK
Plain capped ERC20 + `ERC20Burnable` + `AccessControl`, exact shape of today's
`IntegrityToken.sol` (100M lifetime-mint cap tracked separately from circulating
supply, no fee-on-transfer, no transfer hooks), new contract/address; today's
`IntegrityToken.sol` and the contracts importing it (`IntegrityMarket`,
`SmartBAA`) are untouched. `MINTER_ROLE` governance-held.

### AISRegistry
`struct Checkpoint { uint32 score; uint64 windowEnd; bytes32 evidenceRoot; }`,
`mapping(address => Checkpoint) public latest`,
`postCheckpoint(agent, score, windowEnd, evidenceRoot) onlyRole(SCORER_ROLE)`;
`score` is `uint32` basis points `0..10000` (never a float). The on-chain score
is the existing `ais/v1-geometric-1` geometric product, rescaled — **this math is
not rewritten**, only consumed multiplicatively (see Reward).

### StakeVault (circuit breaker) — with the first draft's bugs fixed
`struct Stake { uint256 amount; uint256 locked; bool frozen; }`.
- `stake` / `unstake` (unlocked portion only), `ReentrancyGuard` on value-moving
  functions (ported from `Slasher.sol`).
- `lockForAction(agent, requiredLock)` — **`require(msg.sender == agent)`**: only
  the agent's own `SovereignAgent` locks its own stake, so no one can lock a
  victim's stake to grief them. Reverts `InsufficientAvailableStake` if
  `amount - locked < requiredLock`.
- `releaseLock(agent, amount) onlyRole(AIS_REGISTRY_ROLE)` — called from
  `AISRegistry.postCheckpoint`'s cross-call; decrements `locked` by
  `min(amount, locked)`. The oracle computes the window's releasable (compliant)
  amount off-chain; the vault trusts `AIS_REGISTRY_ROLE` to release no more than
  is locked. Trust assumption documented; a per-action on-chain lock ledger is a
  deferred refinement, not v1.
- `onCheckpoint(agent, score) onlyRole(AIS_REGISTRY_ROLE)` — **latching freeze**:
  `if (score < freezeThreshold) frozen = true;`. It never clears `frozen`. A
  good checkpoint does **not** auto-unfreeze (the first draft's bug). Clearing is
  only `unfreeze(agent) onlyRole(DEFAULT_ADMIN_ROLE)` or a dispute resolution —
  freeze lasts until governance acts, as intended.
- `raiseDispute` / `resolveDispute` — ported verbatim from `Slasher.sol` (3-day
  challenge window, burn-not-treasury).
- `setFreezeThreshold` / `unfreeze` — `DEFAULT_ADMIN_ROLE`.

### PolicyRegistry + IPolicyModule — arity fixed, call-bound
`checkCompliance(address agent, bytes32 domainId, address target, bytes calldata data) → (bool allowed, uint16 riskWeightBps)` — **four args, consistently**
(spec, the module interface, and `execute`'s call site all agree; the first
draft disagreed across the three). Resolution: `agentOverrideOf[agent]` then
`moduleOf[domainId]`, revert `NoModuleConfigured` if neither.
`checkGraphEdge(domainId, fromNode, relation, toNode, riskWeightBps, proof) → bool`
verifies the A3 leaf against `graphRootOf[domainId]` and binds `bytes4(data)` per
A2. `setGraphRoot` is `GRAPH_CURATOR_ROLE` (governance-approved per domain).
Risk weight is **in the leaf**, never a separate unverified parameter, so it
can't be under-reported.

#### Computational sacrifice is energy, not token (unchanged from prior amendment)
Graph-mode is the cheap path (`O(log n)` proof — the work was done when the graph
was curated). The generic fallback must carry a **ZK proof** (via the existing
`UltraPlonkVerifier`/`IZkVerifier`) to earn a non-zero `S_sacrifice`; proof
*generation* is the real compute cost. No new cryptography — the generic module
forwards a proof payload in `data` to the verifier the protocol already deploys,
and proof-presence feeds the existing `S_sacrifice`, not a new field.

### RewardRegistry + IRewardModule
`onPositiveCheckpoint(agent, oldScore, newScore, domainId)`; one v1
implementation, `DiscountRewardModule`, lowers a per-agent `trustDiscountBps`
(capped, e.g. `MAX_DISCOUNT_BPS = 5000`) used in the lock formula — a trusted
agent locks less stake per identical action. Credit-line / ITK-yield modules are
architecturally supported, not shipped in v1.

### ActionAnchor
`mapping(address => bytes32) public latestRoot`, `anchorRoot(root)` keyed by
`msg.sender`, `verifyLeaf(agent, leaf, proof)`. One singleton replacing per-agent
`StateAnchor` clones; where the memory-DAG `root_of_heads()` and the A4-keyed
traversed-path commitment land. Identity = DID (`XibalbaAgentRegistry`) **plus**
this continuous anchored trail.

### The gated execute() sequence
`SovereignAgent.execute` gains, after its existing `IExecutionPolicy` hook, all
unconditional and in one tx:
1. `require(!stakeVault.stakeOf(address(this)).frozen)` — freeze blocks
   everything first, even a zero-value call.
2. the edge-claim path (A2): `checkGraphEdge(...)` for graph domains, else
   `checkCompliance(agent, domainId, target, data)`; revert on deny.
3. `lockForAction(address(this), domainFloor[domainId] + value*riskWeightBps/10000)`
   discounted by `trustDiscountBps` — the hard action ceiling, and the token's
   utility→demand link.
4. the call.
5. later, `postCheckpoint` releases compliant locks / raises a dispute on flagged
   actions.

`SovereignAgent.updateAIS`, the `ais` field, and `AISUpdated` are **deleted**
(not deprecated) — `AISRegistry` is the sole AIS source of truth.

---

# Part C — Off-chain navigational engine (xibalba-cortex) — decisions flagged

Design-level only; the thesis mechanics and reward are settled, and the four open
choices were confirmed with the owner on 2026-11-08 (see "Settled decisions").

### The thesis mechanics (settled)
- **Action space = outgoing edges of the current node**, enforced by **logit
  masking before softmax** (mask invalid actions to `-1e9`). This is the
  structural gate; an unavailable edge has probability exactly 0. Because masking
  already makes a forbidden hop unavailable, the research's **`-100` terminal
  penalty is redundant and is dropped**.
- **State encoder:** a relational GNN (R-GCN) over the typed edges, so the policy
  "sees" its neighborhood before choosing — edges are typed (`PRESCRIBED` ≠
  `INHIBITS`), so a plain GCN is wrong.
- **The action mask derives from the same anchored graph root as the on-chain
  gate** (A1), so the thing the agent *can* do and the thing the chain will
  *prove* are one graph.

### Reward (settled, and deliberately NOT the research's additive form)
`R_total = R_task × AIS`, with **AIS ∈ [0,1]** (the geometric integrity score,
same value `AISRegistry` anchors). A low-integrity path multiplies task progress
toward zero; it is not an additive penalty a large `R_task` can swamp. Hard
violations are handled by masking (structurally absent), not by reward shaping.
This is the owner's already-agreed fix; the research's `R_bio + λ·AIS` /
`-100` / `[-1,1]` forms are explicitly not used.

### Settled decisions (owner-confirmed 2026-11-08)
- **`R_task`:** **TransE energy primary, with a terminal goal bonus.** Dense step
  reward is `−‖h+r−t‖` (negative TransE energy of the chosen edge, rewarding a
  semantically-grounded hop); the episode adds a terminal bonus for reaching the
  goal node (shortest-path/goal reach). Embeddings are trained before the policy.
  Temporal (TTransE) is out of v1.
- **RL algorithm:** **REINFORCE first** (`log_prob · return`, logit-masked
  actions); PPO deferred until the masked-policy + reward loop is proven.
- **First action space — the agent tool-call graph (dogfood), NOT clinical.**
  Nodes = agent states; **typed edges = permitted tool/action transitions** an
  agent may take from a state. This is the thesis itself: a hallucinated tool call
  is a non-edge, structurally absent from the mask and absent from the anchored
  root. No external data or DUA; the graph is built from the protocol's own
  permitted-action schema. Clinical FHIR (Synthea → MIMIC-IV) is a **later
  domain**, swapped in behind the same engine once the loop is proven here.
- **Engine home:** a **new top-level package** in the real `xibalba-cortex`
  (grounded 2026-11-08: single `src/xibalba_cortex/` package, `requires-python
  >=3.12`, `torch 2.13.0` already resolved in `uv.lock` via `sentence-transformers`,
  and `integrity-sdk` an **editable sibling path** `../integrity-core/integrity-sdk`).
  The engine becomes a **uv workspace member** (e.g. `cortex-nav/`, package
  `cortex_nav`) that depends on `xibalba-cortex` + `integrity-sdk`, never the
  reverse — keeping RL/training code out of the memory service's runtime while
  reusing torch already in the lock. Execution caveat: a Cortex worktree breaks the
  editable `../integrity-core/integrity-sdk` path, so the plan's setup step requires
  a sibling `integrity-core` checkout.

### Falsifiable tests the Cortex plan must include (so it can fail)
- masked actions have probability **exactly 0**;
- a dead-end node (zero valid edges) terminates cleanly — no NaN, no uniform
  softmax over an all-masked row;
- action-index ↔ edge mapping is stable across steps;
- **`AIS = 0 ⇒ R_total = 0`** for any `R_task`;
- a permitted tool transition maps to a typed edge
  (`State → MAY_CALL → Tool → TRANSITIONS_TO → State`) and a forbidden one is
  **absent** from the node's edge set (not a negative edge);
- the A3 **golden leaf/root vectors** match the Solidity side byte-for-byte, with
  the tool-call edge leaf's `targetSelector` bound to the on-chain call;
- **one seeded toy-graph test:** a compliant tool-call path vs. a higher-`R_task`,
  low-AIS path, asserting the trained policy prefers compliance — the falsifiable
  form of the "compliance is physics" claim. No large-scale convergence claim.

---

## Open items deferred by explicit decision
- Fixing `docs/wiki/concepts/ais.md` / `scoring-core` to actually implement the
  multiplicative reward this spec assumes — recommended, out of scope here.
- `CreditLineRewardModule` / `YieldRewardModule` — supported, not in v1.
- `IntegrityMarket` / `SmartBAA` / health-domain gate migration off clones — out
  of scope ("just the trust/security core").
- Per-action on-chain lock ledger (vs. the oracle-computed release of Part B) —
  deferred refinement.
- Clinical FHIR domain (Synthea in-repo, MIMIC-IV out-of-repo credentialed
  evaluation) — a later action space behind the same engine, after the tool-call
  graph proves the loop.
