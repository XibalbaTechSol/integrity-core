# Agent Wallet — Plan 1: wallet-stack spike + Integrity contracts

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Settle the wallet stack with a fork-only spike, then build the wallet-agnostic Integrity contracts: `IntegrityHook`, `AgentRegistry` v3 and `AISRegistry.postedAt`. Include their Forge tests, Halmos proofs and an Anvil deploy.

**Architecture:**
- **`IntegrityHook` implements the standard ERC-7579 `IHook`.** It is tested against a mock 7579 account.
- **Stack adapters.** The two things only the chosen wallet stack can answer sit behind two small interfaces, `IOperationContext` and `IAccountVerifier`:
  - which key authorized this operation
  - is this a genuine account of the stack, and who owns it

  This plan defines them and tests with mocks. Plan 1b implements them for the stack the spike picks.

**Tech Stack:** Solidity 0.8.28 (cancun, via_ir, optimizer 200), Foundry, Halmos, ERC-7579, ERC-4337 EntryPoint v0.7.

**Spec:** `docs/superpowers/specs/2026-11-18-agent-wallet-custody-design.md` (rev 3, approved). Read §5, §6.1–§6.5 and §9 before any task.

## Global Constraints

- **Local chain only (D-D).** Nothing is broadcast to Base Sepolia. Fork tests are read-only `--fork-url` runs, and the spike is one too. This reconciles §6.1 ("deploys one on Base Sepolia") with D-D and with the unrotated credentials (P4).
- **Fork RPC comes from `BASE_SEPOLIA_RPC_URL`.**
  - Alchemy first; `https://sepolia.base.org` is the read-only fallback.
  - Fork tests `vm.skip(true)` when the variable is unset.
  - Never commit an RPC URL that carries a key.
- **Compiler:** solc `0.8.28`, `evm_version = "cancun"`, `via_ir = true`, `auto_detect_remappings = false`. Every new remapping is explicit in `foundry.toml` and `remappings.txt`.
- **EntryPoint v0.7 is `0x0000000071727De22E5E9d8BAf0edAc6f37da032`.** The vendored `lib/account-abstraction` is **v0.9.0** (b36a1ed), so don't assume its EntryPoint is v0.7.
- **The live agent0 identity registry (Base Sepolia) is `0x8004A818BFB912233c491871b3d84c89A494BD9e`.**
- **ERC-7579 constants:**
  - `MODULE_TYPE_HOOK = 4`
  - `execute(bytes32,bytes)` selector `0xe9ae5c53`; `executeFromExecutor(bytes32,bytes)` `0xd691c964`
  - CallType byte 0 of the mode: `0x00` single, `0x01` batch, `0xff` delegatecall
- **Hook error names are a public contract, because the SDK maps them (§6.8):** `LimitExceeded`, `AisBelowFloor`, `AisStale`, `CoSignerRequired`, `OwnerApprovalRequired`, `Frozen`, `AwaitingFirstCheckpoint`.
- **`AISRegistry.MAX_SCORE = 10000`** (basis points). Floors and `bootstrapScore` use the same scale.
- **Workspace.** Work in a worktree from `xb-wt start integrity-core feat/integrity-hook`, never `~/Projects/integrity-core`. Push with `xb-wt push`. Merge with `gh pr merge --match-head-commit <sha>` after every JSON check bucket is `pass`.
- **Deploys.** Merging to integrity-core `main` deploys the Oracle (Render autoDeploy). This plan touches no Oracle code; keep it that way.

## Review Focus

1. **Approve-then-pull.** An `approve(spender, X)` moves no balance now, but lets the spender pull X later, outside the hook. The approved amount must count against per-call and window caps at approve time, and `approve` to a non-allowlisted spender is denied. → Task 4, `test_approve_counts_against_window`.
2. **Batch splitting.** A 7579 batch of transfers, each under the per-call cap but together over the window cap, must fail in `postCheck` on the measured delta. → Task 4, `test_batch_split_caught_by_window`.
3. **Delegatecall mode.** A delegatecall execution can do anything, so it is denied unless the operation is the owner's. → Task 3, `test_delegatecall_denied_for_session`.
4. **Window boundary.** Spending exactly the remaining window passes, one more wei fails, and after `windowSeconds` the window has room again. → Task 4, `test_window_boundary_and_reset`.
5. **A self-serving `isModuleInstalled`.** A contract that answers `true` to `isModuleInstalled` but never calls `preCheck` must not count as governed. That is why `IAccountVerifier.genuine` is required. → Task 7, `test_lying_account_not_governed`.

---

### Task 1: Wallet-stack spike (fork only), plus decision record

The spike is exploratory: no TDD and no production code. Its deliverable is a decision record that Plan 1b uses as its interface source.

**Files:**
- Create: `contracts/test/spike/WalletStackSpike.t.sol` (throwaway; deleted in Plan 1b once the fork tests replace it)
- Create: `docs/superpowers/specs/2026-11-18-wallet-stack-spike.md`
- Modify (only if a stack is vendored): `.gitmodules`, `contracts/foundry.toml`, `contracts/remappings.txt`

**Interfaces:**
- Produces: the decision record. It must answer each of these in its own heading with evidence (test name plus output):
  1. **Chosen stack**, with the factory and validator addresses (or "deployed from source in the fork"). Include `eth_getCode` results on Base Sepolia for each candidate component.
  2. **Execution paths.** Does any owner path skip 7579 hooks (`execTransaction`, other modules)? Is an `IntegrityGuard` needed?
  3. **Role source.** How `IOperationContext.roleOf(account)` will learn Owner / Session / Maintenance for the current operation (transient context from the validator, Smart Sessions policy, or guard).
  4. **Session-key 1271.** The config that makes the session validator refuse EIP-1271, and the test that proves it.
  5. **Passport mint.** From a fork, the wallet calls the live registry's `register(...)`, and `agentWallet` reads back as the wallet address (or the receiver failure, if it fails).
  6. **Genuineness + owner.** How `IAccountVerifier.verify(account)` proves the account came from the stack's factory and reads its single EOA owner.
  7. **Build compatibility.** Does the stack compile under the Global Constraints compiler settings? If not, how it is deployed on Anvil (published artifacts or bytecode).

- [ ] **Step 1: Set up the worktree**

Run, in order:
```bash
xb-wt start integrity-core feat/integrity-hook
cd /mnt/storage/xibalba/Projects/worktrees/integrity-core/integrity-hook
xb-wt setup && git submodule update --init --recursive
cd contracts && forge build
```
Expected: `forge build` succeeds (`Compiler run successful`).

- [ ] **Step 2: Evaluate Safe + Safe7579 + Smart Sessions first, on a fork**

Run: `forge test --match-path test/spike/WalletStackSpike.t.sol --fork-url "$BASE_SEPOLIA_RPC_URL" -vvv`
- Deploy (in the fork) an account owned by a test EOA, and install a stub hook that records `preCheck` calls.
- Enable a session key, and send one session-key UserOperation by calling `EntryPoint(0x0000000071727De22E5E9d8BAf0edAc6f37da032).handleOps` directly. No bundler is needed.
- Then exercise the owner path (`execTransaction` on Safe), and check whether the stub hook saw it.

- [ ] **Step 3: Answer questions 2–7 for that stack.** If question 2 or 3 needs more than one extra contract, repeat Step 2 for Nexus, then Kernel v3, and pick the stack that answers all seven with the least extra code (spec §6.1).

- [ ] **Step 4: Write the decision record.** Stop and show it to the owner before Plan 1b starts. Plan 1 Tasks 2–8 do not depend on the answer and may continue.

- [ ] **Step 5: Commit**
```bash
git add contracts/test/spike docs/superpowers/specs/2026-11-18-wallet-stack-spike.md
git commit -m "spike(wallet): fork-only stack evaluation + decision record"
xb-wt push
```

---

### Task 2: `AISRegistry.postedAt`

The `Checkpoint` struct and the `latest()` getter **stay unchanged**: `AgentAuthorityResolver.sol:33` and `ConstraintExecutionPolicy.sol:88` destructure three return values. Add a separate mapping.

**Files:**
- Modify: `contracts/src/trust/AISRegistry.sol` (`postCheckpoint`, at :94)
- Test: `contracts/test/trust/AISRegistry.t.sol`

**Interfaces:**
- Produces: `mapping(address => uint64) public postedAt;`, set to `uint64(block.timestamp)` in `postCheckpoint`.

- [ ] **Step 1: Write the failing test**
```solidity
function test_postCheckpoint_records_postedAt() public {
    vm.warp(1_700_000_000);
    _post(agent, 8000);                       // existing helper / SCORER_ROLE prank
    assertEq(ais.postedAt(agent), 1_700_000_000);
    vm.warp(1_700_000_500);
    _post(agent, 8100);
    assertEq(ais.postedAt(agent), 1_700_000_500);
    (uint32 score,,) = ais.latest(agent);     // ABI unchanged
    assertEq(score, 8100);
}
```
- [ ] **Step 2: Run it.** `forge test --match-test test_postCheckpoint_records_postedAt`. Expected: FAIL (`postedAt` not found).
- [ ] **Step 3: Add the mapping**, and write it in `postCheckpoint` before the vault calls.
- [ ] **Step 4: Run `forge test --match-path 'test/trust/AISRegistry*'`.** Expected: all PASS.
- [ ] **Step 5: Commit** with `feat(ais): record checkpoint postedAt`.

---

### Task 3: `IntegrityHook` core — adapters, install, classification, checks 1–3

**Files:**
- Create: `contracts/src/wallet/IOperationContext.sol`, `contracts/src/wallet/IAccountVerifier.sol`, `contracts/src/wallet/IntegrityHook.sol`
- Create: `contracts/test/wallet/mocks/MockGovernedAccount.sol`, `contracts/test/wallet/mocks/MockOperationContext.sol`, `contracts/test/wallet/mocks/MockAccountVerifier.sol`
- Create: `contracts/test/wallet/IntegrityHookBase.sol` (fixture), `contracts/test/wallet/IntegrityHookCore.t.sol`

**Interfaces:**
- Produces:
```solidity
interface IOperationContext {
    enum Role { None, Owner, Session, Maintenance }
    /// Role that authorized the operation currently executing on `account`.
    function roleOf(address account) external view returns (Role);
    /// Shield co-signature carried with the current operation (empty if none).
    function coSignatureOf(address account) external view returns (bytes memory);
}
interface IAccountVerifier {
    /// genuine: deployed by the chosen stack's factory; owner: its single EOA owner (D-M).
    function verify(address account) external view returns (bool genuine, address owner);
}
contract IntegrityHook /* is IHook (ERC-7579) */ {
    constructor(address governance, AgentRegistry registry, AISRegistry ais, StakeVault vault,
                IOperationContext ctx, uint32 protocolFloor, uint64 maxCheckpointAge); // reverts if maxCheckpointAge == 0
    function onInstall(bytes calldata initConfig) external;   // msg.sender = account
    function onUninstall(bytes calldata) external;
    function isModuleType(uint256 t) external pure returns (bool); // t == 4
    function isInitialized(address account) external view returns (bool);
    function isConfigured(address account) external view returns (bool);
    function preCheck(address msgSender, uint256 msgValue, bytes calldata msgData) external returns (bytes memory hookData);
    function postCheck(bytes calldata hookData) external;
}
```
- `initConfig` is `abi.encode(uint32 windowSeconds, uint32 ownerFloor)`. Limits are set afterwards by owner setters (Task 6). An account with no limit set for a known token may move **zero** of it.
- `MockGovernedAccount`:
  - a minimal 7579 account: `execute(bytes32 mode, bytes executionCalldata)` wraps the call in `hook.preCheck`/`hook.postCheck`
  - `installModule` / `isModuleInstalled`
  - takes no signatures; the test sets the role on `MockOperationContext`

**Classification (spec §6.2, D-N).**
- **Admin** means any of:
  - the selector is `installModule` / `uninstallModule`
  - an `execute` whose every target is the account itself or an installed module (including the hook)
  - any selector on the account other than `execute` / `executeFromExecutor`
  - an owner `execute` whose every target is a governance-set **protocol target** (`ActionAnchor`,
    XNS) with zero native value (spec §6.2 amendment, S-J). Add the governance setter
    `setProtocolTarget(address, bool)` in Task 6
- Admin requires `roleOf == Owner`, or `Maintenance` calling only the hook (tighten-only, enforced in Task 6). Otherwise it reverts `NotOwner()`. Admin skips checks 1–7.
- **Value-moving** is everything else. Delegatecall mode reverts `DelegatecallDenied()` unless `roleOf == Owner`.

**Checks 1–3, in order, on every value-moving operation (including the owner's):**
1. `vault.stakeOf(account).frozen` → `Frozen()`
2. `!registry.isRegisteredAgent(account)` → `NotRegistered()`
3. AIS:
   - `ais.postedAt(account) == 0` → `AwaitingFirstCheckpoint()`
   - `block.timestamp - postedAt > maxCheckpointAge` → `AisStale(uint64 postedAt)`
   - `score < max(protocolFloor, ownerFloor)` → `AisBelowFloor(uint32 score, uint32 floor)`

- [ ] **Step 1: Write the failing tests** in `IntegrityHookCore.t.sol`. The fixture registers the mock account, posts a checkpoint at 8000 and sets `maxCheckpointAge = 1 days`.
```solidity
function test_admin_always_allowed_for_owner_even_when_frozen_and_unscored() public; // frozen + no checkpoint; owner installModule succeeds
function test_admin_by_session_reverts_NotOwner() public;
function test_owner_anchor_is_admin_even_when_frozen() public;     // protocol target, owner, frozen + unscored → succeeds
function test_session_call_to_protocol_target_NotOwner() public;
function test_value_reverts_Frozen() public;
function test_value_reverts_NotRegistered_and_after_retire() public;
function test_value_reverts_AwaitingFirstCheckpoint() public;      // fresh account, no checkpoint
function test_value_reverts_AisStale_after_maxCheckpointAge() public; // warp 1 days + 1
function test_value_reverts_AisBelowFloor_max_of_protocol_and_owner() public; // protocol 5000, owner 9000, score 8000 → floor 9000
function test_owner_value_op_still_runs_checks_1_to_3() public;    // owner, frozen → Frozen()
function test_delegatecall_denied_for_session() public;            // Review Focus 3
function test_constructor_rejects_zero_maxCheckpointAge() public;
```
Use `vm.expectRevert(abi.encodeWithSelector(IntegrityHook.AisBelowFloor.selector, uint32(8000), uint32(9000)))` style assertions.
- [ ] **Step 2: Run them.** `forge test --match-path test/wallet/IntegrityHookCore.t.sol`. Expected: FAIL (does not compile).
- [ ] **Step 3: Implement** the interfaces, mocks and hook core with the signatures above. Storage layout and the window algorithm are the builder's call (spec §11). Reserve one unused `bytes32` slot in the per-account config for stake collateral (D-L).
- [ ] **Step 4: Run them again.** Expected: all PASS.
- [ ] **Step 5: Commit** with `feat(wallet): IntegrityHook core — classification + freeze/registered/AIS checks`.

---

### Task 4: Token decoding, allowlist, limits, measured window

**Files:**
- Modify: `contracts/src/wallet/IntegrityHook.sol`
- Test: `contracts/test/wallet/IntegrityHookLimits.t.sol`

**Interfaces:**
- Consumes: Task 3's hook and fixture.
- Produces:
  - `function windowSpent(address account, address token) external view returns (uint256);`, where `token == address(0)` means native
  - errors `NotAllowlisted(address target)`, `UnknownSelector(address token, bytes4 selector)`, `LimitExceeded(address token, uint256 attempted, uint256 remaining)`

**Rules (spec §6.2 items 4–6):**
- **Allowlist (default on).** Every target, and every `approve` spender, must be allowlisted; otherwise `NotAllowlisted`.
- **Known tokens are governance-set (Task 6).** On a known token, the hook decodes `transfer`, `transferFrom` (counts only when `from == account`), `approve`, `safeTransferFrom`, `burn` and `burnFrom`. Any other selector reverts `UnknownSelector`.
- **Per-call cap.** Checked in `preCheck` on the decoded amount.
- **Window cap.**
  - `preCheck` returns the account's balances of known tokens and native in `hookData`.
  - `postCheck` adds each measured decrease to the window and reverts `LimitExceeded` if the window is exceeded.
  - **`approve` amounts are added to the window at `preCheck` time** (Review Focus 1).
  - Native value is capped per call and per window like a token, with `token = address(0)`.

- [ ] **Step 1: Write the failing tests.** Fixture: ITK known, perCall 100e18, perWindow 250e18, window 1 days, native perCall 1 ether, perWindow 2 ether.
```solidity
function test_transfer_within_caps_passes_and_counts() public;      // 100e18 → windowSpent == 100e18
function test_per_call_cap_LimitExceeded() public;                  // 100e18 + 1
function test_window_boundary_and_reset() public;                   // 100+100+50 ok; +1 wei fails; warp 1 days → 100e18 ok (Review Focus 4)
function test_batch_split_caught_by_window() public;                // batch of 3×100e18 → LimitExceeded in postCheck (Review Focus 2)
function test_approve_counts_against_window() public;               // approve 200e18 then transfer 100e18 → LimitExceeded (Review Focus 1)
function test_approve_to_unlisted_spender_NotAllowlisted() public;
function test_unknown_selector_on_known_token_denied() public;      // e.g. increaseAllowance → UnknownSelector
function test_burn_and_burnFrom_capped() public;
function test_unlisted_target_NotAllowlisted() public;
function test_native_and_token_conjunction() public;                // batch: 1 ether + 100e18 ok; 1 ether + 1 wei native in same window → fails
function test_undecoded_movement_counted_by_measured_delta() public; // known token pulled by an allowlisted contract via prior approval → window rises
function test_leaked_session_key_stops_at_limits() public;          // loop of session transfers halts at 250e18 total
```
- [ ] **Step 2: Run.** `forge test --match-path test/wallet/IntegrityHookLimits.t.sol`. Expected: FAIL.
- [ ] **Step 3: Implement** the decoding, allowlist, per-call caps and the measured window.
- [ ] **Step 4: Run** `forge test --match-path 'test/wallet/*'`. Expected: all PASS.
- [ ] **Step 5: Commit** with `feat(wallet): token decoding, allowlist, caps, measured window`.

---

### Task 5: Mode gates and owner override

**Files:**
- Modify: `contracts/src/wallet/IntegrityHook.sol`
- Test: `contracts/test/wallet/IntegrityHookModes.t.sol`

**Interfaces:**
- Produces:
```solidity
function coSignDigest(address account, address target, uint256 value, bytes32 dataHash, uint256 nonce, uint256 deadline)
    external view returns (bytes32); // EIP-712, domain ("IntegrityHook","1")
function coSignNonce(address account) external view returns (uint256);
error CoSignerRequired();
error OwnerApprovalRequired();
error Paused();
```

**Rules (spec §6.2 item 7 and owner override):**
- **Shield co-signature.**
  - When a co-signer is set, each value-moving session execution needs `ctx.coSignatureOf(account)` to be an ECDSA signature by the co-signer over `coSignDigest(...)`, with the current nonce and `deadline >= block.timestamp`. Otherwise it reverts `CoSignerRequired`.
  - For a batch, one signature per execution, in order (`abi.encode(bytes[])`).
  - The nonce increments per execution.
- **Owner approval.** A session-key transfer of a known token above `ownerApproveAbove[token]` reverts `OwnerApprovalRequired`.
- **Pause.** While paused, session value-moving operations revert `Paused`.
- **Owner override (D-F).** `roleOf == Owner` skips limits, allowlist, co-sign, owner-approve and pause, but still passes checks 1–3. Its measured spend still counts toward the window.

- [ ] **Step 1: Write the failing tests.**
```solidity
function test_cosign_required_when_cosigner_set() public;           // no sig → CoSignerRequired
function test_cosign_valid_passes_and_nonce_increments() public;
function test_cosign_replay_and_expired_deadline_rejected() public;
function test_owner_approve_threshold() public;                     // session 60e18 with threshold 50e18 → OwnerApprovalRequired; owner same → passes
function test_owner_override_skips_limits_not_freeze_or_floor() public; // owner 1000e18 passes; then frozen → Frozen; score < floor → AisBelowFloor
function test_owner_spend_counts_toward_window() public;
function test_paused_blocks_session_not_owner() public;
```
Co-signer test key: `vm.createWallet("cosigner")` (spec §8: test co-signer key).
- [ ] **Step 2: Run.** `forge test --match-path test/wallet/IntegrityHookModes.t.sol`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `forge test --match-path 'test/wallet/*'`. Expected: all PASS.
- [ ] **Step 5: Commit** with `feat(wallet): co-sign, owner-approve, pause, owner override`.

---

### Task 6: Config writers — owner, maintenance (tighten-only), governance

**Files:**
- Modify: `contracts/src/wallet/IntegrityHook.sol`
- Test: `contracts/test/wallet/IntegrityHookConfig.t.sol`

**Interfaces:**
- Produces. Account setters, where `msg.sender` is the account and the role is read from ctx:
```solidity
function setTokenLimit(address token, uint128 perCall, uint128 perWindow) external;
function setNativeLimit(uint128 perCall, uint128 perWindow) external;
function setWindow(uint32 windowSeconds) external;
function setAllowlisted(address target, bool allowed) external;
function setAllowlistEnabled(bool enabled) external;
function setCoSigner(address coSigner) external;           // address(0) = off
function setOwnerApproveAbove(address token, uint128 threshold) external; // 0 = off
function setOwnerFloor(uint32 floor) external;            // >= protocolFloor, <= 10000
function pause() external;
function unpause() external;                              // Owner only
```
- Governance setters (`GOVERNANCE_ROLE`):
```solidity
function setProtocolFloor(uint32 floor) external;
function setMaxCheckpointAge(uint64 age) external;        // > 0
function setKnownToken(address token, bool known) external;
function setOperationContext(IOperationContext ctx) external;
```
- Errors: `LoosenNotAllowed()`, `FloorBelowProtocol(uint32 floor, uint32 protocolFloor)`.
- Owner role: any value. Session role: `NotOwner`.
- Maintenance role may only tighten:
  - lower caps
  - a shorter window
  - remove from the allowlist
  - enable the allowlist
  - set a co-signer only when none is set
  - lower the owner-approve threshold, or turn it on
  - raise the owner floor
  - pause

  Anything else reverts `LoosenNotAllowed`. Maintenance can never move value: a value-moving operation with `roleOf == Maintenance` reverts `NotOwner`.

- [ ] **Step 1: Write the failing tests.**
```solidity
function test_owner_can_loosen_and_tighten() public;
function test_session_cannot_write_config() public;                 // NotOwner
function test_maintenance_tighten_only_each_setter() public;        // one assert per setter: tighten ok, loosen → LoosenNotAllowed
function test_maintenance_can_pause_not_unpause() public;
function test_maintenance_cannot_spend() public;                    // value op with Maintenance role → NotOwner
function test_owner_floor_cannot_go_below_protocol() public;        // FloorBelowProtocol
function test_governance_setters_role_gated() public;
function test_raising_protocol_floor_applies_to_existing_accounts() public; // I6
```
- [ ] **Step 2: Run.** `forge test --match-path test/wallet/IntegrityHookConfig.t.sol`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `forge test --match-path 'test/wallet/*'`. Expected: all PASS.
- [ ] **Step 5: Commit** with `feat(wallet): owner/maintenance/governance config writers`.

---

### Task 7: `AgentRegistry` v3 — governed actor replaces the codehash pin

**Files:**
- Modify: `contracts/src/framework/AgentRegistry.sol`:
  - constructor :112–118, removing the `SovereignAgent` reference instance and `agentCodehash` (:62)
  - `isGatedAccount` :309
  - `_bindActor` :335
  - `setDomain` :228
- Modify: `contracts/test/framework/AgentRegistryBase.sol`, so the fixture binds a `MockGovernedAccount`
- Test: `contracts/test/framework/AgentRegistryV3.t.sol`
- **Fate of the existing tests that bind a `SovereignAgent` as actor.** Verify each with grep before acting, and list them in the commit body.

| File | Fate | Reason |
|---|---|---|
| `test/framework/AgentRegistry.t.sol`, `AgentRegistryInvariants.t.sol` | **port** to the mock governed account | registry behaviour is unchanged apart from actor admission |
| `test/trust/AgentRegistryGate.t.sol`, `ProtocolPinnedGate.t.sol` | **delete** | they test the codehash pin, which §6.5 removes |
| `test/trust/ExecuteGating.t.sol`, `ConfinedAgentE2E.t.sol`, `SovereignAgentD4.t.sol` | **delete** | `SovereignAgent` can no longer bind as actor; its gating is superseded by the `IntegrityHook` tests (§3.2, §6.8) |
| `test/SovereignAgent.t.sol`, `AgentPrimitivesFactory.t.sol` | **keep** | they don't use `AgentRegistry`; the contracts stay until a later retirement plan |

**Interfaces:**
- Consumes: `IAccountVerifier` and `IntegrityHook.isConfigured` (Task 3).
- Produces:
```solidity
function setIntegrityHook(address hook) external;               // DEFAULT_ADMIN_ROLE, once; HookAlreadySet()
function setAccountVerifier(IAccountVerifier v) external;      // DEFAULT_ADMIN_ROLE
function isGoverned(address actor) public view returns (bool);
error GovernanceNotWired();
error NotGoverned(address actor);
error GuardianNotOwner(address guardian, address owner);
```
- **The constructor becomes `constructor(address admin, address domainRegistry_)`.** The signature is unchanged, so `Deploy.s.sol` still compiles.
- **`isGoverned(actor)`** is true only when all of these hold:
  - `actor.code.length != 0`
  - `verifier.verify(actor).genuine`
  - `IERC7579Account(actor).isModuleInstalled(4, hook, "")`
  - `hook.isConfigured(actor)`

  Each external call is wrapped in `try`/staticcall, and a revert means false.
- **`_bindActor`:**
  - Requires `hook != 0 && verifier != 0`, else `GovernanceNotWired`.
  - Requires `isGoverned(actor)`, else `NotGoverned`.
  - Requires `r.guardian == verify(actor).owner`, else `GuardianNotOwner` (I3).
  - Consent is unchanged (`msg.sender == actor` or 1271).
  - **Drops** `ActorRequiresDomain` and `_requirePolicy`. `recordJoin` runs only when `domainId != 0` (domain is a label, §6.5).
- **`setDomain`:** drops `_requirePolicy`.
- **`isGatedAccount`:** removed. Grep `src/`, `script/`, `integrity-oracle/` and `integrity-sdk/` for callers first. Expected: none outside the deleted tests.

- [ ] **Step 1: Write the failing tests.**
```solidity
function test_bind_governed_actor_succeeds_without_domain() public;
function test_bind_reverts_GovernanceNotWired() public;
function test_bind_reverts_NotGoverned_when_hook_not_installed() public;
function test_lying_account_not_governed() public;                  // isModuleInstalled→true but verifier.genuine=false (Review Focus 5)
function test_bind_reverts_GuardianNotOwner() public;
function test_hook_uninstall_makes_actor_ungoverned() public;       // spec §9: removal → isGoverned false
function test_setIntegrityHook_only_once() public;
function test_setDomain_no_policy_required() public;
```
- [ ] **Step 2: Run.** `forge test --match-path test/framework/AgentRegistryV3.t.sol`. Expected: FAIL.
- [ ] **Step 3: Implement**, then port and delete the tests per the table.
- [ ] **Step 4: Run the full suite** with `forge test`. Expected: all PASS, with no remaining reference to `isGatedAccount` or `agentCodehash` in `AgentRegistry.sol`.
- [ ] **Step 5: Commit** with `feat(registry): v3 — governed actor (hook + verifier) replaces codehash pin; domain optional`. The commit body lists every deleted or ported test.

---

### Task 8: Halmos proofs ported to `IntegrityHook`, plus a CI job

**Files:**
- Create: `contracts/test/halmos/IntegrityHookProperties.t.sol`. Port from `git show kernel-phase1-archive:contracts/test/halmos/KernelProperties.t.sol`.
- Modify: `.github/workflows/ci.yml`, adding a `halmos` job

**Properties.** Each is a `check_` function over symbolic inputs. Spec §9 maps them to the archived functions:

| New | From archived |
|---|---|
| `check_perCallTokenContainment(uint256 amount)` | `check_nativeBudgetContainment` (:35) |
| `check_windowContainmentAcrossTwoCalls(uint256 a, uint256 b)` | `check_cumulativeBudgetContainmentAcrossTwoCalls` (:118) |
| `check_tokenAndNativeConjunction(uint256 t, uint256 n)` | `check_tokenBudgetContainmentAndNativeConjunction` (:218), `check_nativeBudgetStillEnforcedOnTokenTrackingKernel` (:262) |
| `check_aisGating(uint32 score, uint64 age)` | `check_reputationAndAssuranceTierGating` (:302) |
| `check_reentrancyCannotExceedWindow(uint256 outer, uint256 nested)` | `check_reentrancyGuardIsSound` (:382) |

- The invariant asserted in every property: **session-role spend through the hook never exceeds the configured caps**. `check_aisGating`: a value move succeeds only if `postedAt != 0`, the checkpoint is not stale, and `score >= floor`.

- [ ] **Step 1: Install Halmos.** Run `uv tool install halmos` and record the resolved version (`halmos --version`). That version is pinned in CI.
- [ ] **Step 2: Write the five properties, then run** `halmos --contract IntegrityHookProperties`. Expected: every `check_` reports `[PASS]`.
- [ ] **Step 3: Prove each property can fail.** For each one, temporarily weaken the hook: per-call check removed, window add removed, native ignored, staleness ignored, reentrancy lock removed. Confirm the matching `check_` reports a counterexample, then restore. Record the five results in the commit body. This evidence is required because a proof that cannot fail measured nothing.
- [ ] **Step 4: Add the CI job.** `halmos` mirrors the existing `contracts (forge test)` job setup (checkout with submodules, Foundry, `node_modules`), then runs `uv tool install halmos==<pinned>` and `halmos --contract IntegrityHookProperties`.
- [ ] **Step 5: Commit and push.** Commit with `test(halmos): port kernel budget/AIS/reentrancy proofs to IntegrityHook + CI job`, then `xb-wt push`.

---

### Task 9: Anvil deploy of the trust layer + hook + registry v3

The wallet stack itself (factory, validators, EntryPoint, real adapters) is deployed in Plan 1b. Here the deploy wires the hook with **placeholder adapters that fail closed**: `roleOf` returns `None`, and `verify` returns `(false, 0)`. No actor can bind until 1b swaps them in.

**Files:**
- Modify: `contracts/script/Deploy.s.sol`, which deploys `IntegrityHook` after `AISRegistry`/`StakeVault` and wires `agentRegistry.setIntegrityHook` and `setAccountVerifier`
- Create: `contracts/src/wallet/FailClosedAdapters.sol` (`FailClosedOperationContext`, `FailClosedAccountVerifier`)
- Modify: `deployments.local.json`, gaining keys `integrityHook`, `operationContext` and `accountVerifier`
- Test: `contracts/test/wallet/DeployLocal.t.sol`

**Interfaces:**
- Produces:
  - deployment JSON keys `integrityHook`, `operationContext` and `accountVerifier`, beside the existing `agentRegistry`, `aisRegistry` and `stakeVault`
  - hook constructor values: `protocolFloor = 0` (D-K: zero until scoring is verified live) and `maxCheckpointAge = 7 days`

  Both are governance-changeable. Give 7 days as the builder's default in the PR description, so the owner can change it.

- [ ] **Step 1: Write the failing test.** `DeployLocal.t.sol` runs the script in-process and asserts:
  - the hook has `protocolFloor() == 0`
  - `agentRegistry.integrityHook() == hook`
  - `isGoverned(anyEOA) == false`
  - binding any actor reverts `NotGoverned`
- [ ] **Step 2: Run** `forge test --match-path test/wallet/DeployLocal.t.sol`. Expected: FAIL.
- [ ] **Step 3: Implement the adapters and the script changes.**
- [ ] **Step 4: Verify on a real Anvil.** Run `anvil &` and then `forge script script/Deploy.s.sol --rpc-url http://127.0.0.1:8545 --broadcast`. Then `cast call <integrityHook> "protocolFloor()(uint32)"` returns `0`.
- [ ] **Step 5: Run `forge test`, then commit and push.** Expected: the full suite passes. Commit with `feat(deploy): wire IntegrityHook + registry v3 on Anvil with fail-closed adapters`, then `xb-wt push`.
- [ ] **Step 6: Open the PR.** Run `gh pr create --fill`. Wait for CI and require every JSON check bucket to be `pass`. Then merge with `gh pr merge <n> --squash --match-head-commit <sha>`. This touches no Oracle code, so the Render autoDeploy rebuilds an unchanged Oracle.

---

## Roadmap — the plans after this one

Each later plan is written when its dependency is met. None is written now, because each depends on a spike answer or an unapproved design.

| Plan | Scope (spec §) | Written after |
|---|---|---|
| **1b — Wallet stack integration** | Real `IOperationContext` / `IAccountVerifier` for the chosen stack; `IntegrityGuard` if needed (§6.1); session-key policies (§6.3) and the 1271-forbidden test; Anvil deploy of the stack; fork tests (EntryPoint v0.7, live agent0 `register` from the wallet → `agentWallet == wallet`); the owner-path-through-`execTransaction` test (§9) | Task 1 decision record reviewed by the owner |
| **2 — Oracle** | Pending-registration store; `wallet_invariant`, `governed` and `ownership` on `/v1/agent/{id}/onchain/sync` and `/erc8004`; initial checkpoint at `bootstrapScore ≥ freezeThreshold`. **Additive only**: `controller` stays (deprecated) beside `owner`/`session_key`/`wallet` until the consumers move, because merging deploys. Migrations 0028+ land on live Supabase schema `oracle` and need the postgres role | Plan 1b |
| **3 — SDK + CLI** | §6.8, built inside the SDK/CLI redesign layout (`AgentAccount`, `Signer`, handoff, readiness checks) | SDK/CLI design approved |
| **4 — Console** (integrity-console, own `xb-wt` worktree) | §6.9 finish-setup, agent page, spending panel, approvals. Its e2e workflow never runs in CI (subdirectory), so this plan either adds a root `ci.yml` job or records local Playwright evidence | Plans 2 and 3 |
| **5 — End-to-end, runbook, canary** | §7 items 2 and 4, plus the §9 live canary (built, not enabled) | Plans 1b–4 |
