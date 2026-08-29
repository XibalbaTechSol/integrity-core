# Claude Handoff — CI restored, Phase I guardian-quorum slice mid-implementation

Generated: 2026-08-19T01:46:40Z
Repository: `/home/xibalba/Projects/integrity-core`
Branch: `audit/harness-loop-2026-07-30` (local checkout; not pushed as a branch — see §3 for what
actually reached `origin`)
Worktree: dirty by design, mid-slice. Do not reset, clean, stash, or overwrite. Preserve every
existing tracked and untracked change listed in §5.

Session interrupted by an infrastructure outage (OPA policy-engine unreachable via the local
`pretool_gate.py` BCC hook — DNS resolution failure), not by task completion. **User reports this
is now fixed** (a real, disclosed docker-compose config fix was found in the worktree — see §4 —
but was NOT independently re-verified by this session before the PC restart the user is about to
perform). First action on resume: confirm the fix actually holds (§7, step 1) before trusting it.

---

## 1. Executive state

Two independent threads of work this session:

1. **CI repair — complete, merged, verified green.** `integrity-core` main CI (all 8 jobs),
   `xibalba-cortex`, and `xibalba-shield` are all passing on `main` as of this writing.
2. **Phase I guardian-quorum kernel-governance slice — authorized, ~60% implemented, currently
   does NOT compile.** Contract-side change is done; the test file has one landed edit and one
   large pending edit that never applied because the OPA outage started mid-session. `forge
   build` fails right now with 2 errors (see §6) — both are the OLD 3-argument constructor call
   sites that still need updating to the new 5-argument signature.

Nothing was deployed anywhere. Nothing was pushed to a remote for the Phase I work (it's local,
uncommitted, on the dirty `audit/harness-loop-2026-07-30` checkout).

## 2. CI repair — what shipped, verified

### integrity-core

Root cause (confirmed by reading actual CI failure logs, not assumed from a prior handoff):
1. `integrity-dashboard/eslint.config.js` imports `globals`, undeclared as a dependency.
2. `contracts/foundry.toml` (not just `remappings.txt`, which Foundry ignores once
   `foundry.toml` declares its own `remappings` array — this was the real bug the prior Codex
   handoff's fix missed) was missing the `@openzeppelin/contracts@5.3.0` remapping Chainlink CCIP
   imports need.

Fix: rebased the prior session's `fix/ci-dependency-resolution-20260818` branch (PR #59) onto
current `main` (it had drifted into a real merge conflict after PR #58 landed), resolved conflicts
in `docs/wiki/WIKI_LOG.md`, `docs/wiki/entities/contracts.md`, `integrity-dashboard/package.json`
and its lockfile, added the missing `foundry.toml` remapping as a second commit, discarded two
incidental local-run side effects (`gas_usage.jsonl` telemetry noise, a `contracts/package-lock.json`
prune) before pushing, then verified locally before pushing:

- `forge test`: 250/250 passed
- `integrity-dashboard`: `npm run lint` — 0 errors, 56 pre-existing warnings (matches documented
  baseline)
- `integrity-cli`: 70 passed, 1 skipped
- `integrity-sdk`: 264 passed, 3 skipped

Pushed, all 8 GitHub Actions checks passed, **PR #59 squash-merged into `main` with explicit user
authorization** (merge itself is a gated auto-mode action — I do not merge PRs without asking).
Post-merge CI run on `main` (`32201413978`): **success, all 8 jobs**. Local worktree cleaned up
(`/tmp/integrity-core-ci-fix2` worktree removed, git-pruned).

### xibalba-cortex and xibalba-shield

Both were already fixed and merged **before this session started** — confirmed via `gh run
list`, not re-done: cortex PR #3 (wiki TOC regen) and shield PR #13 (dependency-install fix,
`integrity-sdk` git-subdirectory dependency instead of a local absolute path) both merged with
green CI, per `CODEX_HANDOFF_2026-08-18.md`.

## 3. Phase I guardian-quorum slice — full current state

### 3.1 Why this slice

The tracer-bullet account/kernel (`IntegrityAccountV1Experimental.sol` /
`IntegrityKernelV1Experimental.sol`), three reference adapters (budget, reputation-floor,
assurance-tier), reputation epoch-snapshotting, canonical intent encoding, and a
single-signer-timelocked kernel-swap governance mechanism were **already built, tested, and
merged onto `main`** before this session (via PR #58) — `PRODUCTION_GAPS.md` §29-30 has the full
account. This was a genuine discovery mid-session: the prior handoff's "do not resume Phase I"
framing was stale by the time I read it; the user had already authorized and the work had already
landed.

The existing kernel-swap mechanism's own doc comment discloses a real, named gap: "a compromised
signing key can still eventually force a kernel swap, just not instantly... It does NOT provide
the independent-quorum property real multi-party governance would." User authorized closing
exactly this gap, scoped as its own slice (not a redesign of account authority, not a fix for the
other disclosed risks).

### 3.2 Proposal doc — written, hardened by advisor review, authorized

`docs/plans/2026-08-18-phase1-multiparty-kernel-governance-proposal.md` (status line already
updated to "authorized as scoped (option 1)"). Read it in full before continuing — it is the
source of truth for exactly what this slice does and does not claim. Summary:

- A guardian M-of-N quorum gates **only** `executeKernelSwap`. `proposeKernelSwap` and
  `cancelKernelSwap` stay signer-only, unchanged — deliberately, to avoid slowing the common case
  and to avoid making swap *denial* multi-party (which would reintroduce a stuck-negotiation
  failure mode).
- Guardian set + threshold are immutable, set once at construction. No rotation mechanism in this
  slice (explicitly out of scope).
- Approvals are scoped by a `kernelSwapNonce` bumped once per `proposeKernelSwap` call — no
  clear-on-cancel/clear-on-execute bookkeeping needed; a new nonce alone makes prior approvals
  irrelevant.
- **Two guarantee-document falsifications this slice introduces, both must be disclosed, not
  silently absorbed** (caught by an advisor review before implementation, not after):
  1. `approveKernelSwap` is a NEW state-changing entry point that bypasses the hook entirely —
     the account's own "hook fires on every reachable state-changing path" claim needs a second
     amendment (the swap's install/uninstall asymmetry was the first).
  2. Guardian quorum strictly lengthens real-world elapsed time between propose and execute,
     making the pre-existing timelock-vs-`epochLengthSeconds` staleness collision (already
     documented on `moduleActionTimelockSeconds`) materially more likely in practice — needs a
     dedicated regression test, not just a restated theoretical risk.
- Also disclosed as accepted, not solved: this closes unilateral swap **execution**, not
  unilateral swap **denial** (signer can still park an unwanted proposal forever by never
  cancelling).

### 3.3 What's actually implemented in code right now

**`contracts/src/kernel/IntegrityAccountV1Experimental.sol` — DONE, fully landed.**
`git diff --stat`: +110/-3 lines. Adds:

- New errors: `ZeroGuardian`, `DuplicateGuardian`, `InvalidGuardianThreshold`, `NotAGuardian`,
  `GuardianNonceMismatch`, `GuardianAlreadyApproved`, `InsufficientGuardianApprovals`.
- Storage: `address[] private _guardians`, `mapping(address => bool) private _isGuardian`,
  `uint256 public immutable guardianThreshold`, `uint256 public kernelSwapNonce`,
  `mapping(uint256 => mapping(address => bool)) private _kernelSwapApprovals`,
  `mapping(uint256 => uint256) public kernelSwapApprovalCount`.
- Constructor signature changed: now `(address signerAddr, address kernel, uint256
  moduleActionTimelockSeconds_, address[] memory guardians_, uint256 guardianThreshold_)` — was
  3 args, now 5. Validates `threshold >= 1 && threshold <= guardians_.length`, rejects zero
  address and duplicate guardians.
- New `guardians()` view returning the immutable set.
- New `approveKernelSwap(uint256 expectedNonce, address newKernel)` — guardian-only, nonce- and
  target-checked, NOT routed through `execute()`/`withHook` (deliberate, per §3.2).
- `proposeKernelSwap` now bumps `kernelSwapNonce` before storing the pending swap.
- `executeKernelSwap` gained a fourth precondition: `kernelSwapApprovalCount[kernelSwapNonce] >=
  guardianThreshold`, checked after the existing three (pending exists, address match, timelock
  elapsed), before the existing `delete pendingKernelSwap` / uninstall / install sequence.
- Contract-level NatSpec doc comment updated with the guardian-quorum paragraph, stating both
  falsifications from §3.2 plainly (this satisfies part of item 1 from the advisor review, but
  **`docs/design/phase1-tracer-bullet-slice-2026-08-17.md` itself has NOT yet been amended** —
  see §6, remaining work).

**`contracts/test/IntegrityAccountV1Experimental.t.sol` — PARTIALLY landed, currently breaks the
build.** `git diff` shows only this much actually applied:

- `GUARDIAN_THRESHOLD` constant, `guardianSet`/`guardian1`/`guardian2`/`guardian3` state vars.
- `setUp()`'s guardian address generation (`makeAddr("guardian1")` etc.) and `guardianSet =
  [guardian1, guardian2, guardian3]` assignment.

**NOT yet landed** (the edit was in flight when the OPA outage started blocking all
Bash/Write/Edit calls, and never successfully applied):

- `setUp()`'s `account = new IntegrityAccountV1Experimental(...)` call still passes only 3
  arguments (line ~132) — needs `guardianSet, GUARDIAN_THRESHOLD` appended.
- The `test_constructorRevertsOnZeroTimelock` call site (line ~889, `new
  IntegrityAccountV1Experimental(signer, address(kernel), 0)`) still passes 3 arguments — needs
  the same two extra arguments appended (any valid guardian set/threshold; this test is about the
  timelock, not guardians, so it doesn't matter which valid values, as long as they pass
  constructor validation).
- No `_approveWithTwoGuardians(nonce, newKernel)` helper exists yet (was drafted, never applied —
  intended to `vm.prank(guardian1)` then `vm.prank(guardian2)` and call `approveKernelSwap` with
  each).
- **None** of the ~9 existing tests that call `executeKernelSwap` on a success path have been
  updated to gather guardian approval first — they will all fail `InsufficientGuardianApprovals`
  once the build compiles again. This is expected regression work, not a bug — see §7.
- **None** of the new guardian-quorum-specific tests from the proposal's "Scope: in" list have
  been written yet: below-threshold reverts, exact-threshold succeeds, double-approval same-nonce
  doesn't double-count, non-guardian approval reverts, wrong-nonce approval reverts, an approval
  from a cancelled proposal's nonce can't count toward a repropose of the same kernel, and —
  important, this is the one the advisor review specifically flagged as a new failure mode this
  slice introduces, not just restates — the quorum-vs-epoch-staleness sequence (assemble quorum
  after `epochLengthSeconds` has elapsed, confirm `SnapshotStale`, call permissionless
  `refreshReputationSnapshot()`, confirm success).
- No mutation-testing has been done on the new quorum guard (the established discipline in this
  codebase for every prior security-relevant guard — temporarily weaken it, confirm the suite
  actually catches the regression, restore it).
- No gas re-measurement of `proposeKernelSwap`/`approveKernelSwap`/`executeKernelSwap`.

**`PRODUCTION_GAPS.md`** — not yet updated with a §31 entry for this slice (every prior slice got
one; this one needs it before being called done).

**`docs/design/phase1-tracer-bullet-slice-2026-08-17.md`** — not yet amended with the
"hook mediates everything except X" disclosure the advisor review required (item 1). The account
contract's own NatSpec has this disclosure; the design doc does not yet.

## 4. The OPA/DNS outage and the fix found in the worktree

Mid-session, every Bash/Write/Edit tool call started being denied by the `pretool_gate.py`
PreToolUse hook (`~/.claude/xibalba/pretool_gate.py`) with `BCC_POLICY_ENGINE_UNAVAILABLE: OPA
request failed: [Errno -3] Temporary failure in name resolution`. This blocked all further work
on the test file mid-edit. Two retries several minutes apart both hit the identical error: this
session stopped retrying and reported it to the user rather than attempting any workaround (the
hook's fail-closed behavior on an unreachable policy engine is itself correct per this repo's own
"no silent mocks, fail closed" ground rule — see the conversation's own exchange on this, which
the user found amusing but valid).

**User reports the outage is now fixed.** Evidence of the actual fix, found already sitting in
the worktree (not yet re-verified independently by this session before compaction/restart):

```
git diff docker-compose.yml
```
```diff
-    command: ["run", "--server", "--addr=0.0.0.0:8181", "/policies", "/shield-policies"]
+    command: ["run", "--server", "--addr=0.0.0.0:8181", "/policies", "/shield-policies/selected.rego"]
     volumes:
       - ./bcc_middleware/policies:/policies:ro
-      - ../xibalba-shield/policies/rego:/shield-policies:ro
+      - ../xibalba-shield/policies/rego/smb.rego:/shield-policies/selected.rego:ro
```

Root cause this suggests: OPA's `run --server` was pointed at a whole directory
(`../xibalba-shield/policies/rego`) rather than a single selected policy file, which — per the
adjacent code comment already in the file (see the untouched context lines around this diff) —
can leave OPA's `result` key absent from its own data path, which its client code correctly
treats as OPA-unavailable/fail-closed. The fix pins the OPA server to one specific policy file
(`smb.rego`, loaded as `selected.rego`) instead of the whole directory. A backup of the
pre-fix file exists untracked at `docker-compose.yml.before-opa-policy-selection` — **preserve
it**, don't delete it, in case this fix needs to be compared against or reverted.

This fix has **not been proven working** by this session — the DNS error message ("Temporary
failure in name resolution") doesn't obviously match a "wrong OPA data path" root cause on its
face; it's plausible the docker-compose fix is real and unrelated, or that restarting the OPA
container as part of applying it is what actually cleared the DNS resolution symptom, or that
there's a second issue not yet surfaced. **Step 1 on resume is to verify, not assume** — see §7.

## 5. Complete list of changed/untracked paths to preserve

Tracked, modified:
- `contracts/src/kernel/IntegrityAccountV1Experimental.sol` — guardian-quorum implementation,
  complete (§3.3).
- `contracts/test/IntegrityAccountV1Experimental.t.sol` — partial edit, breaks the build until
  finished (§3.3, §6).
- `docker-compose.yml` — OPA policy-path fix (§4).

Untracked, must preserve:
- `docs/plans/2026-08-18-phase1-multiparty-kernel-governance-proposal.md` — the authorized
  proposal for the in-progress slice.
- `docker-compose.yml.before-opa-policy-selection` — pre-fix backup, keep until the fix is
  confirmed durable.
- `CLAUDE_HANDOFF_2026-08-17.md`, `CODEX_HANDOFF_2026-08-18.md` — prior session handoffs,
  untracked by convention, preserve per their own preservation instructions.
- This file, `CLAUDE_HANDOFF_2026-08-19.md`.

Nothing else in the worktree changed this session. `gas_usage.jsonl` and
`integrity-sdk/gas_usage.jsonl` telemetry noise from local test runs was deliberately discarded
(`git checkout --`) before the CI-fix push and is clean again as of this writing — if it shows
dirty again on resume, that's from re-running tests locally, safe to discard the same way unless
you specifically want to inspect the telemetry.

## 6. Exact current build failure

```
cd contracts && forge build
```

fails with exactly 2 errors, both pre-existing 3-argument constructor calls that need the two new
trailing arguments:

```
Error (6160): Wrong argument count for function call: 3 arguments given but expected 5.
   --> test/IntegrityAccountV1Experimental.t.sol:132:19:
    |
132 |         account = new IntegrityAccountV1Experimental(signer, address(kernel), MODULE_ACTION_TIMELOCK);

Error (6160): Wrong argument count for function call: 3 arguments given but expected 5.
   --> test/IntegrityAccountV1Experimental.t.sol:889:9:
    |
889 |         new IntegrityAccountV1Experimental(signer, address(kernel), 0);
```

## 7. Required next steps, in order

1. **Verify the OPA fix actually holds** before trusting it or doing anything else. From the
   `contracts` directory (or wherever is convenient), attempt a trivial Bash/Edit call. If it
   still fails with the same `BCC_POLICY_ENGINE_UNAVAILABLE` error, this handoff's §4 diagnosis
   was insufficient or incomplete — investigate the OPA container's actual running state
   (`docker compose ps`, `docker compose logs opa` if the stack is up) rather than assuming the
   docker-compose diff alone fixed it; the compose file change only takes effect once the `opa`
   service is actually restarted with it.
2. **Finish the two pending test-file edits** from §3.3: append `guardianSet, GUARDIAN_THRESHOLD`
   to both `new IntegrityAccountV1Experimental(...)` call sites. Add the
   `_approveWithTwoGuardians(uint256 nonce, address newKernel)` helper (prank as `guardian1` then
   `guardian2`, call `approveKernelSwap` with each) right after `setUp()`.
3. `forge build` — confirm it compiles clean.
4. `forge test --match-contract IntegrityAccountV1ExperimentalTest` — expect real regressions on
   every existing test that calls `executeKernelSwap` on a success path (~9 call sites per the
   earlier grep in this session: lines ~755, ~768, ~822, ~852, ~912→~933 area, ~965 in the
   pre-edit file — re-grep after the pending edit lands, line numbers will have shifted). Fix each
   by inserting a call to `_approveWithTwoGuardians(account.kernelSwapNonce(), <newKernel
   address>)` after the relevant `proposeKernelSwap` call and before `executeKernelSwap`. The
   tests that expect a revert for reasons unrelated to quorum (nothing pending, parameter
   mismatch, timelock not elapsed) should NOT need this, since those checks run before the quorum
   check in `executeKernelSwap` — verify this stays true rather than assuming it.
5. **Write the new guardian-quorum tests** enumerated in full in
   `docs/plans/2026-08-18-phase1-multiparty-kernel-governance-proposal.md`'s "Scope: in" section
   — do not skip the quorum-vs-epoch-staleness sequence test; it's the one the advisor review
   specifically flagged as a genuinely new failure mode, not a restated one.
6. **Mutation-test** the new `InsufficientGuardianApprovals` guard and the nonce-scoping guard
   (temporarily weaken each, confirm the relevant test actually fails differently, restore) —
   matching the standing discipline every prior security-relevant guard in this codebase got.
7. **Gas re-measurement** of `proposeKernelSwap`/`approveKernelSwap`/`executeKernelSwap`, recorded
   as a real number, not assumed unchanged.
8. **Amend `docs/design/phase1-tracer-bullet-slice-2026-08-17.md`** with the same "hook mediates
   everything except X" disclosure already in the contract's own NatSpec (§3.3) — the advisor
   review's item 1 is only half-closed until this doc matches.
9. **Add a `PRODUCTION_GAPS.md` §31 entry** for this slice, same register as §29/§30 — what
   shipped, what test count, what remains disclosed-not-solved (unilateral denial, the two
   pre-existing reentrancy windows, the broken-kernel brick scenario — none of which this slice
   touches).
10. Full repo suite (`forge test` with no filter) — confirm the count is `250 + <new tests> /
    <same total>, 0 failed`, not just the one contract's suite.
11. This is local, uncommitted, experimental, non-deployed code — do not commit, push, or deploy
    without separate explicit authorization, same standing rule as every prior Phase I slice.

## 8. Safety and claim boundaries

- No Base Sepolia mutation occurred this session.
- No external transaction was broadcast.
- No specification proposal was accepted or amended.
- PR #59 was merged into `integrity-core` `main` — the one exception to "nothing pushed," and it
  was explicitly user-authorized before merging (auto-mode gates PR merges; this session asked
  first, per its own standing instruction not to take actions with external side effects without
  confirmation).
- The Phase I guardian-quorum work is entirely local and uncommitted — safe to discard if the
  user wants to abandon this slice, but per §5, preserve it by default unless told otherwise.
- No credential value belongs in this handoff.
