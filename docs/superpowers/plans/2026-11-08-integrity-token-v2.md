# Integrity Token v2 Implementation Plan (on-chain, Part B)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the six non-cloned singleton contracts of the on-chain
enforcement layer (`contracts/src/trust/`), wired into `SovereignAgent.execute`
with a call-bound graph-edge gate, replacing today's per-agent clones and the
duplicated AIS write path.

**Architecture:** Six `mapping(agent => ...)` singletons (`ITK`, `AISRegistry`,
`StakeVault`, `PolicyRegistry`, `RewardRegistry`, `ActionAnchor`), built
bottom-up: token/anchor first (no cross-module deps), then registry/vault pairs
that call each other, finishing with the gated `execute` that ties freeze +
call-bound policy + stake lock together in one transaction.

**Tech Stack:** Solidity ^0.8.28, Foundry (`forge test`), OpenZeppelin
`AccessControl`/`ERC20`/`ERC20Burnable`/`MerkleProof` (versions already vendored —
see `contracts/src/oracle/IntegrityToken.sol`, `StateAnchor.sol`).

**Spec:** `docs/superpowers/specs/2026-11-08-integrity-token-v2-design.md` (this
is the Part B plan; the off-chain Cortex engine is a separate plan, blocked on the
spec's Part C [REVIEW] decisions).

## Global Constraints

- No per-agent clone/proxy contracts — every new contract is a singleton keyed by
  `mapping(address agent => ...)`.
- `ITK.MAX_SUPPLY = 100_000_000 ether`, lifetime-mint-tracked, no fee-on-transfer,
  no transfer hooks — new contract/address; today's `IntegrityToken.sol` and the
  contracts importing it stay untouched.
- `AISRegistry` score is `uint32` basis points (`0..10000`), never a float.
- **Graph leaf (Spec A2/A3), call-bound and canonicalized:**
  `keccak256(abi.encode(bytes32 fromNode, bytes32 relation, bytes32 toNode, bytes4 targetSelector, uint16 riskWeightBps))`,
  OpenZeppelin sorted-pair Merkle, verified against `graphRootOf[domainId]`.
  `targetSelector` MUST equal `bytes4(data)` of the gated call. Risk weight is
  part of the leaf, never a separate unverified parameter.
- `checkCompliance` has **four parameters** everywhere it appears —
  `(address agent, bytes32 domainId, address target, bytes calldata data)` — in
  the module interface, the registry, and `execute`'s call site.
- `StakeVault.lockForAction` requires `msg.sender == agent` (no griefing).
- Freeze **latches**: `onCheckpoint` only ever sets `frozen = true`, never clears
  it; clearing is `unfreeze` (`DEFAULT_ADMIN_ROLE`) or dispute resolution.
- `evidenceRoot` is an opaque `bytes32` on-chain; PHI HMAC-keying of its leaves
  (Spec A4) happens off-chain, so no contract here handles raw identifiers.
- `SovereignAgent.updateAIS`, its `ais` field, `AISUpdated`, and the
  `IAccount.updateAIS` entry are deleted.

## Review Focus

- **Re-entrancy** through `lockForAction`/`stake`/`unstake` — same
  `ReentrancyGuard` posture `Slasher.sol` uses. → Task 5
- **Edge-claim / call mismatch:** a valid Merkle proof for edge X paired with a
  call whose `bytes4(data)` ≠ the leaf's `targetSelector` must fail — otherwise
  "structurally absent" is defeated by proving a cheap edge then calling
  anything. → Tasks 4, 8
- **Risk-weight forgery:** a `riskWeightBps` not matching the leaf must fail. → Task 4
- **Frozen bypass:** a frozen agent's zero-value call must still revert (freeze
  checked before the stake math). → Task 8
- **Griefing lock:** `lockForAction(victim, ...)` from a non-agent caller must
  revert. → Task 5
- **Auto-unfreeze:** a good checkpoint after a freeze must NOT clear `frozen`. → Task 5
- **Lock/unlock bookkeeping:** `locked ≤ amount` must hold through
  stake→lock→freeze→dispute→resolve and through `releaseLock`. → Task 9

---

## File Structure

```
contracts/src/trust/
  ITK.sol                    # Task 1
  ActionAnchor.sol           # Task 2
  AISRegistry.sol            # Task 3 (+ Task 7 wiring)
  IPolicyModule.sol          # Task 4
  PolicyRegistry.sol         # Task 4
  StakeVault.sol             # Task 5
  IRewardModule.sol          # Task 6
  RewardRegistry.sol         # Task 6
  DiscountRewardModule.sol   # Task 6
contracts/test/trust/
  ITK.t.sol ActionAnchor.t.sol AISRegistry.t.sol PolicyRegistry.t.sol
  StakeVault.t.sol RewardRegistry.t.sol AISRegistryStakeVault.t.sol
  ExecuteGating.t.sol Invariants.t.sol GoldenVectors.t.sol
contracts/src/core/SovereignAgent.sol   # Modified, Task 8
contracts/src/core/IAccount.sol         # Modified, Task 8
contracts/test/SovereignAgent.t.sol     # Modified, Task 8
contracts/test/PolicyHooks.t.sol        # Modified, Task 8
```

---

### Task 1: `ITK` token

**Files:** Create `contracts/src/trust/ITK.sol`; Test `contracts/test/trust/ITK.t.sol`.
**Produces:** `ERC20("Integrity Token","ITK")`, `MINTER_ROLE`, `MAX_SUPPLY`, `totalMinted()`, `mint(to,amount)`, `burn(amount)`; errors `ExceedsMaxSupply`, `ZeroAmount`.

- [ ] **Step 1:** Tests: mint cap, non-minter revert, burn doesn't reopen headroom, zero-amount revert.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Copy `IntegrityToken.sol`'s shape exactly (name only changes).
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit.

---

### Task 2: `ActionAnchor`

**Files:** Create `contracts/src/trust/ActionAnchor.sol`; Test `ActionAnchor.t.sol`.
**Produces:** `latestRoot[agent]`, `epoch[agent]`, `anchorRoot(root)` keyed by `msg.sender`, `verifyLeaf(agent, leaf, proof)`; event `RootAnchored(agent, epoch, root)`; error `EmptyRoot`.

- [ ] **Step 1:** Tests: per-agent epoch independence, empty-root revert, leaf included under latest root, cross-agent root returns false.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement with `MerkleProof.verify` (sorted-pair, same import as `StateAnchor.sol`).
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit.

---

### Task 3: `AISRegistry`

**Files:** Create `contracts/src/trust/AISRegistry.sol`; Test `AISRegistry.t.sol`.
**Produces:** `SCORER_ROLE`, `struct Checkpoint { uint32 score; uint64 windowEnd; bytes32 evidenceRoot; }`, `latest[agent]`, `postCheckpoint(agent, score, windowEnd, evidenceRoot)`; error `ScoreOutOfRange` (score ≤ 10000). (Cross-module calls added in Task 7.)

- [ ] **Step 1:** Tests: stores & emits, non-scorer revert, above-10000 revert, overwrite prior checkpoint.
- [ ] **Step 2:** Run → FAIL. Step 3: implement plain `AccessControl` + mapping. Step 4: PASS. Step 5: Commit.

---

### Task 4: `PolicyRegistry` + `IPolicyModule` (+ golden vectors)

**Files:** Create `IPolicyModule.sol`, `PolicyRegistry.sol`; Test `PolicyRegistry.t.sol`, `GoldenVectors.t.sol`.
**Produces:**
- `IPolicyModule.checkCompliance(address agent, bytes32 domainId, address target, bytes calldata data) → (bool allowed, uint16 riskWeightBps)` — **4 args**.
- `PolicyRegistry` — `GRAPH_CURATOR_ROLE`, `moduleOf[domainId]`, `agentOverrideOf[agent]`, `graphRootOf[domainId]`, `domainFloor[domainId]`; setters (admin, except `setGraphRoot` is curator); `checkCompliance(agent, domainId, target, data)` (override then domain module, revert `NoModuleConfigured`); `checkGraphEdge(domainId, fromNode, relation, toNode, bytes4 targetSelector, uint16 riskWeightBps, bytes32[] proof) → bool` verifying the leaf **and** that `targetSelector` was committed.
- `leafOf(fromNode, relation, toNode, targetSelector, riskWeightBps) → bytes32` pure helper (the canonical leaf; the golden-vector anchor).

- [ ] **Step 1:** Tests in `PolicyRegistry.t.sol`:
  - `test_checkCompliance_usesAgentOverrideWhenSet`
  - `test_checkCompliance_fallsBackToDomainModule`
  - `test_checkCompliance_revertsWhenNoModuleConfigured`
  - `test_checkGraphEdge_trueForCommittedEdge`
  - `test_checkGraphEdge_falseWhenEdgeAbsent`
  - `test_checkGraphEdge_falseWhenRiskWeightMismatched`
  - `test_checkGraphEdge_falseWhenSelectorMismatched` *(Review Focus: call binding)*
- [ ] **Step 2:** Tests in `GoldenVectors.t.sol`: `test_leafOf_matchesPinnedBytes` — assert `leafOf(...)` for one fixed input tuple equals a hard-coded `bytes32` (the value the Cortex Python side will reproduce; record it in both repos).
- [ ] **Step 3:** Run → FAIL. Step 4: implement; leaf = `keccak256(abi.encode(fromNode, relation, toNode, targetSelector, riskWeightBps))`; a tiny `AllowAllPolicyModule` fixture lives in the test file only. Step 5: Run → PASS. Step 6: Commit.

---

### Task 5: `StakeVault`

**Files:** Create `StakeVault.sol`; Test `StakeVault.t.sol`.
**Produces:** `DISPUTER_ROLE`, `AIS_REGISTRY_ROLE`, `Stake { amount; locked; frozen }`, `freezeThreshold`,
`stake`, `unstake` (unlocked only), `lockForAction(agent, req)` **`require(msg.sender == agent)`**,
`releaseLock(agent, amount) onlyRole(AIS_REGISTRY_ROLE)` (decrement by `min(amount, locked)`),
`onCheckpoint(agent, score) onlyRole(AIS_REGISTRY_ROLE)` **latching** (`if (score < freezeThreshold) frozen = true;`),
`setFreezeThreshold` / `unfreeze(agent)` (`DEFAULT_ADMIN_ROLE`),
`raiseDispute`/`resolveDispute` ported from `Slasher.sol`; `ReentrancyGuard`.

- [ ] **Step 1:** Tests:
  - `test_stake_increasesAmount`, `test_unstake_revertsIfExceedsUnlocked`
  - `test_lockForAction_incrementsLocked`, `test_lockForAction_revertsBelowRequired`
  - `test_lockForAction_revertsWhenCallerIsNotAgent` *(griefing)*
  - `test_releaseLock_decrementsByMin`, `test_releaseLock_revertsForNonAisRegistry`
  - `test_onCheckpoint_freezesBelowThreshold`, `test_onCheckpoint_noFreezeAtOrAbove`
  - `test_onCheckpoint_doesNotUnfreezeOnLaterGoodScore` *(latch)*
  - `test_onCheckpoint_revertsForNonAisRegistryCaller`
  - `test_unfreeze_onlyAdmin`
  - `test_raiseDispute_locksThenResolveBurns`, `test_resolveDispute_revertsBeforeWindow`
  - `test_lockedNeverExceedsAmount_singleCase`
- [ ] **Step 2:** Run → FAIL. Step 3: port `Slasher.sol` stake/dispute verbatim where shapes match; add lock/release/freeze/unfreeze surface. Step 4: PASS. Step 5: Commit.

---

### Task 6: `RewardRegistry` + `IRewardModule` + `DiscountRewardModule`

**Files:** Create `IRewardModule.sol`, `RewardRegistry.sol`, `DiscountRewardModule.sol`; Test `RewardRegistry.t.sol`.
**Produces:** `IRewardModule.onPositiveCheckpoint(agent, oldScore, newScore, domainId)`; `RewardRegistry.moduleOf[domainId]` + `notifyPositiveCheckpoint(...)` (no-op when unset); `DiscountRewardModule.trustDiscountBps[agent]` raised on positive delta, capped at `MAX_DISCOUNT_BPS = 5000`.

- [ ] **Step 1:** Tests: no-op unconfigured, forwards when set, discount rises on positive delta, caps at max, no decrease on ≤0 delta.
- [ ] **Step 2:** FAIL → implement → PASS → Commit.

---

### Task 7: Wire `AISRegistry.postCheckpoint` → vault + reward

**Files:** Modify `AISRegistry.sol`; Test `AISRegistryStakeVault.t.sol`.
**Produces:** `setStakeVault`, `setRewardRegistry` (admin); `postCheckpoint` now also calls `stakeVault.onCheckpoint(agent, score)`, `stakeVault.releaseLock(agent, releasable)` (the oracle passes the window's compliant-release amount as a new `postCheckpoint` arg `uint256 releasable`), and on positive delta `rewardRegistry.notifyPositiveCheckpoint(...)`. `domainId` read from `XibalbaAgentRegistry.resolveAgent(agent).domainId` (verified to exist).

- [ ] **Step 1:** Tests: below-threshold freezes **atomically in one tx**; above-threshold doesn't; `releasable` decrements vault `locked`; positive delta notifies reward registry (mock module records it); unset vault reverts.
- [ ] **Step 2:** FAIL → implement (AISRegistry must hold `StakeVault.AIS_REGISTRY_ROLE`, granted in deploy scripting) → PASS → Commit.

---

### Task 8: Gate `SovereignAgent.execute` (call-bound), remove `updateAIS`

**Files:** Modify `SovereignAgent.sol`, `IAccount.sol`, `SovereignAgent.t.sol`, `PolicyHooks.t.sol`; Test `ExecuteGating.t.sol`.
**Produces:** `execute` keeps its signature + `IExecutionPolicy` hook, and adds an **edge-claim overload** `execute(address target, uint256 value, bytes calldata data, bytes32 fromNode, bytes32 relation, bytes32 toNode, uint16 riskWeightBps, bytes32[] calldata proof)` that, after the existing hook:
  1. `require(!stakeVault.stakeOf(address(this)).frozen)`;
  2. for a graph domain, `require(policyRegistry.checkGraphEdge(domainId, fromNode, relation, toNode, bytes4(data), riskWeightBps, proof))`; else `checkCompliance(address(this), domainId, target, data)` revert-on-deny;
  3. `stakeVault.lockForAction(address(this), domainFloor + value*riskWeightBps/10000 - discount)`;
  4. the call. Constructor gains `stakeVault`, `policyRegistry`, `domainId`. The plain `execute(target,value,data)` remains for non-graph calls and routes through the generic `checkCompliance` with `riskWeightBps = 0`.

- [ ] **Step 1:** Tests: reverts when frozen (incl. zero-value call); reverts when edge proof invalid; reverts when `bytes4(data)` ≠ committed selector; reverts when stake insufficient; succeeds & locks when compliant+funded.
- [ ] **Step 2:** FAIL → implement; delete `updateAIS`, `ais`, `AISUpdated` from `SovereignAgent.sol` and `IAccount.sol`.
- [ ] **Step 3:** Update `SovereignAgent.t.sol`/`PolicyHooks.t.sol` (drop `updateAIS`/`ais` assertions; add new constructor args).
- [ ] **Step 4:** Full `forge test` green. Commit.

---

### Task 9: Cross-module invariants

**Files:** Create `Invariants.t.sol`.
- [ ] **Step 1:** Foundry invariants: `totalMinted` monotonic (burn never reopens headroom); `locked ≤ amount` for every fuzzed agent across stake/lock/release/dispute; a frozen agent's `execute` reverts 100%.
- [ ] **Step 2:** Run → PASS. Commit.

---

## Self-Review

**1. Spec coverage:** every Part B module → a task; Part A seam → Task 4
(call-bound `checkGraphEdge` + `targetSelector`), Task 8 (edge-claim overload),
`GoldenVectors.t.sol` (A3 canonicalization). A4 PHI-keying is off-chain (noted,
no contract task). A1 shared-root is satisfied by the Cortex plan reading the same
`graphRootOf`. The four spec fixes (arity, griefing lock, latching freeze,
releaseLock wiring) → Tasks 4/5/7/8.

**2. Step scan:** every step names its file/signature/test; ports of
`Slasher.sol`/`StateAnchor.sol`/`IntegrityToken.sol` are pointers, not transcripts.

**3. Type consistency:** `riskWeightBps` is `uint16`, scores `uint32`, `domainId`
`bytes32`, `targetSelector` `bytes4`, `releasable` `uint256`, `agent` always the
`SovereignAgent` address — consistent across Tasks 4–8.

**4. Review Focus:** re-entrancy → Task 5; edge/call mismatch →
`test_checkGraphEdge_falseWhenSelectorMismatched` (4) +
`execute` selector test (8); risk forgery → Task 4; frozen bypass → Task 8;
griefing lock + auto-unfreeze → Task 5; lock bookkeeping → Task 9.

**5. Proportion:** plan is close in length to Part B of the spec; no code block
exceeds a few signatures.
