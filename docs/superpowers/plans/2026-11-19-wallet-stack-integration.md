# Agent Wallet — Plan 1b: Safe + Safe7579 + Smart Sessions Integration

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate the chosen wallet stack (Safe v1.4.1 + Rhinestone Safe7579 v1.0.0 + Smart Sessions) into Integrity Protocol. Implement production `IOperationContext` and `IAccountVerifier` adapters, the Safe `IntegrityGuard`, session-key policy safeguards (I4 ERC-1271 disabled), Anvil stack setup, and comprehensive Base Sepolia fork integration tests (including EntryPoint v0.7 UserOps and live Agent0 passport registration).

**Architecture:**
- **Stack Core:** Safe v1.4.1 proxy deployed via canonical `SafeProxyFactory` (`0x4e1DCf7AD4e460CfD30791CCC4F9c8a4f820ec67`) with master copy `0x41675C099F32341bf84BFc5382aF534df5C7461a`.
- **Modular Adapter:** Rhinestone Safe7579 (`0x7579EE8307284F293B1927136486880611F20002`). `IntegrityHook` installed as SIG hooks on standard execution selectors.
- **Session Validator:** Rhinestone Smart Sessions (`0x00000000008bDABA73cD9815d79069c247Eb4bDA`). Ephemeral agent session keys execute UserOps through EntryPoint v0.7.
- **Adapters & Guard:**
  - `SafeAccountVerifier`: verifies genuine Safe origin, single EOA owner, threshold = 1, and that Safe7579 is the *only* enabled module (preventing bypass via rogue modules, F1).
  - `SafeOperationContext`: provides path-based role identification (`Role.Owner` during direct Safe `execTransaction` / guard path, `Role.Session` during Safe7579 UserOps validated by Smart Sessions).
  - `IntegrityGuard`: Safe transaction guard intercepting direct `execTransaction` to ensure owner path respects freeze/registration/floor checks and prevents tampering with modules or the guard itself.
- **Security Constraint (F4 / I4):** Smart Sessions ERC-1271 is strictly forbidden for session keys (`erc7739Policies` must be empty).

**Tech Stack:** Solidity 0.8.28 (cancun, via_ir, optimizer 200), Foundry, ERC-7579, ERC-4337 EntryPoint v0.7, Safe v1.4.1, Base Sepolia fork testing.

**Spec & Decision References:**
- Spec: `docs/superpowers/specs/2026-11-18-agent-wallet-custody-design.md` (§5, §6.1–§6.4, §9).
- Spike Decision Record: `docs/superpowers/specs/2026-11-18-wallet-stack-spike.md`.

---

## Global Constraints

- **Workspace:** All work happens strictly in `/mnt/storage/xibalba/Projects/worktrees/integrity-core/wallet-stack-integration` on branch `feat/wallet-stack-integration`.
- **Pushing & Merging:** Push strictly with `xb-wt push`. PR merge on green CI with `gh pr merge <n> --squash --match-head-commit <sha>`.
- **Fork Tests:** Fork tests use `--fork-url` with pinned block `60684000` against Base Sepolia. Fork tests call `vm.skip(true)` if `BASE_SEPOLIA_RPC_URL` is unset or offline, ensuring local CI remains 100% green without external network access.
- **Immutable Addresses on Base Sepolia:**
  - EntryPoint v0.7: `0x0000000071727De22E5E9d8BAf0edAc6f37da032`
  - Safe Singleton v1.4.1: `0x41675C099F32341bf84BFc5382aF534df5C7461a`
  - SafeProxyFactory v1.4.1: `0x4e1DCf7AD4e460CfD30791CCC4F9c8a4f820ec67`
  - Safe7579 Adapter v1.0.0: `0x7579EE8307284F293B1927136486880611F20002`
  - Safe7579 Launchpad v1.0.0: `0x7579011aB74c46090561ea277Ba79D510c6C00ff`
  - Smart Sessions: `0x00000000008bDABA73cD9815d79069c247Eb4bDA`
  - OwnableValidator: `0x000000000013fdB5234E4E3162a810F54d9f7E98`
  - Agent0 Identity Registry: `0x8004A818BFB912233c491871b3d84c89A494BD9e`

---

## Tasks

### Task 1: `SafeAccountVerifier` (`contracts/src/wallet/SafeAccountVerifier.sol`)

Implements `IAccountVerifier` specifically for the Safe v1.4.1 + Safe7579 architecture.

**Files:**
- Create: `contracts/src/wallet/SafeAccountVerifier.sol`
- Create: `contracts/test/wallet/SafeAccountVerifier.t.sol`

**Requirements:**
- Implements `function verify(address account) external view returns (bool genuine, address owner)`.
- Validates:
  1. `account` has non-zero code.
  2. Mastercopy check: querying `ISafe(account).singleton()` or storage slot 0 matches `safeSingleton` (`0x41675C099F32341bf84BFc5382aF534df5C7461a`).
  3. `ISafe(account).getThreshold() == 1`.
  4. `ISafe(account).getOwners()` contains exactly 1 address, assigned to `owner`.
  5. Module check (Finding F1): Safe7579 adapter is enabled (`isModuleEnabled(safe7579)`).
  6. **Sole enabled module check:** Queries `getModulesPaginated(SENTINEL_MODULES, 10)` to ensure Safe7579 is the *only* enabled module on the Safe. Any auxiliary module enabled returns `(false, address(0))`, preventing module-level hook bypasses.
  7. Guard check: verifies `ISafe(account)` has `integrityGuard` installed if required by configuration.

- [ ] **Step 1: Write unit tests in `SafeAccountVerifier.t.sol`.** Test:
  - Valid Safe returns `(true, owner)`.
  - Non-contract or zero address returns `(false, address(0))`.
  - Multi-owner Safe or threshold != 1 returns `(false, address(0))`.
  - Safe without Safe7579 enabled returns `(false, address(0))`.
  - Safe with an extra rogue module enabled returns `(false, address(0))`.
- [ ] **Step 2: Run test.** `forge test --match-path test/wallet/SafeAccountVerifier.t.sol` -> Expected FAIL.
- [ ] **Step 3: Implement `SafeAccountVerifier.sol`.**
- [ ] **Step 4: Re-run test.** `forge test --match-path test/wallet/SafeAccountVerifier.t.sol` -> Expected PASS.
- [ ] **Step 5: Commit:** `feat(wallet): implement SafeAccountVerifier with sole-module and single-owner enforcement`.

---

### Task 2: `SafeOperationContext` (`contracts/src/wallet/SafeOperationContext.sol`)

Implements `IOperationContext` providing execution role resolution.

**Files:**
- Create: `contracts/src/wallet/SafeOperationContext.sol`
- Create: `contracts/test/wallet/SafeOperationContext.t.sol`

**Requirements:**
- Implements:
  - `roleOf(address account) external view returns (Role)`
  - `coSignatureOf(address account) external view returns (bytes memory)`
- Role resolution logic (Q3 / F3 from spike):
  - If `integrityGuard.isDirectExecution(account)` is true: returns `Role.Owner`.
  - If called during Safe7579 UserOp execution:
    - Inspects active validator recorded in transient execution state (or query validator registry):
      - Smart Sessions validator -> `Role.Session`.
      - OwnableValidator -> `Role.Owner`.
  - Fallback / unauthorized -> `Role.None`.
- Co-signature extraction:
  - Reads co-signature stored for current execution frame.

- [ ] **Step 1: Write unit tests in `SafeOperationContext.t.sol`.**
- [ ] **Step 2: Run test.** `forge test --match-path test/wallet/SafeOperationContext.t.sol` -> Expected FAIL.
- [ ] **Step 3: Implement `SafeOperationContext.sol`.**
- [ ] **Step 4: Re-run test.** `forge test --match-path test/wallet/SafeOperationContext.t.sol` -> Expected PASS.
- [ ] **Step 5: Commit:** `feat(wallet): implement SafeOperationContext for dual-path owner and session role resolution`.

---

### Task 3: `IntegrityGuard` (`contracts/src/wallet/IntegrityGuard.sol`)

Implements Safe transaction guard (`BaseGuard`) intercepting direct Safe `execTransaction` calls.

**Files:**
- Create: `contracts/src/wallet/IntegrityGuard.sol`
- Create: `contracts/test/wallet/IntegrityGuard.t.sol`

**Requirements:**
- Implements:
  - `checkTransaction(...)`:
    - Flags direct execution on `SafeOperationContext` for the duration of the call.
    - Inspects value-moving vs admin targets.
    - Enforces protocol gates on owner value moves: `StakeVault.frozen == false`, `AgentRegistry.agentOf(account) != 0`, `AISRegistry.score >= floor`.
    - Protects governance configuration: reverts if `to == account` and selector attempts `disableModule(..., safe7579)` or `setGuard(...)` unless approved by governance.
  - `checkAfterExecution(...)`:
    - Clears direct execution flag on `SafeOperationContext`.
    - Invokes hook window accounting if native value was moved.

- [ ] **Step 1: Write unit tests in `IntegrityGuard.t.sol`.**
- [ ] **Step 2: Run test.** `forge test --match-path test/wallet/IntegrityGuard.t.sol` -> Expected FAIL.
- [ ] **Step 3: Implement `IntegrityGuard.sol`.**
- [ ] **Step 4: Re-run test.** `forge test --match-path test/wallet/IntegrityGuard.t.sol` -> Expected PASS.
- [ ] **Step 5: Commit:** `feat(wallet): implement IntegrityGuard to secure Safe execTransaction owner paths`.

---

### Task 4: Invariant I4 / F4 — Session-Key EIP-1271 Denial (`SmartSessionsPolicyCheck.t.sol`)

Machine-check and test that Smart Sessions ERC-1271 signing capability remains strictly disabled for all session keys.

**Files:**
- Create: `contracts/test/wallet/SmartSessionsPolicyCheck.t.sol`

**Requirements:**
- Tests that session keys configured with empty `erc7739Policies` cannot validate signatures via `isValidSignature(bytes32, bytes)`.
- Tests that any session registration containing non-empty `erc7739Policies` is rejected by the SDK/verification helper.
- Formally validates Invariant I4: session keys can never produce verifiable ERC-1271 signatures for arbitrary off-chain messages or authorizations (e.g. permit / EIP-3009).

- [ ] **Step 1: Write test `SmartSessionsPolicyCheck.t.sol`.**
- [ ] **Step 2: Run test on local fork.** `forge test --match-path test/wallet/SmartSessionsPolicyCheck.t.sol` -> Expected PASS.
- [ ] **Step 3: Commit:** `test(wallet): verify Invariant I4 — session keys strictly forbidden from EIP-1271 signature validation`.

---

### Task 5: Genesis Deploy Update (`Deploy.s.sol`) with Real Adapters & Local Anvil Stack

Updates deployment scripts and `DeployLocal.t.sol` to deploy and wire `SafeAccountVerifier`, `SafeOperationContext`, and `IntegrityGuard`.

**Files:**
- Modify: `contracts/script/Deploy.s.sol`
- Modify: `contracts/test/wallet/DeployLocal.t.sol`

**Requirements:**
- `Deploy.s.sol` deploys `SafeOperationContext`, `SafeAccountVerifier`, and `IntegrityGuard`.
- Wires `agentRegistry.setAccountVerifier(safeAccountVerifier)` and `agentRegistry.setIntegrityHook(address(hook))`.
- Serializes `IntegrityGuard`, `SafeAccountVerifier`, and `SafeOperationContext` into `deployments.local.json`.
- `DeployLocal.t.sol` runs in-process, tests deploy script, and verifies configuration.

- [ ] **Step 1: Update `Deploy.s.sol` and `DeployLocal.t.sol`.**
- [ ] **Step 2: Run test.** `forge test --match-path test/wallet/DeployLocal.t.sol` -> Expected PASS.
- [ ] **Step 3: Test on live Anvil.** Broadcast against `http://127.0.0.1:8545` and verify with `cast call`.
- [ ] **Step 4: Commit:** `feat(deploy): wire SafeAccountVerifier, SafeOperationContext, and IntegrityGuard in genesis deploy`.

---

### Task 6: End-to-End Base Sepolia Fork Tests (`Safe7579Fork.t.sol`)

Performs end-to-end user-operation and live integration tests against Base Sepolia fork at block `60684000`.

**Files:**
- Create: `contracts/test/wallet/Safe7579Fork.t.sol`
- Remove: `contracts/test/spike/WalletStackSpike.t.sol` (superseded by production fork test suite)

**Requirements:**
- Fork tests against `https://sepolia.base.org` at block `60684000` (skipped if `BASE_SEPOLIA_RPC_URL` is unset).
- Exercises:
  1. Safe account creation and Safe7579 module enablement via `Safe7579Launchpad`.
  2. `IntegrityHook` installation as execution SIG hook on selectors `0xe9ae5c53` and `0xd691c964`.
  3. `IntegrityGuard` installation on Safe.
  4. Ephemeral session key authorization via Smart Sessions (`0x...8bDABA`).
  5. 4337 UserOp execution through EntryPoint v0.7 (`0x0000000071727De22E5E9d8BAf0edAc6f37da032`):
     - Single ERC-20 transfer within limits -> PASS.
     - Single ERC-20 transfer exceeding limit -> REVERT (`LimitExceeded`).
     - Transfer to unallowlisted target -> REVERT (`NotAllowlisted`).
  6. Direct Safe `execTransaction` by owner:
     - Spend exceeding session limits -> PASS (owner override).
     - Spend while frozen -> REVERT (`Frozen`).
     - Spend below AIS floor -> REVERT (`AisBelowFloor`).
  7. **Live Agent0 Passport Registration:**
     - Smart wallet executes call to live Base Sepolia Agent0 registry `0x8004A818BFB912233c491871b3d84c89A494BD9e`.
     - Asserts that minted passport assigns `agentWallet == address(safeAccount)`.

- [ ] **Step 1: Implement `Safe7579Fork.t.sol` and clean up `WalletStackSpike.t.sol`.**
- [ ] **Step 2: Run fork test.** `BASE_SEPOLIA_RPC_URL=https://sepolia.base.org forge test --match-path test/wallet/Safe7579Fork.t.sol -vv` -> Expected PASS.
- [ ] **Step 3: Run CI suite.** `forge test` (non-fork) -> 100% PASS without network.
- [ ] **Step 4: Commit:** `test(wallet): complete Safe7579 + Smart Sessions fork integration suite and live agent0 verification`.
- [ ] **Step 5: Open PR & Merge:** `gh pr create --fill`, verify all CI checks green, merge via `gh pr merge <n> --squash --match-head-commit <sha>`.
