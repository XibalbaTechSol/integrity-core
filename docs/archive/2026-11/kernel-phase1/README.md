# Phase I kernel — archived 2026-11-16

**Do not implement from this file.** It records what was removed from `main`, why, and how to bring it back.

| | |
|---|---|
| Archived at | `5668854c116c90f23348bdd22783a88b66f16fd7` (last `main` commit containing the kernel) |
| Tag | `kernel-phase1-archive` (annotated, points at the commit above) |
| Decision | Owner kernel review, 2026-11-16: archive, refactor later on a real product trigger |
| Not archived | `IntegrityIdentityReadV1`, `IntegrityERC8004Registry` (still in `contracts/src/kernel/`), `ReputationRegistry`, `IZkVerifier`, `RejectAllZkVerifier` — other live contracts and BCC use them; their removal is the separate held-graph deletion PR |

## What it was

Two contracts that enforce spending rules on an agent's on-chain wallet:

- **`IntegrityKernel`** — an ERC-7579 type-4 hook bound immutably to one account. Before every `execute()` it reverted unless all of these held:
  - native-value spend within a per-operation and a cumulative budget (measured as a real balance delta in `postCheck`);
  - optionally the same two budgets for one immutable ERC-20 `trackedToken`, read live;
  - the cached `ReputationRegistry.effectiveScore(account)` at or above `minEffectiveScore`, with the cache no older than `epochLengthSeconds` (≤ `MAX_EPOCH_LENGTH_SECONDS`); a stale cache reverted `SnapshotStale`, and `refreshReputationSnapshot()` was permissionless;
  - optionally a live ZK assurance tier (`requireAssuranceTier`, off since A4).
- **`IntegrityAccount`** — the ERC-4337 / ERC-7579 account it guarded: single `CALLTYPE_SINGLE` execution mode, guardian set with threshold, timelocked kernel swap (`proposeKernelSwap` / `executeKernelSwap`), guardian rotation, and a timelocked rescue sweep. Its constructor enforced kernel epoch ≥ module-action timelock.

It never inspected calldata and constrained no asset other than native ETH and the one tracked token. Since A4 (2026-09-28, `ff8e22c4`) policy reached it only as constructor scalars compiled from a signed pack; the on-chain `AdapterRegistry` hook was removed.

## Why it was archived

1. **Disconnected from registration v3.** It read a per-agent `ReputationRegistry` clone. The only writer of those clones was BCC's scoring loop, which finds them through the Oracle `primitives` record that v3 agents do not have. v3 scores live in `AISRegistry` (0–10000, `SCORER_ROLE` checkpoints).
2. **No product consumer.** The near-term product is the off-chain Cortex + Shield loop. No customer agent holds or spends funds from an on-chain wallet.
3. **The deployed reference was dormant.** Base Sepolia `experimentalPhase1Reference` (read 2026-11-15): snapshot ~84 days old against a 3-day epoch, so every `execute()` reverted `SnapshotStale`; account balance 0, nothing ever spent; registry score 800, unchanged since 2026-08-24. It was also built from the pre-A4 source.
4. **Proofs were not continuously checked.** The Halmos properties ran only via a manual `make verify-kernel`; `forge test` skips `check_` functions. Git shows no run after A4 rewrote ~130 lines of the kernel.

Archiving loses little: the kernel touched only `ReputationRegistry.scores()` and the two ZK-boost constants, so porting it later costs about what porting it now would.

## Files removed from `main`

Restore any of them with `git show 5668854c:<path>`.

| Path | Notes |
|---|---|
| `contracts/src/kernel/IntegrityKernel.sol` | 425 lines |
| `contracts/src/kernel/IntegrityAccount.sol` | 983 lines |
| `contracts/test/IntegrityAccount.t.sol` | 121 tests |
| `contracts/test/kernel/IntegrityKernelAssuranceTier.t.sol` | 7 tests |
| `contracts/test/halmos/HalmosKernelFixture.sol` | shared Halmos fixture |
| `contracts/test/halmos/KernelProperties.t.sol` | 6 properties (below) |
| `contracts/test/halmos/KernelSwapHarness.t.sol` | 2 properties (below) |
| `contracts/script/DeployKernelReference.s.sol` | Base Sepolia reference deploy |
| `contracts/script/DeployKernelBridgeTestbed.s.sol` | local EntryPoint testbed |
| `contracts/script/SubmitKernelBridgeUserOp.s.sol` | UserOp submission proof |

Also removed: the `verify-kernel` Makefile target (Halmos 0.3.3 in `contracts/.venv-halmos`, `forge build --ast`), the `deployments.local.kernel-bridge.json` entries in `foundry.toml` and `.gitignore`, the console Kernel page and Guided System Test kernel step (integrity-console), and the Cortex kernel bridge (xibalba-cortex).

### Halmos properties (as of the archive commit)

`check_nativeBudgetContainment`, `check_cumulativeBudgetContainmentAcrossTwoCalls`, `check_tokenBudgetContainmentAndNativeConjunction`, `check_nativeBudgetStillEnforcedOnTokenTrackingKernel`, `check_reputationAndAssuranceTierGating`, `check_reentrancyGuardIsSound` (KernelProperties); `check_placeholderSwapSucceedsViaRealGovernancePath`, `check_realKernelSwapInSucceeds` (KernelSwapHarness).

## On-chain record

The Base Sepolia contracts stay deployed and unused. `deployments.baseSepolia.json` → `experimentalPhase1Reference` keeps their addresses with an `ARCHIVED` status: `IntegrityAccount` `0x25858C53818E777C5569163F2e05570314fC947d`, `IntegrityKernel` `0x3e05E67Fb6dd3eE382eD24150141ffcBE2C9c338`, `ReputationRegistry` `0x5f235388aD02bc7c5426B7f8d2773a17DeB9A616`. Do not refresh or fund them.

## Spec and pack consequences

- `docs/SPEC.md` keeps the kernel's normative requirements (§4.2, §5.2, M1–M5). Rows that were `[EXPERIMENTAL]` because this slice existed are now `[PLANNED]`; no MUST/SHOULD text changed.
- Pack `kernel_range` / `kernel:` compatibility fields remain in the pack schema but no longer map to any on-chain enforcement. The pack schema was deliberately not changed.

## Revival

**Trigger:** a product that needs on-chain spend enforcement for agent funds — agents holding their own wallets, pay-per-call on-chain settlement, or a chain-enforced spend cap sold as a feature.

**Port steps:**

1. Restore the files from the tag into a worktree (`git checkout kernel-phase1-archive -- <paths>`).
2. Replace the `ReputationRegistry` dependency with a minimal read interface backed by `AISRegistry`. Drop `ZK_BOOST_BPS` / `BPS_DENOMINATOR` and `BoostConstantsMismatch`; the ZK boost is retired.
3. Decide the identity mapping: `AISRegistry` scores an agent address, the kernel is bound to an `IntegrityAccount`. Either register the account as the agent's actor in `AgentRegistry`, or score the account address directly.
4. Convert `minEffectiveScore` from the 0–1000 `effectiveScore` scale to 0–10000 explicitly, in code and tests.
5. Rerun Halmos (`make verify-kernel` from the tag) and repair the properties, then **add a CI job** so the proofs cannot go stale again.
6. Confirm that something actually posts `AISRegistry` checkpoints for the target agents before deploying — otherwise the kernel enforces a frozen number, which is the state it was archived in.
7. Redeploy a fresh reference instead of reviving `experimentalPhase1Reference`.
