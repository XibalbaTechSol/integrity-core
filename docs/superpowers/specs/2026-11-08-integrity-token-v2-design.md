# Integrity Token v2: a modular agent-trust/security architecture

**Status:** design, approved in conversation, not yet implemented.
**Author:** brainstormed with Claude Code, 2026-11-08.
**Supersedes (clean-slate, not additive):** `IntegrityToken.sol`, the `Slasher`/
`ReputationRegistry`/`ComplianceGate` per-agent clone pattern, `StateAnchor` clones,
and `SovereignAgent.updateAIS`. Today's Base Sepolia deployment is testnet-only
(245,299 of 100,000,000 ITK minted, no real value) and is treated as throwaway.
`XibalbaAgentRegistry` and `SovereignAgent` (minus `updateAIS`) are **not** touched —
they are the identity layer this design builds on, not redesigns.

## Why this exists

An audit of the current live Base Sepolia deployment (`IntegrityToken`, `Slasher`,
`ReputationRegistry`, `StateAnchor`, `ComplianceGate`, `AgentProfile`,
`VerifierRegistry`) found it mechanically sound but unnecessarily complex for
adoption: six separate per-agent EIP-1167 **clone** contracts, plus a duplicated
AIS write path (`SovereignAgent.updateAIS` *and* `ReputationRegistry.updateScore`
both claim to be the score). Owner's explicit complaint: "this seems unnecessarily
complicated and will fail to adopt users or devs... I don't understand why a clone
is needed."

Owner's spec for v2, verbatim intent:
1. The token must have utility for **AI agent trust and security**, in the context
   of Integrity Protocol specifically (not utility-as-afterthought).
2. Smart contracts must execute automated rules/policies **at machine speed**, and
   anchor agent **intent, action, and AIS score** on-chain for auditability in
   regulated domains (healthcare, finance).
3. It must be **simple** — no per-agent clone contracts.
4. (Discovered during brainstorming, now load-bearing): agents deploy **arbitrary
   contracts** to build their own markets/economies; DID/key identity anchoring
   already exists (`XibalbaAgentRegistry`) and must be reused, not reinvented;
   agents need **persistent memory** to have an identity at all; and AIS must
   function as a true **closed-loop reward function**, not a post-hoc audit metric
   — the physics of the agent's action space, not a guardrail bolted onto it.

## Architecture overview

Six singleton contracts, **zero clones**, each a `mapping(agent => ...)`
independently deployable and independently auditable. Two are explicitly
swappable per domain without redeploying anything else.

| Module | Replaces | Job |
|---|---|---|
| `ITK` | `IntegrityToken` | dumb capped ERC20, the stake asset |
| `AISRegistry` | `ReputationRegistry` clones + `SovereignAgent.updateAIS` | one checkpoint per agent/window: score + evidence root |
| `StakeVault` | `Slasher` clones | stake, per-action lock (the action ceiling), freeze, dispute/slash |
| `PolicyRegistry` | `ComplianceGate`/`EHRGate`/`HIPAAGuardrailRegistry` clones | hard gate (generic module or graph-Merkle-proof) + risk pricing |
| `RewardRegistry` | *(new)* | pluggable positive payoff for compliant goal-progress |
| `ActionAnchor` | `StateAnchor` clones | audit trail; doubles as the agent's memory-DAG root anchor |

`XibalbaAgentRegistry` (DID ↔ `sovereignAgent`/`controller`/`domainId`) and
`SovereignAgent` (the agent's account-abstraction wallet, `execute(target, value,
data)`) are existing, unmodified dependencies — every module below keys off the
`sovereignAgent` address `XibalbaAgentRegistry` already resolves, not a bare EOA.

## Components

### `ITK` — the token

Plain capped ERC20 + `ERC20Burnable` + `AccessControl`, same shape as today's
`IntegrityToken.sol` (100,000,000 lifetime-mint cap tracked separately from
circulating supply, no fee-on-transfer — fee-on-transfer silently breaks any
contract trusting `transferFrom`'s balance delta, which `StakeVault` does). No
transfer hooks, no policy calls on `transfer` — all trust/security logic lives in
`StakeVault`/`PolicyRegistry` at the `execute()` call site, not in the token, so
ITK stays composable with anything expecting plain ERC20 semantics. `MINTER_ROLE`
stays governance-held (confirmed live today: the admin/governance address holds
it, the funder EOA does not — that mainnet-readiness item carries forward
unchanged).

### `AISRegistry` — the checkpoint

```solidity
struct Checkpoint { uint32 score; uint64 windowEnd; bytes32 evidenceRoot; }
mapping(address agent => Checkpoint) public latest;
function postCheckpoint(address agent, uint32 score, uint64 windowEnd, bytes32 evidenceRoot) external onlyRole(SCORER_ROLE);
event CheckpointPosted(address indexed agent, uint32 score, uint64 windowEnd, bytes32 evidenceRoot);
```

`score` is the existing `ais/v1-geometric-1` formula's output
(`S_entropy^wE × S_grounding^wG × S_sacrifice^wS × S_compliance^wC`, scaled to
`0..10000` bps instead of `[0,1]` float — floats are the classic cross-language
canonicalization trap, same reason the Shield observation wire contract uses
basis points). **This math is not being rewritten** — only how it's consumed
changes (see "AIS as reward function," below). `evidenceRoot` is a Merkle root
over the off-chain action/telemetry trail that produced this score: the
auditability surface for a regulator, who gets a leaf + proof against this root,
not a bare number to trust. Per the owner's "persistent memory" requirement,
`evidenceRoot` MAY be (and for a Cortex-backed agent, should be) a commitment over
the agent's `memory_dag.root_of_heads()` — identity-as-continuity, not just
identity-as-keypair. Oracle writes at a cheap, fixed cadence (per window, never
per action) — this is the "low-noise, cheap to anchor" property the owner asked
for explicitly.

### `StakeVault` — the circuit breaker

```solidity
struct Stake { uint256 amount; uint256 locked; bool frozen; }
mapping(address agent => Stake) public stakeOf;
mapping(uint256 => Dispute) public disputes; // unchanged shape from today's Slasher

function stake(uint256 amount) external;
function unstake(uint256 amount) external; // only the unlocked portion, unchanged logic
function lockForAction(address agent, uint256 requiredLock) external; // called from SovereignAgent.execute()
function onCheckpoint(address agent, uint32 score) external onlyRole(AIS_REGISTRY_ROLE); // called BY AISRegistry, same tx as postCheckpoint
function raiseDispute(address agent, uint256 amount, string calldata reason) external onlyRole(DISPUTER_ROLE) returns (uint256 id);
function resolveDispute(uint256 id, bool slash) external onlyRole(DEFAULT_ADMIN_ROLE); // unchanged 3-day challenge window
function setFreezeThreshold(uint32 newThreshold) external onlyRole(DEFAULT_ADMIN_ROLE); // governance-set bps, same posture as today's setDisputeWindow
```

Two independent mechanisms, both "machine speed" (computed in-contract, no
oracle/governance round-trip for the fast path):

- **Freeze.** `AISRegistry.postCheckpoint` calls `StakeVault.onCheckpoint` in the
  *same transaction*. If `score < freezeThreshold`, `frozen` flips `true`
  atomically with the score write. A frozen agent's `execute()` reverts
  unconditionally (Section "The gated `execute()` sequence," step 1) until
  governance resolves the underlying dispute. Freeze ≠ slash: frozen stake is
  locked, not burned, matching today's Slasher's reasoning that one bad data
  point shouldn't destroy a stake, only halt further action pending human review.
- **Action ceiling.** `lockForAction` is the hard resource limit described below:
  an agent cannot take an action priced beyond its currently unlocked stake, full
  stop — not a rule that can be bypassed, a balance that cannot go negative.

Slash/dispute path is unchanged from today's `Slasher.sol`: `DISPUTER_ROLE`
(oracle) raises and locks, `DEFAULT_ADMIN_ROLE` (governance, after a 3-day
challenge window) resolves to burn or release. Burned ITK is destroyed via
`ERC20Burnable.burn`, never routed to a treasury — no address profits from a
slash, same anti-corruption property as today.

### `PolicyRegistry` + `IPolicyModule` — the hard gate and risk pricing

```solidity
interface IPolicyModule {
    function checkCompliance(address agent, address target, bytes calldata data)
        external view returns (bool allowed, uint16 riskWeightBps);
}

mapping(bytes32 domainId => address module) public moduleOf;        // generic fallback, per domain
mapping(address agent => address module) public agentOverrideOf;    // optional, per-agent
mapping(bytes32 domainId => bytes32 graphRoot) public graphRootOf;   // graph-shaped mode
mapping(bytes32 domainId => uint256 floor) public domainFloor;       // base stake lock per domain

function checkCompliance(address agent, address target, bytes calldata data) external view returns (bool allowed, uint16 riskWeightBps);
function checkGraphEdge(bytes32 domainId, bytes32 fromNode, bytes32 relation, bytes32 toNode, uint16 riskWeightBps, bytes32[] calldata proof) external view returns (bool allowed);
function setGraphRoot(bytes32 domainId, bytes32 root) external onlyRole(GRAPH_CURATOR_ROLE); // per-domain curator, governance-approved
```

Two modes, dispatched by what the domain has defined, satisfying the "both" answer
from brainstorming:

- **Graph-shaped (primary, for domains with a defined ontology — e.g. healthcare
  via Cortex).** Each leaf is `keccak256(fromNodeType, relation, toNodeType,
  riskWeightBps)`, the full graph lives off-chain (the real Cortex ontology), and
  `graphRootOf[domainId]` anchors it the same way `AISRegistry.evidenceRoot`
  anchors an action trail — **one anchoring primitive, two jobs**. An agent
  proposing an edge not in the anchored graph cannot produce a valid proof: the
  action is not *denied*, it is *absent*. This is the literal on-chain version of
  "an agent navigating a graph can only take edges that exist" from the owner's
  closed-loop-RL framing — and because `riskWeightBps` is baked into the leaf
  (not a separate claim), an agent cannot under-report risk to dodge the stake
  ceiling below.
- **Generic (fallback, for domains without a graph yet).** Arbitrary
  `IPolicyModule` Solidity, scored per `(target, data)` — a dev writes a small
  contract implementing one function and registers it against their `domainId` or
  their specific agent. This is the escape hatch for devs who don't think in graph
  terms, or need one-off logic a graph schema can't express yet.

Module/graph-root resolution defaults to the agent's `domainId` (read from
`XibalbaAgentRegistry`, reused, not reinvented) with an optional per-agent
override for custom compliance beyond the domain default.

#### Computational sacrifice: energy cost, not token cost

Clarified by the owner after the first draft of this spec: "unwanted behaviors
should be expensive" was meant literally as **computational/energy cost**, not
primarily as staked-token cost. Token stake (Section "`StakeVault`," and the
lock formula below) is a separate, legitimate lever the owner also explicitly
wants for token utility/demand — it is not being replaced — but it is not the
mechanism this phrase was describing.

The actual energy-cost lever already exists in the protocol and needed
reusing, not inventing: `ais/v1-geometric-1`'s `S_sacrifice` component and its
`ZK_boost = 1.0 + 0.15 × verified_event_ratio` (a real Barretenberg ZK proof,
via the existing `UltraPlonkVerifier`/`IZkVerifier`/`submitZkAttestation`
machinery, is genuinely expensive to *generate* — actual compute, not a fee).
This spec's two `PolicyRegistry` modes map directly onto that axis:

- **Graph-shaped mode is the cheap, low-energy path.** A Merkle proof against
  `graphRootOf[domainId]` is O(log n) hashes, because the edge's validity was
  already established once, off-chain, when the graph was curated. Compliance
  costs little *because the work was already done*, not because it's free.
- **The generic fallback path must carry a ZK proof to earn a non-zero
  `S_sacrifice`.** `checkCompliance`'s caller may attempt an action with no
  corresponding graph edge, but absent a verified proof attached to the claim,
  `S_sacrifice` (and therefore the whole multiplicative AIS score, per "AIS as a
  closed-loop reward function" below) stays low — the attempt isn't blocked,
  it's just worth nothing once AIS gates `R_task`. Attaching a real ZK proof is
  the literal energy cost of taking the unverified path: proof generation is
  actually compute-expensive, which is the mechanism, not a stand-in for one.
- Token stake answers a different question — *how much risk can this agent take
  on at all* — and continues to apply on top of this regardless of which mode
  gated the action.

No new cryptography: `PolicyRegistry`'s generic mode accepts an optional proof
payload in its `checkCompliance`/`checkGraphEdge` call and forwards it to the
existing `IZkVerifier`/`UltraPlonkVerifier` the protocol already deploys;
`AISRegistry`'s checkpoint writer (unchanged off-chain scoring-core math) is
what actually folds proof-presence into `S_sacrifice` — this spec does not add a
new score formula, only a new admissible-evidence source feeding the existing
one.

### `RewardRegistry` + `IRewardModule` — the positive payoff

```solidity
interface IRewardModule {
    function onPositiveCheckpoint(address agent, uint32 oldScore, uint32 newScore, bytes32 domainId) external;
}
mapping(bytes32 domainId => address module) public moduleOf;
```

Mirrors `PolicyRegistry`'s shape exactly: governance registers one module per
domain. **v1 ships exactly one implementation**, `DiscountRewardModule`, which
lowers a per-agent `trustDiscountBps` consumed by the lock formula below — a
trusted agent's identical action locks less stake than a new agent's. Owner was
explicit that "Integrity Protocol is an architecture" and the other two discussed
payoffs (a bounded credit line above raw stake; direct bounded ITK yield capped
against `MAX_SUPPLY`) must be addable later via a new `IRewardModule`
implementation and a governance registration call, with **zero changes** to
`AISRegistry` or `StakeVault`. Nothing in this design prevents them; v1 just
doesn't ship them.

### `ActionAnchor` — audit trail and memory continuity

```solidity
mapping(address agent => bytes32) public latestRoot;
mapping(address agent => uint256) public epoch;
function anchorRoot(bytes32 root) external; // caller's SovereignAgent controller, or an authorized anchorer
```

Direct replacement for the per-agent `StateAnchor` clone: one singleton, every
agent anchors into its own mapping slot, no new deployment per agent. Per the
owner's "persistent memory" requirement, this is where the SDK's
`memory_dag.root_of_heads()` commitment lands — an agent's identity is DID
(`XibalbaAgentRegistry`) **plus** a continuous, anchored memory/action trail here,
not a bare keypair. `MerkleProof.verify` against `latestRoot` is the existing
read-side pattern (unchanged from today's `StateAnchor.verify`).

## AIS as a closed-loop reward function

The owner's own analysis (independently arrived at, cross-checked against the
live repo during this design) identified a real gap: the formally documented
formula, `docs/wiki/concepts/ais.md` (last touched 2026-11-07, PR #195), is
**additive** —

$$R_{total} = R_{task} + \lambda \cdot \text{AIS}$$

— while AIS's internal computation is multiplicative
(`S_entropy^wE × S_grounding^wG × S_sacrifice^wS × S_compliance^wC`). An additive
combination lets a large enough `R_task` (task/goal-progress reward) swamp a
small `λ·AIS` penalty — exactly the "guardrails are thermodynamic friction an
optimizing agent routes around" failure mode. **PR #195 renamed the doc to
"Deterministic Reward Function" and added that framing in prose, but did not
change the formula.** The promise and the math currently disagree; this spec is
the fix, scoped to what these six modules consume (not a rewrite of
`scoring-core`'s math, which stays as-is):

1. **Hard/known violations move out of the reward formula entirely**, into
   `PolicyRegistry`'s structural gate (graph edge absent, or generic module
   reverts). There is no reward to swamp, because the action never happened —
   this is strictly stronger than any reward-shaping penalty.
2. **The continuous AIS score becomes a multiplier on task reward, not an
   addend**, for whatever consumes `R_task` off-chain (the oracle's RL training
   loop, if/when one exists): $R_{total} = R_{task} \times \text{AIS}$. A
   technically-successful but low-integrity path is worth near-nothing, not "a
   little less."
3. **What `AISRegistry` anchors on-chain is the existing `[0,1]` geometric score**
   (rescaled to bps), unchanged formula — consumed multiplicatively by
   `RewardRegistry`'s payoff sizing and by `StakeVault`'s freeze threshold, never
   additively combined with a separate task-reward field on-chain. On-chain never
   sees `R_task` at all; that stays off-chain, in whatever system computes it.

Note the owner's distinction between *energy* cost and *token* cost (see
`PolicyRegistry`'s "Computational sacrifice" subsection, above): `S_sacrifice`
inside this same formula is where unverified/off-graph actions get priced in
real compute (a ZK proof), separately from the `StakeVault` lock, which prices
risk in staked ITK. The two axes compose through the same multiplicative AIS
score rather than needing separate gating logic.

Separately recommended, outside this spec's scope: fix `docs/wiki/concepts/ais.md`
and `integrity-oracle/scoring-core` to match this (multiplicative) formula, since
right now the doc's stated promise and its actual math disagree independent of
anything built here.

## The gated `execute()` sequence

`SovereignAgent.execute(target, value, data)` gains two unconditional checks,
neither skippable by the agent, both evaluated in the same transaction as the
call:

1. `StakeVault.stakeOf[agent].frozen` must be `false`. A tripped circuit breaker
   blocks **all** further action — not "this one call," everything — until
   governance resolves the dispute.
2. `PolicyRegistry.checkCompliance(agent, target, data)` (or `checkGraphEdge` for
   graph-mode domains) → `(allowed, riskWeightBps)`. Revert if `!allowed` — Layer
   1, the hard gate, zero stake spent because nothing happened.
3. `requiredLock = PolicyRegistry.domainFloor[domainId] + value * riskWeightBps / 10000`,
   adjusted down by `RewardRegistry`'s `trustDiscountBps[agent]` if set.
   `StakeVault.lockForAction(agent, requiredLock)` — reverts if unlocked stake is
   insufficient. **This is the actual ceiling on the agent's action space**: you
   cannot act beyond what you've staked, which is a hard resource limit, not a
   rule — and it is the token's core utility-to-demand link (more authorized
   action requires more staked ITK).
4. The call executes.
5. Later, `AISRegistry.postCheckpoint` evaluates the window: compliant actions'
   locks release back to `stakeOf[agent].amount`; anything flagged feeds
   `StakeVault.raiseDispute` → the existing slow 3-day path → burn if confirmed.

## Arbitrary agent-deployed contracts (markets/economies)

Per the owner's example (Agent A deploys a market contract charging Agent B per
use of a digital asset): this requires **no new interface**. `AISRegistry.latest`,
`StakeVault.stakeOf`, and `PolicyRegistry`'s views are all plain public mappings
on singletons — any contract, including one an agent deploys via
`SovereignAgent.execute`, can already call
`AISRegistry.latest(counterparty).score` or
`StakeVault.stakeOf(counterparty).frozen` as an ordinary external view, the same
way a DeFi protocol composes with a price feed or a sanctions list. Composability
with arbitrary agent-built economies is a consequence of the "no clones, plain
singleton, public mapping" design choice, not an added feature. Whether a given
market contract chooses to check is that contract's own decision — the trust
layer being readable by anyone is what makes that an option at all.

## Migration

Clean-slate per the owner's explicit choice: today's Base Sepolia deployment
(245,299 ITK minted of 100,000,000 cap, no real economic value, testnet only) is
treated as throwaway. Fresh deployment, not a migration script. Contracts that
import today's `IntegrityToken`/`Slasher`/`ReputationRegistry`
(`IntegrityMarket`, `SmartBAA`, the health-domain gates) are **out of scope** per
the "just the trust/security core" scoping decision — they are a different
concern (prediction markets, HIPAA business-associate collateral, identity
metadata) not named in the owner's spec, and keep their current clone-based
contracts unless a separate decision brings them into this redesign later. This
is possible without contradiction: today's `IntegrityToken.sol` source and its
already-deployed instance are **not deleted** by this change — `ITK` is a new,
separate contract/address that becomes the canonical stake asset for the six
modules above. `IntegrityMarket`/`SmartBAA` keep pointing at whatever token
address they are already configured with; nothing here breaks them, and adopting
`ITK` for those subsystems (a single-token-economy future) is an explicit,
separate decision this spec defers rather than forces.
`SovereignAgent.updateAIS` is removed (role revoked, function deleted) since
`AISRegistry` becomes the one source of truth for AIS — closing the existing
duplicate-source-of-truth bug the audit found between `SovereignAgent.updateAIS`
and `ReputationRegistry.updateScore`.

## Testing

- **Per-module unit tests** (Foundry, mirroring today's `*.t.sol` coverage):
  `ITK` mint-cap/role tests (near-identical to today's `IntegrityToken.t.sol`);
  `StakeVault` stake/unstake/lock/freeze/dispute/slash (near-identical to today's
  `Slasher.t.sol`, plus new tests for `lockForAction`'s insufficient-stake revert
  and `onCheckpoint`'s atomic freeze); `AISRegistry` checkpoint-write and
  access-control tests; `PolicyRegistry` generic-module and graph-Merkle-proof
  tests (including the "risk weight baked into leaf, can't be under-claimed" case
  and the "edge absent → proof fails, not just a revert reason" case);
  `RewardRegistry` discount-module tests; `ActionAnchor` anchor/verify tests
  (near-identical to today's `StateAnchor.t.sol`).
- **Integration test**: the full gated `execute()` sequence end to end — stake,
  attempt a graph-gated call with a valid edge proof (succeeds, locks stake),
  attempt one with an invalid/absent edge (reverts, no stake moved), attempt one
  beyond available stake (reverts), post a low checkpoint (freeze trips
  atomically, further `execute()` reverts regardless of policy), raise+resolve a
  dispute (slash burns, matching today's `Slasher.t.sol` dispute-window tests).
- **Cross-module invariant tests** (Foundry invariant/fuzz, new): total `ITK`
  burned only ever decreases `totalSupply`, never raises mint headroom (same
  property `IntegrityToken.sol`'s NatSpec already documents and tests); a frozen
  agent can never successfully call `execute()` regardless of policy/stake state;
  `lockForAction` never allows `locked > amount` for any agent.
- No contract here needs new off-chain test infrastructure beyond what
  `contracts/test/` already has (Foundry, `forge test`); `AISRegistry`'s
  checkpoint writer and the oracle's role in computing the score are out of scope
  for this spec (unchanged `scoring-core`).

## Open items deferred by explicit decision (not silently dropped)

- Fixing `docs/wiki/concepts/ais.md`/`scoring-core` to actually implement the
  multiplicative formula this spec assumes AIS feeds — recommended, not in scope
  here.
- `CreditLineRewardModule` / `YieldRewardModule` — architecturally supported by
  `IRewardModule`, not implemented in v1.
- Whether `IntegrityMarket`/`SmartBAA`/health-domain gates get migrated off their
  current clone-based dependencies — explicitly out of scope per the "just the
  trust/security core" scoping answer.
- Per-agent Cortex graph-root curation workflow (who exactly calls
  `setGraphRoot` for the healthcare domain, how often) — the `GRAPH_CURATOR_ROLE`
  exists in the interface; the operational process for using it is not specified
  here.
