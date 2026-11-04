# Claude handoff: ecosystem documentation consolidation

Date: 2026-11-03  
Workspace: `/home/xibalba/Projects`  
Managed worktrees: `/mnt/storage/xibalba/Projects/worktrees/<repo>/ecosystem-authority-20261103`

## Objective

Consolidate the Xibalba ecosystem architecture and documentation around one authoritative plan. The
target outcome is a simpler Integrity trust substrate plus two independently deployable,
monetizable SaaS products:

- Shield: customer-boundary enforcement and compliance evidence.
- Cortex: governed memory, content provenance, retention and retrieval evidence.
- Integrity: identity, signed packs, receipts, verification, anchoring and bounded on-chain trust.

Jev/DecisionTrace is optional annotation infrastructure. It must never become an enforcement,
identity, anchoring, availability or readiness dependency.

## Canonical documentation

The canonical plan is now:

`integrity-core/docs/ecosystem/INTEGRITY_ECOSYSTEM_PLAN.md`

The canonical domain documents beside it are:

- `ECOSYSTEM.md` — product boundaries and repository ownership.
- `DATA.md` — data boundary, telemetry, retention and evidence handling.
- `STATUS.md` — short list of open gaps only.
- `ADR-0001-six-function-test.md` — the six-function scope test.
- `DOCUMENTATION_MIGRATION.md` — what was consolidated, redirected or deliberately left historical.

The old `docs/EXECUTION_PLAN.md` is a compatibility redirect. Its historical full content was moved
to `docs/archive/2026-11/EXECUTION_PLAN-superseded.md`. Wiki and historical documents were not
blindly rewritten; they remain non-normative unless explicitly linked by the canonical documents.

Product repositories point to the core canonical plan from their local `docs/ecosystem/README.md`:

- `xibalba-cortex/docs/ecosystem/README.md`
- `xibalba-shield/docs/ecosystem/README.md`
- `integrity-console/docs/ecosystem/README.md`

## Completed commits and PRs

| Repository | PR | Branch head / relevant commit | State |
|---|---:|---|---|
| `integrity-core` | #183 | `1d5e70bf` merge commit; `32bf5140` documentation commit | Open; updated from `origin/main`; CI rerunning |
| `xibalba-cortex` | #89 | current head `b082999` (includes `698511d`) | Open; current-head workflow was manually dispatched |
| `xibalba-shield` | #66 | `b8b74ff` | Merged |
| `integrity-console` | #6 | `7fbd87d` | Merged |

Shield and Console were merged with their exact green CI-tested heads. Local branches were retained
because `--delete-branch` conflicts with the repository base worktree; branch retirement is a separate
`xb-wt finish` operation after verification.

## Core PR details

The original core PR conflicted with the upstream Jev-status plan in `docs/EXECUTION_PLAN.md`. The
intended resolution is to keep this branch's compatibility redirect and the new ecosystem authority,
while retaining upstream's non-conflicting tree changes. Because the managed mount rejected normal
unlink operations during `git merge`, the merge was constructed with Git's index plumbing as commit
`1d5e70bf` with parents:

- `32bf5140` — documentation consolidation.
- `1bcedbb5` — upstream `origin/main` at merge time.

Do not replace this with the old Jev-heavy execution plan. It is historical context, not the current
authority.

The documentation-contract check originally failed because `scripts/check_docs.py` still hard-coded
`docs/EXECUTION_PLAN.md` as the authority. That script is now patched locally to use
`docs/ecosystem/INTEGRITY_ECOSYSTEM_PLAN.md`, but the patch is not yet committed or pushed.

## Current local dirt to handle carefully

Core worktree currently reports:

```text
 M integrity-sdk/tests/unit/test_core_decision_trace.py
 M scripts/check_docs.py
```

The test file is a worktree/index mismatch caused by the managed mount refusing the normal checkout
step while constructing the merge tree. Inspect it before staging; do not accidentally overwrite or
commit unrelated test changes. The `scripts/check_docs.py` change is intentional and should be
committed after running it locally.

Cortex, Shield and Console worktrees are clean. The base checkouts remain read-only and must stay
clean; do not edit or install into them.

## Immediate next actions

1. In the core worktree, inspect the test-file diff and confirm it is only the upstream merge-tree
   difference. Run:

   ```bash
   git diff -- integrity-sdk/tests/unit/test_core_decision_trace.py
   python3 scripts/check_docs.py
   git diff --check
   ```

2. Commit only the intentional docs-contract fix:

   ```bash
   git add scripts/check_docs.py
   git commit -m "docs: update authority contract path"
   xb-wt push
   ```

   Do not stage the test file unless its contents are verified and intentionally part of the merge.

3. Wait for all required checks on core PR #183. The first updated run showed the documentation
   contract failure; other jobs were passing or still running.

4. Wait for the current Cortex workflow run `41743148451` on PR #89. The prior pull-request run was
   for an older head; the branch now includes commit `b082999`.

5. Merge only after the current head is green and the PR is clean:

   ```bash
   gh pr view <number> --json headRefOid,mergeable,mergeStateStatus
   gh pr merge <number> --squash --match-head-commit <head_sha>
   ```

   Omit `--delete-branch`; the local base worktree owns the base branch. Use `xb-wt finish` only after
   confirming the remote merge and only for these managed feature worktrees.

6. Run `xb-wt doctor` and `xb-wt list` after the merges. Preserve unrelated dirty or broken worktrees;
   they predate this task and are outside its scope.

## Constraints and decisions to preserve

- Do not rename `integrity-core` in this documentation-consolidation change.
- Four active repositories are in scope: core, Cortex, Shield and Console.
- No on-chain adapter registry, no on-chain policy compiler and no kernel rewrite.
- Third-party adapter preparation means deterministic, pure off-chain adapters plus a conformance
  kit; adapters cannot sign, anchor, permit, deny, change kernel authority or cross tenants.
- Shield and Cortex must work locally when chain, oracle, anchor or vendor services are unavailable.
- Customer content stays inside the declared boundary; evidence exports use metadata, HMAC-protected
  identifiers and roots/checkpoints rather than raw PHI.
- The plan's execution model uses `xb-wt` worktrees, no direct base edits, no `git stash`, and green
  CI plus `--match-head-commit` for merges.

## Known non-blocking warning

The core commit hook previously warned that
`/mnt/storage/xibalba/Projects/worktrees/integrity-sdk/.venv/bin/python` was missing. The commit still
succeeded. Treat this as a local hook/tooling warning, not evidence that the documentation change is
validated; rely on CI and `scripts/check_docs.py`.
