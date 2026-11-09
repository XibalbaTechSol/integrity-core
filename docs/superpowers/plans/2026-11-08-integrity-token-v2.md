# Integrity Token v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the six per-agent EIP-1167 clone contracts (`ReputationRegistry`,
`Slasher`, `ComplianceGate`/`EHRGate`/`HIPAAGuardrailRegistry`, `StateAnchor`) and
the duplicated AIS write path (`SovereignAgent.updateAIS`) with six non-cloned
singleton contracts under `contracts/src/trust/`, wired into `SovereignAgent.execute`.

**Architecture:** Six `mapping(agent => ...)` singletons (`ITK`, `AISRegistry`,
`StakeVault`, `PolicyRegistry`, `RewardRegistry`, `ActionAnchor`), built bottom-up:
token and anchor first (no cross-module dependencies), then registry/vault pairs
that call each other (`AISRegistry` → `StakeVault.onCheckpoint`), finishing with
the `SovereignAgent.execute` wiring that ties stake, policy, and freeze together
in one transaction.

**Tech Stack:** Solidity ^0.8.28, Foundry (`forge test`), OpenZeppelin
`AccessControl`/`ERC20`/`ERC20Burnable`/`MerkleProof` (same versions already
vendored in this repo — see `contracts/src/oracle/IntegrityToken.sol` and
`contracts/src/oracle/StateAnchor.sol` for the exact import paths this plan
reuses).

**Spec:** `docs/superpowers/specs/2026-11-08-integrity-token-v2-design.md`

## Global Constraints

- No per-agent clone/proxy contracts anywhere in this plan — every new contract
  is a singleton deployed once, keyed by `mapping(address agent => ...)`.
- `ITK.MAX_SUPPLY = 100_000_000 ether`, lifetime-mint-tracked (not circulating
  supply), no fee-on-transfer, no transfer hooks — exact shape of today's
  `IntegrityToken.sol`, just a new contract/address (today's `IntegrityToken.sol`
  file and deployed instance are untouched; `IntegrityMarket`/`SmartBAA` keep
  using it).
- `AISRegistry` score is `uint32` basis points (`0..10000`), never a float —
  matches the existing cross-language canonicalization rule already applied to
  the Shield observation wire contract in this repo.
- `StakeVault`'s dispute/slash path (3-day challenge window, burn-not-treasury)
  is unchanged behavior from today's `Slasher.sol` — do not redesign it, port it.
- `PolicyRegistry`'s graph-mode leaf is
  `keccak256(abi.encode(fromNode, relation, toNode, riskWeightBps))`, verified
  with `MerkleProof.verify` against `graphRootOf[domainId]` — risk weight MUST be
  part of the leaf, never a separate unverified parameter.
- `SovereignAgent.execute`'s existing `IExecutionPolicy.check` hook is `view` and
  cannot be used for the stake lock, because `StakeVault.lockForAction` mutates
  state — Solidity does not allow a `view` call to reach a non-view external
  call. This plan modifies `SovereignAgent.execute` directly (Task 8) instead of
  routing through `IExecutionPolicy`; `IExecutionPolicy` stays available for
  agents that only need pure read-only checks and is otherwise untouched.
- `SovereignAgent.updateAIS` and its `IAccount.updateAIS` interface entry are
  deleted, not deprecated — `AISRegistry` becomes the sole AIS source of truth.

## Review Focus

- **Re-entrancy through `StakeVault.lockForAction`/`stake`/`unstake`**, since
  `stake`/`unstake` move real ERC20 value via `SafeERC20` the same way today's
  `Slasher.sol` does — a reasonable implementer expects the same
  `ReentrancyGuard` posture `Slasher.sol` already uses, not a bare `transferFrom`.
- **A `riskWeightBps` claimed in `checkCompliance`/`checkGraphEdge` that doesn't
  match what the Merkle leaf actually commits to** — the spec requires the risk
  price to be unforgeable (baked into the leaf), so a caller supplying a
  mismatched `riskWeightBps` with an otherwise-valid proof must fail, not pass
  with the wrong price.
- **A frozen agent whose policy check would otherwise pass** — freeze must block
  `execute` unconditionally, before the policy/stake checks run, not merely
  reduce the available lock to zero (a zero-value call with `value == 0` and
  `riskWeightBps == 0` would otherwise sneak through a stake-ceiling-only gate).
- **`onCheckpoint` called by anything other than `AISRegistry` itself** — a
  reasonable attacker tries calling `StakeVault.onCheckpoint` directly to force
  or avoid a freeze; it must be role-gated to the `AISRegistry` contract address
  specifically, not any `SCORER_ROLE` holder.
- **`resolveDispute` burning more than the locked amount, or unlocking without
  burning, due to an off-by-one in the lock/unlock bookkeeping** — the invariant
  "`locked <= amount` for every agent, always" must hold through stake → lock →
  freeze → dispute → resolve, which is a longer chain than today's `Slasher.sol`
  exercises (today's flow has no `lockForAction` step).

---

## File Structure

```
contracts/src/trust/
  ITK.sol                    # Task 1
  ActionAnchor.sol           # Task 2
  AISRegistry.sol            # Task 3
  IPolicyModule.sol          # Task 4 (interface)
  PolicyRegistry.sol         # Task 4
  StakeVault.sol             # Task 5
  IRewardModule.sol          # Task 6 (interface)
  RewardRegistry.sol         # Task 6
  DiscountRewardModule.sol   # Task 6 (reference IRewardModule implementation)
contracts/test/trust/
  ITK.t.sol                  # Task 1
  ActionAnchor.t.sol         # Task 2
  AISRegistry.t.sol          # Task 3
  PolicyRegistry.t.sol       # Task 4
  StakeVault.t.sol           # Task 5
  RewardRegistry.t.sol       # Task 6
  AISRegistryStakeVault.t.sol  # Task 7, cross-module freeze wiring
  ExecuteGating.t.sol        # Task 8, full gated-execute integration
  Invariants.t.sol           # Task 9, Foundry invariant/fuzz
contracts/src/core/SovereignAgent.sol   # Modified, Task 8
contracts/src/core/IAccount.sol         # Modified, Task 8
contracts/test/SovereignAgent.t.sol     # Modified, Task 8
contracts/test/PolicyHooks.t.sol        # Modified, Task 8
```

---

### Task 1: `ITK` token

**Files:**
- Create: `contracts/src/trust/ITK.sol`
- Test: `contracts/test/trust/ITK.t.sol`

**Interfaces:**
- Produces: `ITK` — `ERC20("Integrity Token", "ITK")`, `MINTER_ROLE`, `MAX_SUPPLY`,
  `totalMinted()`, `mint(address to, uint256 amount) external onlyRole(MINTER_ROLE)`,
  `burn(uint256 amount) external` (from `ERC20Burnable`), errors
  `ExceedsMaxSupply(uint256 requested, uint256 remaining)`, `ZeroAmount()`.

- [ ] **Step 1: Write failing tests in `contracts/test/trust/ITK.t.sol`**
```solidity
function test_mint_respectsMaxSupplyCap() external { ... } // mint MAX_SUPPLY+1 reverts ExceedsMaxSupply
function test_mint_revertsForNonMinter() external { ... }
function test_burn_reducesSupplyButNotMintHeadroom() external { ... } // mint, burn, mint again up to cap succeeds
function test_mint_revertsOnZeroAmount() external { ... }
```
- [ ] **Step 2: Run `forge test --match-path contracts/test/trust/ITK.t.sol -vv`, confirm all FAIL** (contract doesn't exist yet)
- [ ] **Step 3: Implement `ITK` in `contracts/src/trust/ITK.sol`**

Copy today's `contracts/src/oracle/IntegrityToken.sol` shape exactly (same
constructor `ITK(address admin, uint256 initialMint)`, same `MAX_SUPPLY`,
`totalMinted` tracked separately from `totalSupply()`, same errors) — only the
contract name changes. No new logic in this task.

- [ ] **Step 4: Run tests, confirm PASS**
- [ ] **Step 5: Commit** — `git add contracts/src/trust/ITK.sol contracts/test/trust/ITK.t.sol && git commit -m "feat(trust): add ITK, the non-legacy stake token"`

---

### Task 2: `ActionAnchor`

**Files:**
- Create: `contracts/src/trust/ActionAnchor.sol`
- Test: `contracts/test/trust/ActionAnchor.t.sol`

**Interfaces:**
- Produces: `ActionAnchor` — `mapping(address => bytes32) public latestRoot`,
  `mapping(address => uint256) public epoch`,
  `function anchorRoot(bytes32 root) external returns (uint256 newEpoch)`
  (caller is the agent — i.e. `msg.sender` is the `SovereignAgent` address being
  anchored, matching how `StateAnchor` is called today via
  `SovereignAgent.execute` targeting its own anchor), `function verifyLeaf(address
  agent, bytes32 leaf, bytes32[] calldata proof) external view returns (bool)`,
  event `RootAnchored(address indexed agent, uint256 indexed epoch, bytes32 root)`,
  error `EmptyRoot()`.

- [ ] **Step 1: Write failing tests in `contracts/test/trust/ActionAnchor.t.sol`**
```solidity
function test_anchorRoot_incrementsPerAgentEpoch() external { ... } // two different agents each start at epoch 1, independently
function test_anchorRoot_revertsOnEmptyRoot() external { ... }
function test_verifyLeaf_trueForIncludedLeafAgainstLatestRoot() external { ... } // build a 2-leaf tree, verify one leaf
function test_verifyLeaf_falseForDifferentAgentsRoot() external { ... } // leaf valid under agent A's root, checked against agent B returns false
```
- [ ] **Step 2: Run tests, confirm FAIL**
- [ ] **Step 3: Implement `ActionAnchor`**

One singleton replacing the per-agent `StateAnchor` clone: `anchorRoot` is keyed
by `msg.sender` (no role check — any address, including a `SovereignAgent`, can
only ever write its own slot) rather than today's `ANCHOR_ROLE`-gated single
root, since there is no "this agent's dedicated contract" anymore. Use
`MerkleProof.verify` from `@openzeppelin/contracts/utils/cryptography/MerkleProof.sol`,
same import `StateAnchor.sol` already uses.

- [ ] **Step 4: Run tests, confirm PASS**
- [ ] **Step 5: Commit**

---

### Task 3: `AISRegistry`

**Files:**
- Create: `contracts/src/trust/AISRegistry.sol`
- Test: `contracts/test/trust/AISRegistry.t.sol`

**Interfaces:**
- Consumes: nothing yet (Task 7 wires it to `StakeVault`).
- Produces: `AISRegistry` — `SCORER_ROLE`,
  `struct Checkpoint { uint32 score; uint64 windowEnd; bytes32 evidenceRoot; }`,
  `mapping(address => Checkpoint) public latest`,
  `function postCheckpoint(address agent, uint32 score, uint64 windowEnd, bytes32 evidenceRoot) external onlyRole(SCORER_ROLE)`,
  event `CheckpointPosted(address indexed agent, uint32 score, uint64 windowEnd, bytes32 evidenceRoot)`,
  error `ScoreOutOfRange(uint32 score)` (score must be `<= 10000`).

- [ ] **Step 1: Write failing tests**
```solidity
function test_postCheckpoint_storesLatestAndEmits() external { ... }
function test_postCheckpoint_revertsForNonScorer() external { ... }
function test_postCheckpoint_revertsAboveTenThousandBps() external { ... }
function test_postCheckpoint_overwritesPriorCheckpointForSameAgent() external { ... }
```
- [ ] **Step 2: Run tests, confirm FAIL**
- [ ] **Step 3: Implement `AISRegistry`** — plain `AccessControl` + the mapping/struct/function above. No cross-module call yet (that's Task 7).
- [ ] **Step 4: Run tests, confirm PASS**
- [ ] **Step 5: Commit**

---

### Task 4: `PolicyRegistry` + `IPolicyModule`

**Files:**
- Create: `contracts/src/trust/IPolicyModule.sol`
- Create: `contracts/src/trust/PolicyRegistry.sol`
- Test: `contracts/test/trust/PolicyRegistry.t.sol`

**Interfaces:**
- Produces:
  - `IPolicyModule.checkCompliance(address agent, address target, bytes calldata data) external view returns (bool allowed, uint16 riskWeightBps)`
  - `PolicyRegistry` — `GRAPH_CURATOR_ROLE`,
    `mapping(bytes32 => address) public moduleOf`,
    `mapping(address => address) public agentOverrideOf`,
    `mapping(bytes32 => bytes32) public graphRootOf`,
    `mapping(bytes32 => uint256) public domainFloor`,
    `function setModule(bytes32 domainId, address module) external onlyRole(DEFAULT_ADMIN_ROLE)`,
    `function setAgentOverride(address agent, address module) external onlyRole(DEFAULT_ADMIN_ROLE)`,
    `function setGraphRoot(bytes32 domainId, bytes32 root) external onlyRole(GRAPH_CURATOR_ROLE)`,
    `function setDomainFloor(bytes32 domainId, uint256 floor) external onlyRole(DEFAULT_ADMIN_ROLE)`,
    `function checkCompliance(address agent, bytes32 domainId, address target, bytes calldata data) external view returns (bool allowed, uint16 riskWeightBps)`
    (resolves `agentOverrideOf[agent]` then `moduleOf[domainId]`; reverts
    `NoModuleConfigured(bytes32 domainId)` if neither is set),
    `function checkGraphEdge(bytes32 domainId, bytes32 fromNode, bytes32 relation, bytes32 toNode, uint16 riskWeightBps, bytes32[] calldata proof) external view returns (bool allowed)`.

- [ ] **Step 1: Write failing tests**
```solidity
function test_checkCompliance_usesAgentOverrideWhenSet() external { ... }
function test_checkCompliance_fallsBackToDomainModule() external { ... }
function test_checkCompliance_revertsWhenNoModuleConfigured() external { ... }
function test_checkGraphEdge_trueForLeafIncludedInGraphRoot() external { ... }
function test_checkGraphEdge_falseWhenEdgeNotInGraph() external { ... }
function test_checkGraphEdge_falseWhenRiskWeightClaimDoesNotMatchLeaf() external { ... } // valid proof for a different riskWeightBps, wrong value supplied
```
- [ ] **Step 2: Run tests, confirm FAIL**
- [ ] **Step 3: Implement `IPolicyModule` and `PolicyRegistry`**

A minimal `AllowAllPolicyModule` test fixture living in the test file (not
production code) implementing `IPolicyModule` to exercise the generic path.
`checkGraphEdge`'s leaf is `keccak256(abi.encode(fromNode, relation, toNode,
riskWeightBps))` per Global Constraints — this is what makes the "wrong
riskWeightBps supplied" test fail correctly: the leaf changes, so the same proof
no longer verifies.

- [ ] **Step 4: Run tests, confirm PASS**
- [ ] **Step 5: Commit**

---

### Task 5: `StakeVault`

**Files:**
- Create: `contracts/src/trust/StakeVault.sol`
- Test: `contracts/test/trust/StakeVault.t.sol`

**Interfaces:**
- Consumes: `ITK` (Task 1) via `SafeERC20`, same pattern as today's `Slasher.sol`
  consuming `IntegrityToken`.
- Produces: `StakeVault` — `DISPUTER_ROLE`, `AIS_REGISTRY_ROLE`,
  `struct Stake { uint256 amount; uint256 locked; bool frozen; }`,
  `mapping(address => Stake) public stakeOf`,
  `uint32 public freezeThreshold`,
  `function stake(uint256 amount) external`,
  `function unstake(uint256 amount) external`,
  `function lockForAction(address agent, uint256 requiredLock) external`
  (callable by anyone — in practice `SovereignAgent.execute`, Task 8 — reverts
  `InsufficientAvailableStake()` if `amount - locked < requiredLock`, else
  increments `locked`),
  `function releaseLock(address agent, uint256 amount) external` (decrements
  `locked`; called after a window's checkpoint confirms compliance — Task 7/8
  wire this),
  `function onCheckpoint(address agent, uint32 score) external onlyRole(AIS_REGISTRY_ROLE)`
  (sets `frozen = score < freezeThreshold`),
  `function setFreezeThreshold(uint32 newThreshold) external onlyRole(DEFAULT_ADMIN_ROLE)`,
  `function raiseDispute(address agent, uint256 amount, string calldata reason) external onlyRole(DISPUTER_ROLE) returns (uint256 id)`,
  `function resolveDispute(uint256 id, bool slash) external onlyRole(DEFAULT_ADMIN_ROLE)`,
  same `Dispute` struct/events/errors/3-day-window constant as today's
  `Slasher.sol`, `ReentrancyGuard` on `stake`/`unstake`/`resolveDispute`
  (Review Focus item 1).

- [ ] **Step 1: Write failing tests**
```solidity
function test_stake_increasesAmount() external { ... }
function test_unstake_revertsIfAmountExceedsUnlocked() external { ... } // port from Slasher.t.sol's InsufficientAvailableStake case
function test_lockForAction_revertsWhenUnlockedBelowRequired() external { ... }
function test_lockForAction_incrementsLocked() external { ... }
function test_releaseLock_decrementsLocked() external { ... }
function test_onCheckpoint_freezesWhenScoreBelowThreshold() external { ... }
function test_onCheckpoint_doesNotFreezeWhenScoreAtOrAboveThreshold() external { ... }
function test_onCheckpoint_revertsForNonAisRegistryCaller() external { ... } // Review Focus item 4
function test_raiseDispute_lockWithoutBurn_thenResolve() external { ... } // port Slasher.t.sol's dispute/resolve flow
function test_resolveDispute_revertsBeforeChallengeWindowElapses() external { ... }
function test_invariant_lockedNeverExceedsAmount() external { ... } // single targeted case here; full fuzz is Task 9
```
- [ ] **Step 2: Run tests, confirm FAIL**
- [ ] **Step 3: Implement `StakeVault`**

Port `contracts/src/oracle/Slasher.sol`'s stake/dispute logic verbatim where the
shape matches (same `disputeWindow`, same burn-on-slash-via-`ERC20Burnable`,
same "no treasury profits" property); add `locked`, `lockForAction`,
`releaseLock`, `onCheckpoint`, `freezeThreshold` as the new surface this plan
needs. `unstake`'s "only unlocked portion" check now reads
`amount - locked`, same formula `Slasher.sol` already uses for
`lockedStakeOf`/`stakeOf`.

- [ ] **Step 4: Run tests, confirm PASS**
- [ ] **Step 5: Commit**

---

### Task 6: `RewardRegistry` + `IRewardModule` + `DiscountRewardModule`

**Files:**
- Create: `contracts/src/trust/IRewardModule.sol`
- Create: `contracts/src/trust/RewardRegistry.sol`
- Create: `contracts/src/trust/DiscountRewardModule.sol`
- Test: `contracts/test/trust/RewardRegistry.t.sol`

**Interfaces:**
- Produces:
  - `IRewardModule.onPositiveCheckpoint(address agent, uint32 oldScore, uint32 newScore, bytes32 domainId) external`
  - `RewardRegistry` — `mapping(bytes32 => address) public moduleOf`,
    `function setModule(bytes32 domainId, address module) external onlyRole(DEFAULT_ADMIN_ROLE)`,
    `function notifyPositiveCheckpoint(address agent, uint32 oldScore, uint32 newScore, bytes32 domainId) external`
    (no-ops if `moduleOf[domainId] == address(0)`; else forwards to the module).
  - `DiscountRewardModule` implements `IRewardModule` — `mapping(address => uint16) public trustDiscountBps`,
    read by `StakeVault`'s/`SovereignAgent`'s lock calculation in Task 8;
    `onPositiveCheckpoint` increases `trustDiscountBps[agent]` proportionally to
    `newScore - oldScore`, capped at a `MAX_DISCOUNT_BPS` constant (e.g. `5000`,
    i.e. never more than a 50% discount — pick a concrete cap and state it in
    the contract, since the spec leaves the exact ceiling to this
    implementation).

- [ ] **Step 1: Write failing tests**
```solidity
function test_notifyPositiveCheckpoint_noOpWhenNoModuleConfigured() external { ... }
function test_notifyPositiveCheckpoint_forwardsToConfiguredModule() external { ... }
function test_discountModule_increasesDiscountOnPositiveDelta() external { ... }
function test_discountModule_capsAtMaxDiscountBps() external { ... }
function test_discountModule_doesNotDecreaseOnNegativeOrZeroDelta() external { ... } // negative deltas are StakeVault's freeze concern, not this module's
```
- [ ] **Step 2: Run tests, confirm FAIL**
- [ ] **Step 3: Implement all three files**
- [ ] **Step 4: Run tests, confirm PASS**
- [ ] **Step 5: Commit**

---

### Task 7: Wire `AISRegistry.postCheckpoint` → `StakeVault.onCheckpoint` + `RewardRegistry.notifyPositiveCheckpoint`

**Files:**
- Modify: `contracts/src/trust/AISRegistry.sol`
- Test: `contracts/test/trust/AISRegistryStakeVault.t.sol`

**Interfaces:**
- Consumes: `StakeVault.onCheckpoint(address, uint32)` (Task 5),
  `RewardRegistry.notifyPositiveCheckpoint(address, uint32, uint32, bytes32)` (Task 6).
- Produces: `AISRegistry` constructor/setter gains
  `function setStakeVault(address vault) external onlyRole(DEFAULT_ADMIN_ROLE)`,
  `function setRewardRegistry(address registry) external onlyRole(DEFAULT_ADMIN_ROLE)`;
  `AISRegistry` must hold `StakeVault.AIS_REGISTRY_ROLE` (granted during
  deployment scripting, not in this task's Solidity).

- [ ] **Step 1: Write failing tests in `AISRegistryStakeVault.t.sol`**
```solidity
function test_postCheckpoint_belowThreshold_freezesStakeVaultAtomically() external { ... } // single tx: post, then read StakeVault.stakeOf(agent).frozen == true
function test_postCheckpoint_aboveThreshold_doesNotFreeze() external { ... }
function test_postCheckpoint_positiveDelta_notifiesRewardRegistry() external { ... } // mock IRewardModule records the call
function test_postCheckpoint_revertsIfStakeVaultUnset() external { ... }
```
- [ ] **Step 2: Run tests, confirm FAIL**
- [ ] **Step 3: Implement the wiring** — `postCheckpoint` now also calls
  `stakeVault.onCheckpoint(agent, score)` and, when `score > latest[agent].score`
  prior to overwrite, `rewardRegistry.notifyPositiveCheckpoint(agent, oldScore, score, domainId)`.
  `domainId` must be read from `XibalbaAgentRegistry.resolveAgent(agent).domainId`
  (existing contract/function per the spec's identity-layer reuse — add this as
  a constructor-injected dependency, `IXibalbaAgentRegistry` import, read-only
  call).
- [ ] **Step 4: Run tests, confirm PASS**
- [ ] **Step 5: Commit**

---

### Task 8: Gate `SovereignAgent.execute`, remove `updateAIS`

**Files:**
- Modify: `contracts/src/core/SovereignAgent.sol`
- Modify: `contracts/src/core/IAccount.sol`
- Modify: `contracts/test/SovereignAgent.t.sol` (remove/replace `updateAIS`-specific tests)
- Modify: `contracts/test/PolicyHooks.t.sol` (remove/replace any `updateAIS` references)
- Test: `contracts/test/trust/ExecuteGating.t.sol`

**Interfaces:**
- Consumes: `StakeVault.lockForAction`/`stakeOf` (Task 5), `PolicyRegistry.checkCompliance`/`checkGraphEdge`/`domainFloor` (Task 4).
- Produces: `SovereignAgent` constructor gains `address stakeVault, address policyRegistry, bytes32 domainId` parameters; `execute` keeps its existing signature and `IExecutionPolicy` hook (untouched, still runs first) and additionally, after the existing policy check and before the external call:
  1. `require(!IStakeVault(stakeVault).stakeOf(address(this)).frozen, "SovereignAgent: frozen")`
  2. an `IPolicyRegistry(policyRegistry).checkCompliance(address(this), target, data)` call, reverting on `!allowed`
  3. `IStakeVault(stakeVault).lockForAction(address(this), domainFloor + value * riskWeightBps / 10000)`

- [ ] **Step 1: Write failing tests in `ExecuteGating.t.sol`**
```solidity
function test_execute_revertsWhenFrozen() external { ... }
function test_execute_revertsWhenPolicyDenies() external { ... }
function test_execute_revertsWhenUnlockedStakeInsufficient() external { ... }
function test_execute_succeedsAndLocksStake_whenCompliantAndFunded() external { ... }
function test_execute_locksZeroWhenRiskWeightZero() external { ... } // Review Focus item 3's complement: a value==0,riskWeight==0 call still must check frozen first
```
- [ ] **Step 2: Run tests, confirm FAIL**
- [ ] **Step 3: Implement the `execute` changes; delete `updateAIS` from `SovereignAgent.sol` and `IAccount.sol`; update `ais` field removal — remove the `ais` state variable and `AISUpdated` event entirely, since `AISRegistry` (Task 3) is now the sole source.**
- [ ] **Step 4: Update `SovereignAgent.t.sol`/`PolicyHooks.t.sol`**: remove any test asserting on `updateAIS`/`ais`/`AISUpdated`; add constructor arguments the modified `SovereignAgent` now requires wherever it's instantiated in those files.
- [ ] **Step 5: Run full `forge test`, confirm no regressions and all new tests PASS**
- [ ] **Step 6: Commit**

---

### Task 9: Cross-module invariants

**Files:**
- Create: `contracts/test/trust/Invariants.t.sol`

**Interfaces:**
- Consumes: `ITK`, `StakeVault`, `AISRegistry` (Tasks 1, 5, 3) — no production code changes.

- [ ] **Step 1: Write Foundry invariant tests**
```solidity
function invariant_itkBurnedNeverIncreasesMintHeadroom() external { ... } // totalMinted is monotonic non-decreasing across any sequence of mint/burn
function invariant_lockedNeverExceedsAmount() external { ... } // for every agent touched by the fuzzer's handler
function invariant_frozenAgentExecuteAlwaysReverts() external { ... } // fuzz execute() calls against a frozen agent, assert 100% revert
```
- [ ] **Step 2: Run `forge test --match-contract Invariants -vv`, confirm PASS** (these are the project's safety net, not a red/green TDD step against new production code — no separate "write failing" step since nothing here is new production logic)
- [ ] **Step 3: Commit**

---

## Self-Review

**1. Spec coverage:** `ITK` → Task 1. `AISRegistry` → Tasks 3, 7. `StakeVault`
(stake/lock/freeze/dispute) → Tasks 5, 7, 8. `PolicyRegistry` (generic +
graph-Merkle, risk-weight-in-leaf) → Task 4. `RewardRegistry`/`DiscountRewardModule`
→ Task 6. `ActionAnchor` → Task 2. The gated `execute()` sequence → Task 8.
`SovereignAgent.updateAIS` removal → Task 8. Computational-sacrifice/ZK-proof
path for `PolicyRegistry`'s generic fallback (spec amendment) is **not** a
separate task: it is explicitly `scoring-core`/off-chain work per the spec's own
"this spec does not add a new score formula, only a new admissible-evidence
source feeding the existing one" — no on-chain task required beyond
`PolicyRegistry.checkCompliance` already accepting an optional proof-bearing
`data` payload, which Task 4 covers generically (the module decides what `data`
means). Migration (clean-slate, `IntegrityMarket`/`SmartBAA` untouched) requires
no task — it is the absence of a migration script, already satisfied by every
other task only ever creating new files. `RewardRegistry`'s deferred
`CreditLineRewardModule`/`YieldRewardModule` are explicitly out of v1 per spec —
correctly absent here.

**2. Step scan:** done inline while drafting — no step left a signature, file,
or test name undecided; bodies are omitted everywhere the signature + test
already determine them (ports of `Slasher.sol`/`StateAnchor.sol`/`IntegrityToken.sol`
logic), present only as prose pointers to the exact existing file to copy from.

**3. Type consistency:** `riskWeightBps` is `uint16` everywhere it appears
(Task 4's interface, Task 8's lock formula). `score`/`newScore`/`oldScore` are
`uint32` everywhere (Tasks 3, 6, 7). `domainId` is `bytes32` everywhere (Tasks
4, 7, 8). `agent` is always `address` (the `SovereignAgent` instance), never a
DID string, consistent with the spec's "keys off `sovereignAgent`, not a bare
EOA" rule.

**4. Review Focus coverage:** item 1 (re-entrancy) → Task 5's port of
`Slasher.sol`'s `ReentrancyGuard`. Item 2 (risk-weight forgery) → Task 4's
`test_checkGraphEdge_falseWhenRiskWeightClaimDoesNotMatchLeaf`. Item 3
(frozen-but-zero-value sneaking through) → Task 8's
`test_execute_locksZeroWhenRiskWeightZero`, which asserts the frozen check runs
regardless of lock size. Item 4 (`onCheckpoint` caller spoofing) → Task 5's
`test_onCheckpoint_revertsForNonAisRegistryCaller`. Item 5 (lock/unlock
off-by-one through the full chain) → Task 9's
`invariant_lockedNeverExceedsAmount`, fuzzed across stake/lock/release/dispute
sequences rather than a single hand-written case.

**5. Proportion:** this plan is ~370 lines against a ~400-line spec (after the
energy-cost amendment); no task's code block exceeds a handful of function
signatures, and every port of existing logic (`Slasher.sol`, `StateAnchor.sol`,
`IntegrityToken.sol`) is a pointer to the source file, not a transcript of it.
