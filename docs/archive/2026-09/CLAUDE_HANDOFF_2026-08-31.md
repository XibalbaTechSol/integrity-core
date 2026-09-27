# Claude Handoff — Phase I/II/III completion audit, branch backlog cleanup, spec repairs

Generated: 2026-08-31T10:45:00Z
Repository: `/home/xibalba/Projects/integrity-core`
Worktree: in-place edits on the primary worktree, moving between `main` and short-lived feature
branches per change (see "Branches" below). Nothing uncommitted at session close — see `git
status` before assuming otherwise.

This was a long session starting from "audit Integrity Protocol and plan completing Phase 1/2/3
(skip external audits)." It surfaced three separate cases where shipped code and the current
normative docs (`docs/SPEC.md`, `docs/DOCUMENT_STATUS.yaml`) had silently diverged, closed two
real gaps (Phase III R1, R5), repaired the docs in both remaining cases, and did a full branch
backlog sweep across `integrity-core`, `xibalba-shield`, and `xibalba-cortex`. Six PRs merged
(#78–#83). One real technical blocker was found and left open, not worked around.

---

## 1. What actually shipped this session

### PR #78 — `audit/harness-loop-2026-07-30` sync (52 commits, first-ever push of that branch)
This branch had 52 commits that had never been pushed to GitHub. Pushed and merged. **Caught a
real bug along the way, not just CI noise:** `integrity-sdk`'s `PreflightResult.ok` folded
`oracle_reachable` into its aggregate — an unrelated liveness check that doesn't gate any real
on-chain revert — so a briefly-unreachable oracle reported a safe-to-register agent as unsafe.
Fixed in `integrity_sdk/registration.py`.

**Duplicate-merge incident, worth remembering for next time:** a *separate* PR (#77, "Audit/harness
loop 2026-07-30 follow-up") had already merged the same underlying branch content earlier the
same morning, via a different path. When #78 merged afterward, the 3-way merge found no conflict
against #77's already-present-but-unfixed code and **silently dropped the one-line
`oracle_reachable` fix**. Root-caused by checking `git show origin/main:<file>` directly rather
than trusting the PR's own green checkmark. Re-applied via PR #80. **Lesson:** after any merge
into a branch with a known-messy history (rebased/duplicated commits, multiple concurrent
sessions), verify the actual file content on `main` post-merge, don't trust CI-green alone.

### PR #79 — `docs/spec-open-definitions`
Retargeted from the archived, non-normative `spec/integrity-protocol-v0.4.md` (which the branch
originally edited) to current `docs/SPEC.md` §4.5. The design doc's other five gaps (verification
ladder, AIS versioning, governance authority, ZK-boost binding, quantities) still cite the old
v0.4 section numbers and were flagged inline as needing re-verification against `docs/SPEC.md`'s
restructured sections — not silently renumbered, since that's real editorial judgment outside
this session's standing.

### PR #80 — re-apply of the `oracle_reachable` fix
See #78 above. Confirmed genuinely present on `main` after merging (`git show origin/main:...`),
not just assumed from a green PR.

### PR #81 — `docs/dev-single-key-posture`
Restructured `docs/KEY_SPLIT_RUNBOOK.md` into "development posture (allowed)" vs. "mainnet
posture (required)" sections. The eight-key split was always scoped to mainnet launch readiness;
the doc's original wording read as applying to local/testnet work too.

### PR #82 — Phase III R1 (differential-replay admission suite) + R5 (corrected to Identity, closed)
**R1:** `AdapterRegistry.sol`'s own NatSpec named R1 (determinism) as needing an off-chain
differential-replay admission suite "this repo has never built." Built it:
`contracts/script/AdapterAdmissionSuite.s.sol` — snapshots state, calls
`AdapterRegistry.evaluate()` twice per vector, reverts between calls, compares results. Runnable
as a `forge script` CLI or via a reusable `runFor()` any Foundry test can call. 7 tests
(comparison-logic unit tests, a positive-control integration test against `SpendBudgetAdapter`
that also proves the snapshot/revert bookkeeping leaves zero residual state, a JSON-vectors
round-trip), plus a real anvil CLI run producing a real report.

**R5 — architecture correction, found mid-task, not assumed:** was about to build a
staking/audit-attestation mechanism per `AdapterRegistry.sol`'s own docstring and the
2026-08-25 design note. Both predate `docs/SPEC.md`'s spec cutover. Current normative source
(`docs/DOCUMENT_STATUS.yaml`) redefines R5 in §7.2 as **Identity** — "published with source,
machine-readable semantics, and a version hash the account pins" — no bonds, no attestation.
Built `AdapterRegistry.publishIdentity(adapter, metadataURI)` instead: permissionless, ties to
the SAME `specHash` already pinned immutably at registration (not a second parallel hash).
`isInstallable()` now returns real `true`/`false`. Repaired the stale docstrings in
`AdapterRegistry.sol` and `LicenceAccount.sol` in the same change (`docs/SPEC.md` §16 requires
this). Full suite 492/492 after both R1 and R5.

### PR #83 — `docs/SPEC.md` §5.2/§5.3 repair
Found while investigating whether `IntegrityKernel` could be wired into a real registered agent
(see §2 below): §5.2 claimed the kernel reference instance was **"non-deployed"** and **"MUST
NOT be referenced by deployment scripts"** — both false against this repo's own history
(`deployments.baseSepolia.json`'s `experimentalPhase1Reference`, `PRODUCTION_GAPS.md` §44,
`script/DeployKernelReference.s.sol`). Narrowed the prohibition to what was actually meant: not
wired to a real agent, not referenced by *production* tooling.

Also: four contract files (`IExecutionPolicy.sol`, `IAnchorPolicy.sol`, `SovereignAgent.sol`,
`StateAnchor.sol`) cited "SPEC.md §5.3" — a section that **never existed** in this document's
git history (checked via `git log -p --follow docs/SPEC.md`). Wrote the real §5.3, describing the
mechanism those files actually implement (`IExecutionPolicy`/`IAnchorPolicy`, live in
`SovereignAgent.execute()`/`StateAnchor.anchorRoot()`) — the four citations are now accurate
without needing their own edit.

---

## 2. The real blocker found, left open — not worked around

Original plan item: "wire kernel-gated execution into a real registered agent." Investigation
found the *actual* live mechanism isn't `IntegrityKernel` at all (that's explicitly walled off
from real deployment by §5.2, see above) — it's `SovereignAgent.setExecutionPolicy()` /
`StateAnchor.setAnchorPolicy()`, real and already in `main`'s source.

**But it cannot reach any currently-registered agent.** Verified directly on-chain (not
inferred): `cast call <address> "executionPolicy()(address)"` **reverts** against all three real
registered agents —

- `xibalba.integrity` — `0x360E2a56eb23e383B81E5bB42Ee5c3966688558a`
- `xibalba-health` (registered 2026-08-30, the day before this check) — `0x82F4cA2070c3a599d60310e3bD5752e1d4f33318`
- `xibalba-quant` — `0x753e2DA2cC10041D4A0deE6a8353E1C5C99eB867`

while a genuinely-supported call (`ais()`) succeeds against the same contracts — confirming this
is "feature absent from that deployment," not an RPC/ABI mismatch. Root cause: `SovereignAgent`/
`StateAnchor` are deployed **directly per agent, not behind a shared upgradeable proxy** — every
agent's copy is frozen at whatever bytecode existed the day it registered. The
`IExecutionPolicy`/`IAnchorPolicy` feature only became reachable on `main`'s real mainline
history via this session's own PR #77/#78 merges — after all three agents, including yesterday's
`xibalba-health`, were already registered. It genuinely never existed on `main` when any current
agent was created.

**`XibalbaAgentRegistry.registerPrimitives()` hard-reverts `AlreadyRegistered()` for a DID or
`sovereignAgent` address that's already registered** — confirmed by reading the contract
directly, not inferred from SDK behavior. There is no update/rotate path. Re-registering
`xibalba.integrity` cannot pick up new bytecode; the SDK's own idempotency check would just
return the existing (old) contracts as a no-op before even attempting it.

**Decision made, on purpose, not a fallback:** did not register a throwaway test DID to
"prove" the wiring works live — `contracts/test/PolicyHooks.t.sol` (7 real Foundry tests) already
does that without spending real gas or leaving an orphaned agent behind.

**Standing recommendation for future sessions:** this is the P0-6 upgradeability blocker
(`MAINNET_READINESS.md`) showing up in practice, and it will recur for every future
`SovereignAgent.sol` feature the same way it just did for `IExecutionPolicy`. Two separate
threads, not one:
1. **Going forward:** every *new* agent registration already gets `IExecutionPolicy`/
   `IAnchorPolicy` for free (current `main` has them). Lean into "swappable policy behind
   designed-in hooks" as the extension pattern for new features — `MAINNET_READINESS.md` itself
   named this as a real, under-explored third option alongside beacon-proxy and registry-rotation.
2. **Already-registered agents (`xibalba.integrity` included) are permanently frozen** short of
   the full beacon-proxy migration `MAINNET_READINESS.md` records as "decided, then reopened same
   day." That's a separately-scoped mainnet-readiness project, not a rider on any single feature
   task — don't attempt it opportunistically.

---

## 3. Branch backlog swept across all three product repos

Full survey + cleanup across `integrity-core`, `xibalba-shield`, `xibalba-cortex`. Before this
session: 17 branches in `integrity-core` alone (11 dead bot-generated `fix-ci-*`/`jules-*`
branches with zero unique commits each, three genuinely stale/absorbed feature branches, plus the
six real items above). After: every repo is down to just `main`, confirmed in sync
(`git rev-list --count main..origin/main` / reverse both `0` in all three).

**Two branches turned out to be fully absorbed duplicates, not real unreviewed work** — worth
remembering as a pattern, not a one-off: `integrity-core/feat/invocation-id-v1-sdk` and
`xibalba-cortex/feat/hybrid-extraction-retrieval-docs` both showed large "ahead" counts from
`git rev-list`, but a direct two-dot `git diff origin/<branch> origin/main` came back **empty** —
byte-identical trees. Their content had already landed via a different, duplicated merge path
(same root cause as the PR #77/#78 incident above). **Lesson, generalized:** a large
`git rev-list --count origin/main..origin/<branch>` number does not by itself mean real,
unreviewed work exists — always check the actual current two-dot content diff before spending
review effort on an old branch's history.

`integrity-core/feat/role-split-policy-hooks` was a middle case: its core interfaces had already
landed on `main` (further evolved), but its own test file (`PolicyHookInvariants.t.sol`, 11
tests) never made it — `main`'s renamed equivalent (`PolicyHooks.t.sol`) has only 7. Flagged as a
possible small residual test-coverage gap, not chased further this session — a real follow-up
item if someone wants it, not urgent.

---

## 4. What's genuinely still open

- The upgradeability blocker (§2 above) — no code fix attempted, by design.
- `feat/role-split-policy-hooks`'s possible 4-test coverage gap (`PolicyHookInvariants.t.sol` vs.
  `PolicyHooks.t.sol`) — never independently verified whether those 4 invariants are real gaps or
  redundant with what `PolicyHooks.t.sol` already covers differently.
- `docs/design/spec-open-definitions.md`'s gaps 2–6 (verification ladder, AIS versioning,
  governance authority, ZK-boost binding, quantities) still cite the archived v0.4 spec's section
  numbers, flagged but not retargeted to `docs/SPEC.md`'s current structure.
- The original Lane B items from the session's own audit plan (paymaster sponsored UserOperation
  demo, Phase II external-adoption evidence) were never started this session — Lane A was the
  full scope actually worked.

## 5. Working state note for whoever picks this up

Funder wallet (`0x7530bd7Cb142C50d5cC742EdF02263f368e89E2f`) is down to ~0.0048 ETH as of this
session's last check — verify current balance before any further on-chain writes.
