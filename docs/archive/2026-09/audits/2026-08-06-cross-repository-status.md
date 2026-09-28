# Integrity Protocol — Audit Status

Status: AUDIT IN PROGRESS · 2026-08-06

This page records the current codebase audit for `integrity-core`. The consolidated cross-repository implementation plan is `/home/xibalba/Documents/INTEGRITY — Cross-Repository Audit and Implementation Plan.md`.

## Current verified state

- Clean default-branch audit commit: `bed263a8001ad6c975260d29f1876d8f800f7d2a`.
- Active local audit branch/worktree evidence also exists at `f474f2f`; package counts differ between these baselines and must not be merged into one unqualified total.
- Clean default-branch evidence: Solidity 200 tests; Zero-Knowledge 4 tests; CLI 68 passed/1 skipped; dashboard 68 passed; SDK 242 passed/2 failed/3 skipped; middleware 119 passed; User API 51 passed with temporary PostgreSQL.
- Active audit-branch evidence: Solidity 200 tests; Zero-Knowledge 4 tests; Oracle 143 tests; SDK 252 passed/2 skipped; CLI 68 passed/1 skipped; middleware 121 pytest plus 43 OPA tests; dashboard 68 tests and production build passed.
- The active branch's dashboard lint failed in 3 files; the standalone MVP lint passed with Oxlint in that branch. These are separate repositories and separate commands.

## Deployment evidence boundary

Base Sepolia bytecode was directly observed at declared protocol addresses, including the registry, token, and verifier address. This proves bytecode exists at those addresses only. `contracts/src/oracle/UltraPlonkVerifier.sol:42-50` still implements a fail-closed placeholder whose `verify()` reverts with `PlaceholderVerifierNotYetGenerated()`. The on-chain verifier is therefore not a working production Zero-Knowledge verifier.

## Open findings

1. `integrity-sdk/tests/unit/test_hardware.py` is out of sync with `integrity_sdk/hardware.py`: the test mocks `subprocess.run`, but the current implementation uses `/proc/cpuinfo` and `/.dockerenv`. The clean main branch therefore reports 2 test failures, while open PR #48 updates the tests and has green CI. This is a test/implementation contract drift finding, not proof that production hardware detection is correct.
2. Aggregate `make test` timed out during SDK tests; no aggregate pass is claimed. The corresponding main CI failure is [run 31087969036](https://github.com/XibalbaTechSol/integrity-core/actions/runs/31087969036).
3. `.github/workflows/auto-merge-jules.yml` grants automatic review/merge authority to a bot, which conflicts with the required human-review/no-automatic-merge policy.
4. Base Sepolia deployment records, roles, bytecode, and source matches require direct chain verification.
5. Production gaps and package READMEs contain a mixture of closed, partial, planned, blocked, and historical claims; the canonical reconciliation is still in progress.

## Documentation drift found

- Root README and testing/wiki pages contain historical test counts that differ from both clean-main and active-branch runs; counts must be labeled by commit and command.
- `docs/MAINNET_READINESS.md` still describes identity-ceiling enforcement as open even though current Rust tests cover tier ceilings; reconcile the readiness document without deleting historical rationale.
- Broad “real ZK pipeline” wording must distinguish tested off-chain Noir/Barretenberg proving from the deployed on-chain placeholder verifier.
- The wiki structure is sound, but the delegated linter found 0 orphan/dead links and 18 pages stale by more than 14 days.

## Production posture

This repository is a strong testnet protocol prototype with broad tested surfaces. It is not production-ready. Production readiness additionally requires complete reproducible CI, deployment/source matching, security and identity review, rollback and monitoring controls, secret handling, replay/origin controls, and explicit treatment of all normative gaps.

Historical documents remain historical. Current status belongs in this page, `PRODUCTION_GAPS.md`, the root README, and the canonical wiki.
