# Handoff — 2026-08-17k (Phase I reputation epoch-snapshotting — resolves the Table 4 gas finding for real, Devil's Advocate reviewed and code-fixed before landing)

Continuation after 2026-08-17j below. Direct continuation of the user's explicit next-scope
choice ("lets continue... reputation epoch-snapshotting") and the standing "validation loop for
every new feature" instruction — proposal doc first, strict TDD, mutation-test every
security-relevant guard, gas-measure rather than estimate, then a dedicated Devil's Advocate
review before landing, matching the exact pattern 2026-08-17j established for kernel-swap
governance.

## 0. What changed

`IntegrityKernelV1Experimental`'s `preCheck` no longer reads `effectiveScore`/`isZkBoosted` live
from `ReputationRegistry` on every call — the real, previously-disclosed cause of the Table 4
gas-budget overage (~40,129 gas, over the whitepaper's `<=40k` ceiling). It now reads a local
cache (`snapshotScore`/`snapshotIsZkBoosted`/`snapshotTakenAt`), refreshed by a new permissionless
`refreshReputationSnapshot()` function (anyone may call it — a keeper-bot pattern, not gated
behind the account's own signer), and fails closed with `SnapshotStale` if the cache is older
than an immutable `epochLengthSeconds`. **Measured, not estimated: `preCheck` now costs 33,321
gas — genuinely under the Table 4 budget**, confirmed live both before and after the review below.

Real design research happened before any Solidity: read `ReputationRegistry.sol` in full to
confirm `baseScore` has no monotonicity guarantee (a naive cache genuinely needs periodic
refresh) and to evaluate-then-reject an alternative (caching the raw `zkBoostExpiry` timestamp
instead of a boolean, which looked staleness-free at first but isn't, because `reportingPeriod`
is admin-mutable and could produce a real expiry earlier than a previously cached one). A second
alternative — auto-refreshing inline inside `preCheck` instead of failing closed — was also
considered and rejected (it wouldn't bring the worst-case call under budget, only the average),
though review later flagged that this specific claim was asserted rather than measured — see
below.

**The Devil's Advocate review's top-line verdict was "add code-level mitigations before treating
this as closed."** Three real gaps got fixed:

1. **The constants-match test verified nothing about the kernel.** `ZK_BOOST_BPS`/
   `BPS_DENOMINATOR` are duplicated locally on the kernel (for gas efficiency — one external call
   instead of two on refresh) but marked `private`, so the original test comparing them to the
   real registry's values never actually touched the kernel — it compared two hardcoded literals
   in the test file against each other. A future `ReputationRegistry` redeployment with different
   constants would have silently produced wrong cached scores forever. Fixed: the constructor now
   reads the real registry's constants once and reverts `BoostConstantsMismatch` on divergence.
2. **`epochLengthSeconds` had no upper bound** — a deployment could set an absurdly long epoch and
   truthfully claim "epoch-snapshotted reputation" while meaning "never re-checked." Fixed:
   capped at `MAX_EPOCH_LENGTH_SECONDS = 7 days`.
3. **Zero events anywhere** — the entire mechanism's safety story depends on someone (a keeper,
   the operator) noticing staleness and refreshing, but there was no on-chain signal to react to.
   Fixed: `ReputationSnapshotRefreshed` now emits on every refresh.

All three are mutation-tested. A genuine differential test
(`test_refreshedSnapshotMatchesALiveEffectiveScoreRead`) was also added, asserting the cached
value equals a live `effectiveScore()`/`isZkBoosted()` read — this is what actually would catch a
rounding/boundary/order-of-operations divergence between the kernel's reimplementation of the
boost math and the registry's own (review confirmed these are currently bit-for-bit identical by
reading both side by side, not assumed).

**Disclosed more precisely, not code-fixed — real tradeoffs, not oversights:**
- Within an epoch, reputation is not "possibly a little stale" — it is **completely unenforced**;
  only the budget check still bounds behavior during that window. This was true from the first
  design pass but under-stated before review.
- A compounding case the original tests missed: a boost expiring mid-epoch leaves BOTH the
  assurance-tier flag and the boosted (1.15x) score stale-permissive at once, not just one —
  now its own dedicated test rather than an inference from the score-staleness test.
- **A real, newly-surfaced interaction with 2026-08-17j's kernel-swap governance**: this test
  suite's own placeholder values already have `moduleActionTimelockSeconds` (3 days) exceed
  `epochLengthSeconds` (1 day). If the timelock outlives the epoch, a fully-vested swap's
  uninstall half can revert `SnapshotStale` for a reason unrelated to reputation, and a
  freshly-installed replacement kernel can be stale-on-arrival, rejecting the account's very
  first post-swap call. The test suite was already patched around this with explicit refresh
  calls, but review correctly flagged the original test comments as underselling it — this is now
  stated as an explicit, named **deployment invariant** (`epochLengthSeconds >=
  moduleActionTimelockSeconds`) in both contracts' NatSpec, not left implicit in test comments.
  Neither contract enforces this across the other; it's deploy-time discipline, not a code
  guarantee, and it's the one item from this piece that most needs picking up before any real
  deploy script gets written.
- The permissionless refresh's original "no manipulation surface" framing was slightly too
  strong: a caller can't manipulate WHAT gets cached, only WHEN real data gets pulled in — an
  adversary could force an early refresh locking in a real-but-temporary reputation dip sooner
  than an operator wanted. Stricter, not exploited, but worth naming precisely.

## 1. What this does NOT close, restated

The gas-budget finding is now genuinely closed (33,321 < 40,000, measured). Everything else from
2026-08-17j's list still applies unchanged: multi-party governance (still single-signer), the two
disclosed reentrancy windows, the no-recovery-path broken-kernel-brick class, no external audit,
not deployed. New open item from this piece: the `epochLengthSeconds`-vs-
`moduleActionTimelockSeconds` deployment invariant is real and currently unenforced by code.

## 2. State of the tree

`forge build` clean. `contracts/test/IntegrityAccountV1Experimental.t.sol`: 41/41 (up from 31).
Full repo suite: 250/250 (up from 240). Not yet committed as of this write-up; commit and push to
follow immediately after.

---

# Handoff — 2026-08-17j (Phase I module governance: timelocked kernel swap — reverses the "module mutation permanently disabled" claim, Devil's Advocate reviewed and code-fixed before landing)

Continuation after 2026-08-17i below. Different pattern from the three adapters: this change
**reverses** a previously committed claim (module mutation was "permanently disabled by
construction"; it no longer is), so it was written up as its own proposal doc
(`docs/plans/2026-08-17-phase1-module-governance-proposal.md`) alongside the implementation, and
— because this session's own operating loop calls for a focused review before landing a
foundational security/identity-boundary change — was run through a dedicated Devil's Advocate
review (independent subagent, full diff + OZ base source + test suite) before being finalized,
not after.

## 0. What changed

`IntegrityAccountV1Experimental` gained `proposeKernelSwap`/`executeKernelSwap`/
`cancelKernelSwap`: a timelocked, atomic mechanism to replace the installed kernel. Direct
`installModule`/`uninstallModule` still always revert — this is the only reachable path to
module mutation, and it is swap-only (not generic install/uninstall) by design: in a one-hook
account, bare uninstall with nothing queued to replace it is exactly the "the agent can simply
uninstall its own supervisor" failure the whitepaper names as fatal, so the swap atomically
uninstalls-then-installs in one transaction, never leaving a reachable zero-hook state.

**The review's top-line verdict was "add code-level mitigations before shipping,"** not ship-as-is
and not revert. Two real gaps got fixed in code:

1. **Zero timelock had no validation** — would have let `executeKernelSwap` succeed in the same
   transaction as `proposeKernelSwap`, silently voiding the mechanism's entire point. Fixed:
   constructor now reverts `ZeroTimelock()` on a zero value.
2. **No interface probe on the proposed kernel** — a non-conforming address only failed after the
   timelock had already elapsed. Fixed: `proposeKernelSwap` now probes
   `newKernel.isModuleType(MODULE_TYPE_HOOK)` and fails fast.

Both are mutation-tested (temporarily removed, confirmed the specific regression test fails for
the right reason, restored byte-identical via `diff`).

**One finding was disclosed rather than code-fixed, because it's genuinely unfixable at this
scope, not because it was overlooked:** the interface probe can't verify `preCheck`/`postCheck`
*correctness*. A kernel that passes the probe but reverts unconditionally in `preCheck` installs
cleanly, then permanently bricks the account — every future `execute()` reverts forever, and so
does every rescue-swap attempt (the rescue's own uninstall half must call the broken kernel's
`preCheck` first). This is genuinely worse than simply re-enabling `installModule` outright (a
bad kernel there fails instantly and visibly; here it can fail catastrophically later with no way
back). It's now a permanent regression fixture, not just prose:
`test_brokenKernelPreCheckPermanentlyBricksAccountWithNoRescuePath`. This also corrected an
earlier, incomplete disclosure — the original NatSpec framed the lockout risk as "requalify and
retry" (true for the separate reputation-floor case), which underclaimed how severe the
broken-kernel case actually is.

The review also sharpened, rather than changed, one existing claim: the swap is *asymmetrically*
mediated — removal of the old kernel is genuinely content-gated (reputation floor + assurance
tier, both real security checks), installation of the new kernel is gated only by the interface
probe and elapsed time. So this mechanism satisfies the whitepaper's condition (iii) for removal,
not for installation — the docs now say this explicitly rather than leaving a single uniform
"constrained" claim to be read either way. Two reentrancy windows (one per swap half, both from
`AccountERC7579Hooked` updating `_hook` storage before calling the module's own
`onInstall`/`onUninstall`) were named and disclosed, not closed — closing them would need
re-architecting the swap ordering, disproportionate for an experimental, non-deployed slice.

Single-signer governance and the reentrancy/mediation asymmetry were reviewed and found already
correctly bounded — no code change, but one test gap was closed
(`test_governanceFunctionsRevertForNonSelfNonEntryPointCaller`, since the access-control claim had
rested only on reading the inherited base class, not a regression test).

**One process note worth keeping:** the review also caught and helped verify a genuine Foundry
optimizer artifact (a second `vm.warp` call within one test function can silently fail to advance
`block.timestamp` under this repo's exact settings). The new brick-and-no-rescue test genuinely
needs two sequential timelocked actions; rather than assume the landmine applied, the test was
written to assert the *specific* custom-error selector expected only if time truly advanced both
times (not a generic revert, and not the timelock error) — it passes, confirming this exact usage
pattern is safe, and that's documented in the test itself rather than worked around blindly.

## 1. What this does NOT close, restated

Everything from 2026-08-17i's list still applies (gas-budget finding, no external audit, not
deployed). Additionally now open: multi-party governance (this remains single-signer), the two
disclosed reentrancy windows, and the no-recovery-path brick class for a hostile/broken kernel —
none of these are solved by this change, only the "permanently unreachable" state itself is
replaced with something reachable-but-still-constrained-on-one-side.

## 2. State of the tree

`forge build` clean. `contracts/test/IntegrityAccountV1Experimental.t.sol`: 31/31 (up from 17).
Full repo suite: 240/240 (up from 226). `forge fmt --check` flags pre-existing formatting drift
across several unrelated files repo-wide (`IntegrityGovernance.sol`, `Slasher.sol`,
`CCIPReputationBridge.sol`, `UltraPlonkVerifier.sol`) that predates this change and was not
introduced by it — not fixed here as out of scope for this slice. Not yet committed as of this
write-up; commit and push to follow immediately after.

---

# Handoff — 2026-08-17i (Phase I third adapter: assurance tier — completes the named trio, real gas-budget finding surfaced and documented, not hidden)

Continuation after 2026-08-17h below. Same authorization pattern: scoped proposal
(`docs/plans/2026-08-17-phase1-assurance-tier-adapter-proposal.md`) committed first, explicit
"authorize as scoped," then built. Mid-build, the user set a standing session goal — "implement
all kernel features and validate each one" — which is being treated as the authorization to
continue through the rest of Phase I's well-scoped pieces without a fresh go/no-go each time,
while keeping the same rigor (dependency checks, strict TDD, mutation testing, gas assertions,
honest documentation) that produced this finding in the first place.

## 0. What changed

`preCheck` gained a third conjunctive condition: `ReputationRegistry.isZkBoosted(boundAccount)`
must be true. No new external dependency — reuses the `reputationRegistry` immutable the
reputation-floor adapter already wired in. This completes the trio of reference adapters the
original Phase I plan named (spend/velocity cap, reputation floor, assurance tier).

**Two real bugs surfaced and fixed during this build, both genuinely instructive:**

1. **Test interaction bug, not a kernel bug.** Making the account ZK-boosted by default (for the
   new adapter's own tests) silently broke the existing below-floor reputation test: a raw
   `baseScore` of 499 boosted 1.15x becomes 573 — *above* the 500 floor — so the "below floor"
   test was actually exercising an above-floor call and wrongly passing. Fixed by choosing a base
   score low enough to stay below the floor even after boosting, with the boosted value computed
   from the contract's own constants rather than hand-rounded.
2. **Real gas-budget finding, not fixed away.** With all three checks live, `preCheck` measures
   ~40,129 gas — over the whitepaper's own Table 4 budget (`<=40k`), exactly the pressure point
   the Phase I plan had already named as a risk before this slice existed. Per this session's own
   stated commitment (written into the proposal *before* this was measured), the response was to
   document the finding honestly — the gas test was renamed
   (`test_preCheckGasExceedsPaperTable4BudgetWithThreeUncachedChecks`) and now asserts the cost
   is both genuinely over 40k and hasn't regressed further past a documented ceiling, rather than
   quietly raising the threshold to make a red test go green.

2 new tests (non-boosted reverts even when budget+reputation pass; an expired boost — a real
`block.timestamp` boundary — is treated as not-boosted), both mutation-tested same as every other
check in this kernel. Net effect on the suite: +2 (one redundant test removed along the way).
Full repo suite: 226/226.

## 1. What this does NOT close, restated

The gas-budget finding is a real, open item — not resolved by this slice, and not silently
absorbed either. The real fix (per-epoch score snapshotting instead of live cross-contract reads)
is exactly what the original plan already anticipated and is out of scope for a reference-adapter
slice. Everything else from the prior sections' "still true, restated" lists still applies:
not deployed, not audited, module governance/canonical intent encoding/BCC replay-gap unbuilt.

## 2. State of the tree

`forge build` clean, full suite 226/226. Committed and pushed to `audit/harness-loop-2026-07-30`.

---

# Handoff — 2026-08-17h (Phase I second adapter: reputation floor, authorized, built, tested)

Continuation after 2026-08-17g below (the first tracer-bullet slice, same day). Same
authorization pattern repeated: scoped proposal committed first
(`docs/plans/2026-08-17-phase1-reputation-adapter-proposal.md`), explicit user go/no-go
("authorize as scoped"), then built.

## 0. What changed

`IntegrityKernelV1Experimental` now enforces two conjunctive conditions instead of one: the
existing native-value budget, plus `ReputationRegistry.effectiveScore(boundAccount) >=
minEffectiveScore`, checked once in `preCheck` (a precondition gate, not a conserved quantity —
reputation can't change mid-call, so no `postCheck` involvement needed). This is the paper's
actual "adapters multiplex inside one hook" model, exercised for real — `AccountERC7579Hooked`
only ever supports one installed hook module, confirmed when the first slice was built.

Real `ReputationRegistry` used in tests, not a mock: its implementation constructor calls
`_disableInitializers()` (standard OZ upgradeable-safety pattern), so a bare `new` +
`.initialize()` reverts — deployed via `Clones.clone`, the same path `AgentPrimitivesFactory`
uses in production, confirmed by reading the contract before writing the test.

3 new tests, plus a mutation-test sanity check (same discipline as the first slice's `armed`
guard): removing the reputation check makes the below-floor test wrongly pass, confirmed and
reverted before landing. `preCheck`'s gas regression test caught a real cost increase from the
new cross-contract read (27,131 → 35,505) — still under the paper's 40k budget, but exactly the
kind of thing that test exists to catch. Full repo suite: 224/224 (up from 221).

Full detail: `PRODUCTION_GAPS.md` §29 (updated in place, same entry as the first slice — this is
explicitly an extension, not a new one), `docs/design/phase1-tracer-bullet-slice-2026-08-17.md`
(guarantee statement updated to state both conditions precisely).

## 1. Still true, restated

Not deployed anywhere. Not referenced by `Deploy.s.sol`. Not audited. Does not touch or resolve
the still-deferred AIS floor/shadow-gate decision (§27) — reads the existing
`effectiveScore`, independent of that unmade decision. Module governance, the third adapter
(assurance-tier), canonical intent encoding, and the BCC replay-gap fix all remain unbuilt and
unscoped — nothing here is a queued next step by default, same as the first slice's own note.

## 2. State of the tree

`forge build` clean, full suite 224/224. Committed and pushed to `audit/harness-loop-2026-07-30`.

---

# Handoff — 2026-08-17g (Phase I tracer-bullet slice: authorized, built, tested, not deployed)

Continuation after 2026-08-17f below. This is the first Phase I code to exist anywhere in this
repo — everything before this was architecture discovery, a Devil's Advocate review, and a plan.

## 0. What happened, in order

1. Reviewed Phase 0 (`IntegrityIdentityReadV1`) independently rather than trusting the prior
   session's summary — verified the controller-check logic against `SovereignAgent`'s actual
   role model, confirmed genuine `Deploy.s.sol` wiring, confirmed genuinely not yet on Base
   Sepolia. No issues found.
2. Reviewed Phase I's plan (`/home/xibalba/.claude/plans/where-are-we-with-dapper-gem.md`) and
   the Devil's Advocate findings (`CLAUDE_HANDOFF_2026-08-17.md` §9) — spot-verified the plan's
   three most load-bearing claims directly against code (`SovereignAgent.execute` is genuinely
   ungated; OZ's hooked-account plumbing genuinely exists at the claimed path; BCC's signed
   fields genuinely carry no `chain_id`/verifier binding). All three checked out.
3. Scoped the review's own recommended minimal slice into
   `docs/plans/2026-08-17-phase1-tracer-bullet-proposal.md` — explicit IN/OUT boundaries,
   acceptance criteria, real risks stated. Committed as documentation only, not authorization.
4. **User explicitly authorized the slice as scoped**, via a direct go/no-go decision, not a
   general "continue."
5. Built it, strict TDD throughout: real dependency inventory first
   (`docs/design/phase1-slice-dependency-inventory-2026-08-17.md`, written before any Solidity),
   then one failing test at a time. See §1 below for what exists.

## 1. What exists now

`contracts/src/kernel/IntegrityAccountV1Experimental.sol` +
`IntegrityKernelV1Experimental.sol`, `contracts/test/IntegrityAccountV1Experimental.t.sol` (12
tests), `docs/design/phase1-tracer-bullet-slice-2026-08-17.md` (the precise guarantee statement).
Full detail in `PRODUCTION_GAPS.md` §29 — don't duplicate it here, read that entry for the
verification table and what's explicitly NOT proven.

**Load-bearing, not decorative — verified by mutation testing, not just written:** the kernel's
`armed` reentrancy guard was proven to do real work by temporarily removing it and confirming the
reentrancy test fails *differently* (a different revert reason, revealing real state corruption
from the missing guard) rather than just failing generically. This is the standard this session
tries to hold every claimed protection to.

## 2. What this is NOT, stated again because it matters

Not deployed anywhere. Not referenced by `Deploy.s.sol`. Not the full Phase I plan — module
governance, reference adapters, canonical intent encoding, and the BCC replay-gap fix are all
still unbuilt. Not audited — this slice does not clear the Devil's Advocate review's own gate to
Phase II. Completing this slice is explicitly not grounds to deploy it or to claim "the kernel is
built" — see the proposal doc's own risk section and the design note's "what this does NOT
prove" list.

## 3. State of the tree

`forge build` clean, full suite 221/221 (up from 209). Committed and pushed to
`audit/harness-loop-2026-07-30`.

## 4. Next, if this is ever picked back up

Nothing here is a queued next step by default — this was a scoped, bounded authorization, not an
open door to the rest of Phase I. If continuing: the proposal doc's explicit OUT-of-scope list is
the menu, and each item there would need its own review/authorization cycle the same way this
slice did, not an assumption that authorizing the slice authorized the rest of the plan.

---

# Handoff — 2026-08-17f (Shield registration retry: real second root cause found, fixed, verified)

With explicit user authorization for real Base Sepolia transactions, re-ran
`xibalba-shield/scripts/register_with_oracle.py`. **Corrects 2026-08-17e §2 item 4 below,
which said this was still open pending go-ahead — it's now genuinely done, not just
attempted.**

## 0. What actually happened

The run deployed a real `SovereignAgent` (`0x0C24806C751A04B785F1aF3A9E915FE4d4313A77`) and
`StateAnchor` (`0x4131ccebaA186A95B51f7017f99fF8E55c87B358`), got through genesis-root
anchoring, then failed at the final `registerPrimitives` step with
`AccessControlUnauthorizedAccount(0xC19fc9cB..., REGISTRAR_ROLE)` — the same error
`PRODUCTION_GAPS.md`'s existing registration entry (item 4) had already seen and attributed
to RPC staleness. **That attribution was wrong.** `AgentPrimitivesFactory.registerPrimitives`
needs `REGISTRAR_ROLE` on two registries, not one — its own NatSpec says so
("Holds `REGISTRAR_ROLE` on both registries") — and only `XibalbaAgentRegistry`'s grant had
been fixed on 2026-08-14. `DomainRegistry.recordJoin` (`onlyRole(REGISTRAR_ROLE)`) never got
the same fix. Confirmed live via `hasRole` returning `false` on the canonical
`sepolia.base.org` endpoint — the same endpoint item 4 already trusted, ruling out staleness
as this call's explanation.

**Fix**: granted `REGISTRAR_ROLE` to the factory on `DomainRegistry` from the funder/
governance wallet (tx `0xd40ac7e2586b3aca21d2d36c015385b07650202c3efe61e5b9d962e2b2ccb979`),
verified `true` afterward. Then — deliberately not re-running the non-idempotent script from
scratch, which would have deployed a *fifth* orphaned pair on top of the four already
documented — resumed registration from the already-deployed `SovereignAgent`/`StateAnchor`
via a one-off script calling `integrity_sdk.chain.register_primitives` directly with those
existing addresses. `registerPrimitives` succeeded for real. The one remaining failure (the
final oracle-registration POST hitting `http://localhost:8080` from inside the container,
which doesn't resolve there) was a pure networking misconfiguration in that resume script,
fixed by passing the compose-internal `http://oracle-backend:8080` and re-running — which
correctly took the script's existing "already registered on-chain, just re-POST idempotently"
branch rather than touching the chain again.

**Verified end-to-end against the real running stack, not assumed:** `resolveDID` returns
the full real 7-primitive set; `GET /v1/agent/{id}` shows `oracle_registered: true`; the DID
no longer appears in `GET /v1/shield/unregistered-agents`. Full detail:
`PRODUCTION_GAPS.md`'s registration entry item 7, `docs/demo-shield-integration.md`'s
2026-08-17 update.

## 1. What this does and doesn't mean

- Milestone 2 of the Shield demo is done for Shield's specific DID. No new orphan was
  created — the four pre-existing orphaned `SovereignAgent`/`StateAnchor` pairs from
  2026-08-14 are untouched, still no cleanup path.
- **Does NOT mean registration is now robust for a new agent.** The script's core
  non-idempotency bug (a partial failure isn't resumable automatically, only manually as
  done here) is unfixed. A future agent's first registration attempt could still orphan a
  pair if it fails partway for an unrelated reason.
- **Does NOT mean `DomainRegistry`'s role setup is done.** It's fixed enough to work today,
  on the same stopgap factory with the old shared-key roles `docs/signer-role-rotation-2026-08.md`
  already flagged for `XibalbaAgentRegistry`. Same caveat now applies to both registries.

## 2. State of the tree

Committed and pushed to `audit/harness-loop-2026-07-30`: `PRODUCTION_GAPS.md`,
`docs/demo-shield-integration.md`, this file. The on-chain transactions themselves are, of
course, already final and irreversible — nothing to commit there, just to document.

---

# Handoff — 2026-08-17e (AIS shadow mode landed; MCP gap found; Cortex Merkle item closed as reviewed-and-documented)

Continuation after 2026-08-17d below (Phase 0 + doc reconciliation, committed as `bd233e1`).
Everything in this section is committed and pushed to `audit/harness-loop-2026-07-30` (and,
for the `xibalba-cortex` item, that repo's `feat/hybrid-extraction-retrieval-docs`) — nothing
here is a working-tree-only claim.

## 0. What landed

- **MCP identity-resolution gap found and documented** (`b80522f`) — `integrity_resolve_did`
  only reaches `GET /v1/agent/{id}`, which has no `ais` field. An external MCP client can
  resolve identity but not reputation today. Fix sketch recorded in
  `docs/plans/2026-08-17-ecosystem-adoption-strategy.md` §5 item 3, not implemented (wasn't
  asked for).
- **AIS dry-run against the live agent set** (`1e5b44d`, `PRODUCTION_GAPS.md` §27 addendum) —
  only one agent is registered (`xibalba.integrity` itself). Its real breakdown: entropy
  268.45, grounding 950.17, sacrifice 861.34, compliance 1000.0 (of 1000); reported `ais:600`
  is the verification-tier-1 ceiling, not the raw ~645 geometric mean. Recorded as the one real
  number a future entropy-floor decision needs to be checked against.
- **spec §3.1.4 rows 5–6 landed** (`afab497`) — row 6 for real: `AisBreakdown.constraint_score`
  (eq. 4b's `r(ι)`, pre-boost, tier-ceilinged, clamped `[0,1]`), now the correct field for any
  future reputation-parameterised constraint to read instead of `ais`. Row 5 in **shadow
  mode**, an explicit user decision after the dry-run above showed N=1 isn't enough to
  responsibly pick permanent floor values: `AisFloors` (provisional defaults — compliance 400
  is the spec's own worked example, entropy/grounding chosen to sit below the one real agent's
  telemetry) plus `gate_entropy_pass`/`gate_grounding_pass`/`gate_compliance_pass`/
  `gate_would_pass` on `AisBreakdown`, purely observational — never zeroes `ais` or
  `constraint_score`, not wired into `bcc_middleware`'s chain-push or dispute logic. Verified
  live against the real running oracle (rebuilt + restarted the container, not just unit
  tests): the real dogfooding agent returns `constraint_score:0.6`,
  `shadow_gate.would_pass:true`.
- **Floor-value + enforcement decision: explicitly deferred** (`277fe11`) — user's own call,
  not a default. Revisit once a second real agent registers, or the decision is explicitly
  revisited regardless of count.
- **Cortex Merkle malleability item (§5.2 below, and the 2026-08-17c/d sections' own
  references): reviewed, closed as reviewed-and-documented, not patched.** The exploitable
  half (leaf domain-separation + position commitment for `session_merkle_evidence`) was already
  fixed before this section, in `xibalba-cortex`'s `32b1b1c`. The remaining residual
  (`merkle_parent`'s internal-node combination has no domain/level tag; odd-width nodes are
  promoted unchanged — the CVE-2012-2459 *shape*) got a real adversarial review before any
  further code was touched, using a fresh independent agent with no prior exposure to this
  session's own reasoning (the paid Devil's Advocate MCP tool was tried first and is not
  entitled/subscribed in this environment). Verdict: **not practically exploitable today**
  (every leaf is forced through `domain_leaf`'s own tag before entering the tree — no free
  collision the way Bitcoin's original bug allowed); the specific proposed fix was itself
  flawed (claimed level-separation it didn't actually deliver); and the alternative
  (leaf-count-in-root) would force a breaking wire-format bump plus migration of two OTHER
  domains' persisted roots (`projection_checkpoint`, `retrieval_trace`) that the original
  framing of this item never anticipated. Documented in `xibalba-cortex`'s
  `spec/xibalba-cortex-v1.md`, wiki concept page, and `WIKI_LOG.md` (commit `ddf46cf`) rather
  than patched. **Do not re-open this as "still open, needs a fix"** — it was reviewed and the
  considered decision was to document, not patch; only reopen if a version bump of this
  construction happens anyway for unrelated reasons, in which case do it as a deliberate
  versioned profile with an explicit migration plan, not an in-place patch.

## 1. State of the tree

Both repos clean relative to their remote — everything above is pushed, not working-tree-only.
`integrity-core`'s `CLAUDE_HANDOFF_2026-08-17.md` remains untracked at repo root (preserved,
per the 2026-08-17c/d sections' own instruction) and is now stale relative to this section on
the Phase 0/documentation status front — read this section and 2026-08-17d together, not that
file alone, for current status.

## 2. Next, adjusted again

1. ~~MCP AIS-resolution gap~~ **found and documented, not fixed — this section.**
2. ~~AIS dry-run / floor values~~ **dry-run done, floors deliberately deferred — this section.**
3. ~~Cortex Merkle malleability~~ **reviewed and documented as deliberately unfixed — this
   section. Do not re-open without a real reason to revisit.**
4. Registration retry — still open, still a real chain write (real testnet gas, real on-chain
   state), still pending explicit go-ahead.
5. Phase I — still needs a new, explicit authorization distinct from routine "continue"/
   "proceed" instructions, per its own Devil's Advocate review (2026-08-17d §9). Not resumed.
6. Base Sepolia facade deployment, ERC-8004 clause-by-clause acceptance — both still open,
   both real external actions requiring separate approval.

---

# Handoff — 2026-08-17d (Phase 0 and v3.2 documentation reconciliation complete locally)

This section supersedes the current-status and document-authority claims in older same-day
sections below. Historical evidence remains preserved.

## 0. Closure outcome

All Phase 0 tasks and the added Whitepaper v3.2/new-specification documentation criterion are
**complete locally**. No external deployment, specification acceptance, public release, or Base
Sepolia mutation occurred.

The document authority chain is now explicit and consistent:

1. `spec/integrity-protocol-v0.4.md` remains the accepted normative specification.
2. `spec/integrity-protocol-v0.5-proposed.md` is the new non-authoritative amendment under
   clause-level review. It now maps the full substantive v3.2 proposal set, including identity,
   AIS evidence/floors, memory, complete mediation, telemetry-prover decentralization,
   availability escrow, grace modes, high-frequency channels/compiler trust, and the hybrid
   attested-host boundary.
3. `spec/integrity-protocol-v3.2.md` is explanatory and non-normative. All change labels say
   `PROPOSED NORMATIVE CHANGE`; no whitepaper text silently amends v0.4.
4. `spec/Integrity_Protocol_Whitepaper_v3.2.pdf` is generated publication output.

Phase 0's `IntegrityIdentityReadV1` remains a custom, read-only, explicitly non-ERC-8004 profile.
It is locally tested, wired into future-genesis deployment output, and preserved by every
incremental deployment-file reserializer. It was not broadcast to Base Sepolia. Agent Integrity
Score (AIS) remains the sole reputation authority.

## 1. Documentation reconciliation

Updated living authority/status surfaces include `README.md`, `SPECIFICATION.md`,
`IMPLEMENTATION_PLAN.md`, `CLAUDE.md`, `.agents/AGENTS.md`, `spec/README.md`, v0.4's
implementation clarification, the complete v0.5 proposal, Whitepaper v3.2,
`docs/INTERFACE_CONTRACT.md`, `docs/MAINNET_READINESS.md`, `docs/TESTING.md`,
`docs/CONTRIBUTOR_VALIDATION.md`, package READMEs, `PRODUCTION_GAPS.md`, active plans, and the
canonical wiki/index/backlinks/log. Historical v3.1 releases and archived plans/log entries were
not rewritten.

The v0.5 proposal and interface/gap ledgers preserve honest status: Phase 0 identity discovery
and bounded AIS fail-closed defaults are implementation evidence; the execution firewall,
federated telemetry prover, availability escrow, grace modes, high-frequency channel/compiler,
and attested-host profiles remain `[PLANNED]` or `[PARTIAL]`, not deployed behavior.

A delayed independent adversarial review initially failed this closure on residual whitepaper
authority wording, two section references, and five load-bearing mapping omissions. The final source
now marks complete mediation as proposed, uses only proposed-normative language, corrects §10.3/§10.4
references, and carries verified-evidence monotonicity, exposure-scaled availability escrow with
anti-grief deposit and deterministic redress/burn, hard value partition plus typed degradation
events, budgeted state-channel conservation/unilateral settlement, and per-transaction enclave
binding with residual TEE risk into v0.5-proposed. These remain proposals, not v0.4 requirements.

## 2. Publication evidence

- Added reproducible builder `scripts/build_whitepaper_v32.py`.
- Build inputs: pinned Mermaid 11.16.1 and KaTeX 0.16.47 assets in the user cache.
- Build result: all 13 Mermaid diagrams rendered; 59-page A4, unencrypted PDF.
- Extracted-text checks retained the v3.2 title, non-normative notice, v0.5-proposed link,
  custom identity/non-conformance boundary, and proposed-change markers; no stale `SPEC CHANGE`
  marker remained.
- Cover and technical page 16 were visually inspected before the final text reconciliation;
  representative final pages 3, 18, 24, 38, and 56 were then re-rendered and inspected with no
  clipping, overlap, browser header, broken glyph, or raw-markup defect. Page 24 is underfilled
  because the following structured block is kept together, not because content was truncated.
- PDF SHA-256 after the final internal-authority/identity reconciliation:
  `d7d3135007f118f174be3a5bcde247198a8fb6f5dbf821c2825fca8508c63552`.

## 3. Final verification evidence

- Scoped `forge fmt --check`: passed for the facade, test, genesis script, and all touched
  incremental deployment scripts.
- `forge build`: passed; only pre-existing lint warnings were reported.
- Full Foundry suite: **209 passed / 0 failed / 0 skipped** across 23 suites.
- Living Markdown link audit: **108 files, 544 local links, 0 missing**. Append-only wiki logs,
  schema-template examples, dated audits, and archived plans were intentionally excluded from
  current-link assertions while remaining preserved.
- Wiki table-of-contents check: current for 36 pages.
- Wiki linter: 36 total pages, 25 concepts, 8 entities, 0 orphans, and 0 dead catalog links. The
  linter now correctly treats canonical `index.md` as a landing page rather than a counted article.
- Dashboard validation contract: `npm run build && npm run lint` passed with 0 errors (56 existing
  warnings). `Makefile` and hosted CI now use that real validation surface; Playwright remains a
  separately prepared browser layer because no dashboard unit/component test script exists.
- Authority/claim assertions: passed for v0.4 authority, v0.5 proposal status, v3.2
  non-normativity, complete v3.2 clause mapping, Phase 0 negative ERC-8004 conformance, interface
  planned-state rows, and production-gap coverage.
- `git diff --check`: passed.
- No external transaction or deployment was performed.

## 4. Remaining work is post-Phase-0

The following are explicit future work, not blockers to Phase 0 closure: accepting or rejecting
v0.5 clause by clause; native ERC-8004 convergence; approval-gated incremental Base Sepolia
facade deployment; underlying registry invariant prevention; and implementation of Phase I plus
the other planned v3.2 profiles.

---

# Handoff — 2026-08-17c (Phase 0 identity discovery closed locally; no external deployment)

This section supersedes only the Phase 0 identity/adoption claims in the older same-day
sections below. Historical test evidence and unresolved Phase I work remain intact.

## 0. Outcome

Phase 0 is **complete locally**. `contracts/src/kernel/IntegrityIdentityReadV1.sol` is a
read-only, versioned discovery facade over `XibalbaAgentRegistry`; it is not an ERC-8004
Identity Registry or ERC-721 implementation. It resolves by DID, DID hash, and
`SovereignAgent`, returns fixed registry/primitives state, validates forward/reverse and
declared-DID consistency, and checks candidate controllers against the account's live role
state. The optional, mutable `profileURI` is a separate read, so a broken profile contract
cannot deny fixed identity resolution.

Primary-source review pinned the ERC-8004 Draft at
`ethereum/ERCs@503591a6e80e6e1affdd6403341e25269141f046/ERCS/erc-8004.md` and rejected the
earlier "ERC-8004-shaped" compatibility claim. The facade explicitly returns
`isERC8004Conformant() == false` and defines no token identifier, ownership, transfer,
approval, wallet-proof, metadata-write, reputation-feedback, validation, event, or ERC-165
surface. Agent Integrity Score (AIS) remains the sole reputation authority through the
existing Integrity Oracle and per-agent `ReputationRegistry`.

Existing agents require no migration and no Base Sepolia transaction was broadcast.
`Deploy.s.sol` now includes the facade for future genesis deployments as
`singletons.IntegrityIdentityReadV1`; an incremental testnet deployment remains a distinct,
approval-gated external write.

## 1. Verification evidence

- Focused Foundry suite: **10 passed / 0 failed / 0 skipped**.
- Full Foundry suite: **209 passed / 0 failed / 0 skipped** across 23 suites.
- `forge build`: compiler run successful; only pre-existing lint warnings were emitted.
- Scoped `forge fmt --check` for the facade, tests, and deployment script: passed.
- `git diff --check`: passed.
- Future-genesis dry simulation: passed; `deployments.local.json` contained a valid
  `singletons.IntegrityIdentityReadV1` address and the deployment log named the facade.
- Wiki checks: 36-page table of contents current; zero index orphans; zero dead index links.
- Static secret-pattern scan over the Phase 0 Solidity/deployment diff: no hits.

## 2. Reconciled artifacts

- `README.md`
- `docs/INTERFACE_CONTRACT.md` §6.1a and deployment schema
- `spec/integrity-protocol-v0.5-proposed.md` (still proposed/non-authoritative)
- `spec/integrity-protocol-v3.2.md` (explanatory source correction)
- `PRODUCTION_GAPS.md` §28
- `docs/wiki/entities/contracts.md` and append-only `docs/wiki/WIKI_LOG.md`
- `/home/xibalba/.claude/plans/where-are-we-with-dapper-gem.md`
- `docs/plans/2026-08-17-ecosystem-adoption-strategy.md`

Historical v3.1 release artifacts were deliberately not rewritten. The v3.2 correction
records that direct review found deployed Validation proxy bytecode while canonical project
material still labels that component unstable.

## 3. Open items are post-Phase-0

1. Prevent duplicate-agent and registered/declared-DID mismatches in the registry/factory
   write path; the facade currently detects and rejects them.
2. Deploy `IntegrityIdentityReadV1` incrementally to Base Sepolia only after exact approval,
   then verify bytecode and reads directly.
3. Revisit native ERC-8004 convergence only on a real integrator, stable Validation, or
   cross-chain portability trigger, with a selector-by-selector compatibility review.
4. Begin Phase I kernel work only under its independent-audit and machine-checked-invariance
   gate. The kernel must read fixed registry/primitive state directly, not this external
   discovery facade or dynamic profile metadata.

## 4. Tree state

Work is intentionally uncommitted on branch `audit/harness-loop-2026-07-30`. The
pre-existing untracked ecosystem-adoption draft was preserved and minimally reconciled;
unrelated files were not deleted or staged.

---

# Handoff — 2026-08-17b (AIS fail-closed defaults landed; v0.5-proposed evidence trail; open-item triage)

Continuation of the same-day session below, picking up its own priority-ordered open-items
list (§3). Landed on top of the already-committed `3372db5`; nothing here has been committed
yet — see "State of the tree" at the end of this section.

## 0. What actually changed

**Landed HANDOFF §3 item 1 — `derive.rs` fail-open defaults, items 1–2 of spec
§3.1.4's implementation-delta table.** `derive_entropy`, `derive_grounding`
(`integrity-oracle/backend/src/derive.rs`) and `self_reported_compliance` (same file) now
return `0.0` on an empty batch instead of `1.0`. Mirrored in
`integrity_sdk/telemetry/derive.py`'s `derive_entropy`, `derive_grounding`, and the
self-reported half of `derive_compliance` — these were not previously in lockstep with the
Rust side's fix scope; both now are. This is the fix the earlier section's §0 called "the
highest-value open item."

**Why this alone closes the numerically-verified attack, without needing the floor/gate
(item 5, still open):** `scoring-core::score` is a weighted *geometric* mean, and
`scoring-core`'s own `any_single_zero_component_annihilates_ais` test already establishes
that any exact-zero component annihilates the product. Entropy and grounding now derive to
exactly `0.0` on content-free input (not a small positive number), so the attack scenario
from the earlier section's §0 (content-free submission, claimed GPU-hours, r = 0.923) now
independently gates to `r = 0.000` through the existing mean, with no new gate code
required. The honest-agent case (real telemetry on all four axes, r = 0.465) is untouched
— its axes are non-empty, so the changed branch never fires. Verified as a direct regression
test, not just reasoned about:
`derive::tests::content_free_submission_with_token_counts_fails_closed_on_entropy_and_grounding`
(Rust) and the Python sibling of the same name in `test_derive.py`.

**Deliberately NOT landed — items 3–6 of the same table (compliance/sacrifice attestation,
floors + Θ gate, pre-boost clamp).** These change AIS's *output value* for every currently
registered agent, and this repo pushes AIS to chain automatically
(`bcc_middleware/app/scoring_loop.py`, default `SCORE_SYNC_INTERVAL_SECONDS=300`) and can
fire a real `Slasher.raiseDispute` off the resulting flagged ratio, locking
`DISPUTE_STAKE_BPS` (default 10%) of an agent's stake. Landing those needs a dry-run score
table against the live agent set *first* — advised against and not attempted this session.
See §2 below.

## 1. What was verified

| Suite | Result |
|---|---|
| `cargo test --workspace --lib` (`integrity-oracle`) | **137 passed** (126 backend + 11 scoring-core), 0 failed — verified directly this session; not compared against the prior session's recorded 130, since `CLAUDE.md` itself warns per-package test counts drift across docs and aren't auto-updated |
| `uv run pytest tests/` (`integrity-sdk`) | **262 passed / 3 skipped**, up from the prior session's recorded 259 passed/3 skipped — 1 existing test renamed in place (`test_derive_entropy_empty_batch_is_max` → `..._fails_closed_to_zero`, assertion flipped, no count change) plus 3 new tests added |

No e2e run (`ORACLE_E2E=1 cargo test --test e2e`) this session — the change is in a pure
function exercised directly by unit tests; the e2e suite needs a live Postgres/Redis it
wasn't worth standing up for a 6-line fix already covered at the unit level. If the exact
ingest-path wiring (`handlers::ingest_telemetry` → `derive::recompute`) is ever suspected of
drifting from these pure functions, that's the suite to re-run — see the earlier section's
own note that `--lib` doesn't exercise the ingest path.

## 2. Devil's-Advocate gate on items 3–6 — explicitly not run, explicitly required before landing

Per the operating profile's own carve-out (foundational security/identity-boundary changes
warrant a red-team pass; routine work doesn't), items 5–6 cross that line because they
change every registered agent's on-chain score and can trigger slashing. **Before landing
them:** pull the live agent set from `XibalbaAgentRegistry`, recompute AIS under the
proposed floors+gate for each using its actual recent telemetry, and diff against today's
pushed scores — specifically flag any agent that would newly fall below a
`DISPUTE_FLAGGED_RATIO_THRESHOLD` or lose PHI-gate access it currently has under
`EHRGate`/`ComplianceGate`. Only after that table exists should a Devil's-Advocate pass run
against the floor *values* chosen (§3.1.1's Table 1a leaves `S_E^floor`, `S_G^floor`,
`S_C^floor` as symbols, not numbers — picking the actual thresholds is itself a decision
this session did not make).

## 3. Other continuation work this session

- **Documentation kept in lockstep, not left to drift:** `CLAUDE.md`'s AIS-scoring section
  now states which axes fail closed as of this fix and lists rows 3–6 as explicitly still
  open (it previously said nothing about the empty-batch defaults at all).
  `PRODUCTION_GAPS.md` gained `§27` recording the vulnerability, the fix, and what's still
  open — appended, not merged into any existing entry (no prior entry named this
  specifically). `spec/integrity-protocol-v0.5-proposed.md` §4.1 gained a clause →
  code-path → test-name evidence table for the two landed requirements, explicitly scoped
  to *not* claim clause 4.2 (the gate) is implemented — the document's `[PARTIAL]` status
  line for this section is unchanged, correctly, since the gate itself still doesn't exist.
- **Did not touch:** `ais-equations.html` — checked, and it presents the formula *shape*
  (weights, geometric mean, ZK boost), which did not change; only empty-input *behavior*
  did, which isn't represented there. Re-check this call if items 5–6 land — a floor/gate
  is a shape change the page's own sync rule would then require.
- **Did not touch:** `integrity-cli` — confirmed by grep it holds no independent copy of
  `derive_entropy`/`derive_grounding`/`self_reported_compliance` logic (per `CLAUDE.md`,
  the CLI reimplements identity/wallet/chain/BCC, not AIS derivation), so there is nothing
  there to bring into lockstep.

## 4. State of the tree

Working-tree changes only, not committed: `integrity-oracle/backend/src/derive.rs`,
`integrity-sdk/integrity_sdk/telemetry/derive.py`,
`integrity-sdk/tests/unit/test_derive.py`, `CLAUDE.md`, `PRODUCTION_GAPS.md`,
`spec/integrity-protocol-v0.5-proposed.md`, this file. Run `git status`/`git diff` before
trusting this list — it was accurate at time of writing, not re-verified after.

## 5. Next, in the earlier section's own priority order, adjusted

1. ~~`derive.rs` items 1–2~~ **DONE — this section.**
2. Cortex Merkle malleability — still open, still a separate bounded lane in
   `xibalba-cortex`, not touched here.
3. Registration retry — still open; unrelated to this session's AIS work.
4. Doc alignment — partially advanced (CLAUDE.md, PRODUCTION_GAPS.md,
   v0.5-proposed.md above); `docs/INTERFACE_CONTRACT.md` not yet touched.
5. Signer-role rotation — still blocked on operator input, unrelated to this session.
6. Orphaned testnet contracts — still open, unrelated to this session.
7. **New, added by this session:** items 3–6 of §3.1.4, gated on the dry-run + review in §2
   above — do not land by editing `scoring-core`/`derive.rs` directly from the spec table
   without that first.

---

# Handoff — 2026-08-17 (whitepaper v3.2, AIS scoring defect, registration root-caused)

**Correction (2026-08-17, later same day): this section's original claim that "nothing was
committed" is false.** Commit `3372db5` ("Whitepaper v3.2, AIS redefinition, and registration
root cause") landed everything this section describes, including this file. Left in place
uncorrected rather than rewritten, per this file's own 2026-08-12 precedent of not silently
rewriting historical entries — read `§0`/`§4` below as describing the working tree at the
moment this section was drafted, not the repo's state after the session ended. See the new
section at the top of this file for what happened after that commit.

Cross-repo session. ~~**Nothing was committed** — all changes are uncommitted working-tree edits.~~
**(Corrected above — this was committed as `3372db5`.)**
Every claim below was verified directly (tests run, chain reads, PDFs parsed), not inferred.

## 0. If you take away nothing else

- **AIS has a live scoring vulnerability. This is the highest-value open item and it is ~6 lines.**
  `integrity-oracle/backend/src/derive.rs`: `derive_entropy` and `derive_grounding` return **1.0
  (maximum)** when no values are present, and `self_reported_compliance` returns 1.0 for an empty
  batch. Missing data therefore reads as *perfect*. Only `derive_sacrifice` fails closed. Verified
  numerically: a submission carrying token counts but **no analysable content** scores
  r = **0.923** at 100 claimed GPU-hours, while an honest agent with real-but-mediocre telemetry
  scores **0.465** — the content-free agent outscores the honest one roughly two-to-one. Fix:
  return 0 on absent evidence. Independently valuable regardless of any v3 work.
- **Compliance is self-reported for every non-healthcare agent.** `handlers.rs`'s
  `oracle_compliance` falls back to `derive::self_reported_compliance` in six paths, including
  `compliance_vertical != 1`. Only a live healthcare BAA read can override it downward. The
  agent tells the oracle whether it violated policy.
- **Registration was root-caused and is no longer a mystery.** `REGISTRAR_ROLE` on
  `XibalbaAgentRegistry` had been granted **only to an `AgentPrimitivesFactory` address with zero
  deployed bytecode** since 2026-08-13. A prior rotation's `CREATE` never broadcast (only 3 of 22
  txs in `broadcast/RotateOperatorKeyGrant.s.sol/84532/run-latest.json` have real hashes;
  `receipts: []`), but `deployments.baseSepolia.json` was updated with the predicted address
  anyway, and a later manual `cast send` granted the role to that phantom address while revoking
  it from the real factory. A call to a codeless address trivially "succeeds" with empty return
  data — which is exactly the `status: 1`, ~29k-gas, zero-log symptom every attempt produced.
  **Fixed:** deployments files repointed to the real factory `0xC19fc9cB2cB87297EfDF11DA7e211e44A6C1181D`
  and `REGISTRAR_ROLE` re-granted (verified `hasRole == true`). One registration retry away from done.
- **Lesson now encoded in `docs/demo-shield-integration.md`:** never write a deployed-contract
  address to a deployments file or grant it a role without first confirming `eth_getCode` returns
  real bytecode.
- **`.env` key naming is actively misleading.** `FUNDER_PRIVATE_KEY` and `DEPLOYER_PRIVATE_KEY`
  are the **public Anvil test key** (`0xf39Fd6e5…`), useless on Base Sepolia. The key controlling
  the funded `funderWallet` (`0x7530bd7C…`) is `ORACLE_SIGNER_PRIVATE_KEY`. Use that one.

## 1. What was produced

| Artefact | Notes |
|---|---|
| `spec/integrity-protocol-v3.2.md` | 1,646 lines. Markdown+LaTeX, 13 mermaid diagrams, 13 "In plain terms" on-ramps, Appendix D change register. Non-normative; proposes changes for `v0.5-proposed`. |
| `spec/Integrity_Protocol_Whitepaper_v3.2.pdf` | 64pp. Built markdown → HTML (`marked` + `mermaid@11` + KaTeX) → headless chromium print. **No LaTeX/pandoc on this machine.** Chromium is snap-confined and cannot write to or serve from `/tmp` — stage under `$HOME`. |
| `docs/demo-shield-integration.md` | Shield↔integrity-core bring-up runbook, incl. the funder-key trap above. |
| `docs/signer-role-rotation-2026-08.md` | Operator-side steps for the 2-of-3 Safe + distinct EOAs. |
| `PRODUCTION_GAPS.md` | New dated entries: registration root cause, nonce race, RPC read-after-write lag. |

## 2. Substantive spec decisions (don't silently reverse these)

- **AIS redefined** as a *gated* weighted geometric mean over *admissible* evidence (§3.1.1):
  requirements N1–N5, an evidence-admissibility rule (unverifiable assertion scores 0),
  per-component floors enforced by a conjunctive Θ gate reusing the kernel's own constraint form,
  and `r(ι)` normalised from the **pre-boost** score clamped to [0,1]. A bare geometric mean does
  **not** prevent compensation — only exact zero collapses it, and a 90%-violation agent still
  reached r = 0.631. §3.1.4 is a 6-row implementation-delta table; the code does not satisfy it yet.
- **Identity: bridge, not adopt.** Keep `XibalbaAgentRegistry` as substrate; expose a read-only
  ERC-8004-shaped adapter for external legibility. AIS stays the single authoritative `r(ι)` —
  running two reputation systems would reintroduce the commensurability failure §1.2 diagnoses.
  Convergence deferred with explicit revisit triggers.
- **Shield is Untrusted tier** (§9.4), deliberately not part of the guarantee, with a stated
  four-condition path to graduate (hardware root of trust, on-chain remote attestation,
  freshness-with-expiry, honest sensor coverage).
- **Three v3.2 amendments implemented differently from the source register**, each because
  verbatim transcription contradicted an existing section: ZK-telemetry → research horizon, not a
  roadmap phase; hybrid TEE → joint coverage, not "complete mediation achieved"; grace modes →
  operate strictly inside AIS floors. Appendix D records each with reasoning.
- **Cortex corrected the spec, not the reverse:** v3.0's Eq. 5 used naive `∥` concatenation while
  §4.4 warns that construction is an attack surface; Cortex already used an injective encoding.

## 3. Open items, priority order

1. **`derive.rs` items 1–2** — invert the fail-open defaults (§3.1.4 rows 1–2). ~6 lines.
2. **Cortex Merkle malleability** — `events.py`'s `merkle_parent` sorts the pair before hashing and
   promotes odd nodes with no leaf/internal domain tag (CVE-2012-2459 shape). Anchored roots are
   safe (root = chain head); impact is limited to inclusion evidence via `session_merkle_evidence`,
   which calls the **un-domained** `merkle_proof`. Fix before that evidence is used in a dispute.
3. **Registration retry** — stack is up, fix is in, one run to confirm end-to-end.
4. **Doc alignment** — `CLAUDE.md` architecture map, `docs/INTERFACE_CONTRACT.md` (planned v3
   schemas), cortex/shield cross-repo notes. README already has a marked-planned v3 section.
5. **Signer-role rotation** — blocked on operator: needs the 2-of-3 Safe address plus three new
   EOA addresses (see `docs/signer-role-rotation-2026-08.md`). Then adapt
   `RotateOperatorKeyGrant.s.sol` and hand back a `forge script --broadcast` command.
6. **Orphaned testnet contracts** — at least four `SovereignAgent`/`StateAnchor` pairs from failed
   registration attempts against the phantom factory. Real gas spent, no cleanup path. Listed in
   `PRODUCTION_GAPS.md`.

## 4. Caveats

- **Nothing is committed.** Working tree only, across `integrity-core`, `xibalba-shield`
  (`shield/cli.py` device-config fix), and `integrity-sdk` (`chain.py` nonce/read retries).
- `integrity-sdk` suite is green at **259 passed / 3 skipped** after fixing a stale
  `.venv/bin/pytest` shebang carrying the pre-rename path. The README's old "242 passed, 2 failed"
  was unreproducible.
- The docker-compose `mvp` service was removed — it pointed at the deleted `integrity-mvp` repo and
  broke `docker compose up` entirely.
- `DOCKER_RPC_URL` switched to `https://sepolia.base.org`; the previous third-party endpoint was
  responsible for a nonce race and stale role reads.

---

# Handoff — 2026-08-12 (ecosystem stabilization + dual rename: xibalba-graph-memory → xibalba-cortex, INTEGRITY-LATEST → integrity-core)

Cross-repo session covering `integrity-core` (this repo), `xibalba-shield`, and `xibalba-cortex`.
All three repos are clean, tested, fully committed, and fully pushed as of this writing. Nothing
below is inferred — every claim was verified directly (test suites run, files read, git history
checked) during the session.

## 0. If you take away nothing else

- Old names are gone. `INTEGRITY-LATEST` and `xibalba-graph-memory` no longer exist as
  directories or GitHub repos — they are `integrity-core` and `xibalba-cortex` now (old GitHub
  URLs redirect). Don't reintroduce the old names anywhere.
- **Shield currently has NO path to a signed BCC commitment.** The `shield/integrity_exporter`
  module (real signing + submission to `bcc_middleware`) was removed and replaced with plain
  OTel spans that nothing on the `bcc_middleware` side ingests. Tracked in
  `xibalba-shield/IMPLEMENTATION_PLAN.md`'s "Known gap — 2026-08-12" section. This is a real
  regression from previously-working behavior, not a planned-but-unbuilt gap — treat it as
  higher priority than most open items below.
- **The real ZK verifier is live but untested.** `contracts/src/oracle/UltraPlonkVerifier.sol`
  is the actual `bb`-generated verifier now, not the placeholder — `forge build`/`forge test`
  both pass clean (195/195). But there is zero test coverage exercising it with a real proof.
  Tracked in `PRODUCTION_GAPS.md` #26.
- **This repo's own `CLAUDE.md` is stale on that exact point** — its "ZK proof pipeline"
  section still says `UltraPlonkVerifier.sol` "is an explicit placeholder that reverts... until
  replaced wholesale by `make generate-verifier`." That's no longer true. Not fixed this
  session (out of scope of the rename work); fix it before trusting that section again.

## 1. What actually happened, in order

1. **Full audit** of `xibalba-shield`, `xibalba-cortex` (then `xibalba-graph-memory`), and this
   repo (then `INTEGRITY-LATEST`) — git state, uncommitted work, dependency direction, what's
   real vs. documented-only.
2. **Stabilized all three repos' pre-existing uncommitted work** rather than renaming a broken
   tree:
   - `bcc_middleware/app/opa_client.py` had been accidentally deleted (unstaged) while
     `main.py` still imported it — `bcc_middleware` genuinely could not import. Restored
     byte-identical from git history.
   - `contracts/src/oracle/UltraPlonkVerifier.sol`'s dropped `IZkVerifier` conformance and the
     deleted `contracts/test/UltraPlonkVerifier.t.sol` / one test in
     `ReputationRegistry.t.sol` were initially suspected as damage — verified they're actually
     the correct, necessary consequence of swapping in the real `bb`-generated verifier (adding
     back `is IZkVerifier` reproduces a genuine Solidity diamond-conflict compile error;
     confirmed by reproducing then reverting). The removed tests only asserted placeholder-only
     behavior and are correctly gone, not restorable. See §0 for the resulting gap.
   - `xibalba-cortex`'s `store.py` had drifted its event-schema constant from
     `"xibalba.memory.event.v1"` to `"xibalba.memory_event.v1"` in the same uncommitted diff
     that delegated hashing to `integrity_sdk.crypto.merkle.compute_node_hash`. Since
     `verify_chain()` recomputes every stored event's hash using the *current* schema constant,
     this would have made all 366 real memories in the live
     `~/.hermes/xibalba-cortex/graph-memory.sqlite3` fail chain verification with a false
     "corrupted" result. Reverted just the schema string; verified all sampled chains valid
     against the real store afterward.
   - `xibalba-shield`'s uncommitted `integrity_exporter` → OTel + in-process rules → real-OPA
     refactor was mostly done but left stray references to the deleted module in scripts,
     dead test scaffolding (`_RecordingExporter` classes, unused after a `fix_tests.py` scratch
     script had already run once), and zero test coverage for the new span-based telemetry path
     in `agent_core/router.py`. Cleaned up; added 2 new tests (success + tracer-failure paths).
   - **Found a real structural bug in this repo**: `integrity-dashboard/` had its own separate,
     live `.git` (a real, unregistered clone of `integrity-mvp`, not a submodule), while this
     outer repo separately tracked a *stale, directly-committed snapshot* of the same path from
     2026-08-04 — silently diverged for over a week. Confirmed with the user this was leftover
     from the `integrity-mvp`-into-`integrity-core` migration, not the intended state. Removed
     the nested `.git`, reconciled the outer repo to `integrity-mvp`'s actual current state
     (249 files: old single-page panel UI → new routed multi-page app with real
     `shieldBackend.ts`/`graphMemory.ts`/`bccMiddleware.ts` integration clients). One file
     (`gas_usage.jsonl`, an append-only ledger) had disappeared with no successor in that
     diff — restored from its last known state rather than silently dropped.
   - Removed `integrity-dashboard/demo/src/integrity_demo/framework/` (19MB, ~788 files) — an
     unreferenced directory closely mirroring `~/.hermes/hermes-agent`'s own
     skills/hermes_cli/acp_registry layout, sitting unused in a **public** repo
     (`integrity-mvp`) since before this session. Confirmed zero imports from it anywhere in
     the demo package before removing.
3. **Renamed `xibalba-graph-memory` → `xibalba-cortex`** end-to-end: GitHub repo, local folder,
   Python package (`xibalba_graph` → `xibalba_cortex`), env vars (`XIBALBA_GRAPH_MEMORY_*` →
   `XIBALBA_CORTEX_*`), console scripts, MCP server registration name, default state-directory
   paths, the live `~/.hermes/xibalba-graph-memory` state dir → `~/.hermes/xibalba-cortex`
   (366 real memories moved intact, verified), `~/.hermes/config.yaml`, the Hermes plugin
   directory + hardcoded bridge paths, `~/.hermes/cron/jobs.json`, `~/.claude.json`'s
   project/mcpServers/githubRepoPaths entries (backed up first — see `~/.claude.json.bak-*`).
4. **Renamed `INTEGRITY-LATEST` → `integrity-core`** end-to-end, same pattern: GitHub repo
   (`integrity-protocol` was considered and rejected — collides with an existing archived
   private repo in the org), local folder, `contracts/foundry.toml`'s CI-runner path,
   `integrity-dashboard/scripts/copy_shield.cjs`, CI workflows (`e2e.yml`/`wiki-sync.yml` —
   including renaming the required PAT secret `INTEGRITY_LATEST_PAT` → `INTEGRITY_CORE_PAT`,
   **which does not exist yet** — user is handling secret creation separately),
   `wiki-data.json` regenerated via its own sync script (not hand-edited), both sibling repos'
   (`xibalba-shield`, `xibalba-cortex`) dependency paths, `~/.hermes/config.yaml`'s
   `pre_tool_call` hook path, `~/.claude.json` entries, workspace-level
   `/home/xibalba/Projects/CLAUDE.md`.
5. Discovered mid-rename that the branch being worked on (`audit/harness-loop-2026-07-30`) had
   **already been merged into `main` via PR #50 on 2026-08-07** — local `main` was just stale
   (87 commits behind), not genuinely diverged. All new work this session is additional commits
   on top of that already-merged branch, pushed to its own remote ref, **not yet landed into
   `main` via a fresh PR/fast-forward**.

## 2. Verification performed (all passing except where noted)

| Package | Result |
|---|---|
| `contracts` | `forge build` clean, `forge test`: 195/195 |
| `integrity-sdk` | 262 passed, 2 skipped |
| `integrity-cli` | 68 passed, 1 skipped |
| `bcc_middleware` | 121 passed |
| `integrity-oracle` (Rust) | 130 passed (119 backend + 11 scoring-core) |
| `integrity-userapi` | **not verified** — needs local Postgres on `:5435`, not running in this environment |
| `integrity-dashboard` | `tsc -b && vite build` clean; `eslint .` 0 errors (54 pre-existing unused-var warnings untouched); `playwright test` (`test-e2e`) 20/26 — the 6 failures are `health.spec.ts`/`shield.spec.ts` tests needing a live oracle/bcc_middleware stack that wasn't running, not code bugs |
| `xibalba-shield` | 99 passed, 6 skipped |
| `xibalba-cortex` | 108 passed, 1 skipped |

## 3. Open items, in rough priority order

1. **Shield's BCC-signing gap (§0)** — needs a real design decision: does Shield call
   `integrity_sdk.bcc.build_bcc_commitment` directly again, or does `bcc_middleware` grow a
   real OTLP ingestion endpoint that converts incoming spans to signed commitments? Not started.
2. **Create `INTEGRITY_CORE_PAT`** GitHub secret on `integrity-mvp`'s repo settings (fine-grained
   PAT, read-only Contents access to `XibalbaTechSol/integrity-core`) — user is handling this.
3. **Land `audit/harness-loop-2026-07-30` into `main`** — it's pushed to its own remote ref but
   not yet merged/fast-forwarded into `main` via a fresh PR.
4. **Write real ZK verifier tests** (§0) — feed `UltraPlonkVerifier.sol` an actual proof from
   `integrity-zkp`'s pipeline, confirm valid proofs verify and invalid ones don't.
5. **Fix this repo's own stale `CLAUDE.md`** (§0's third bullet) and do a broader documentation
   accuracy pass — requested by the user at session end, scoped to README/SPECIFICATION/
   IMPLEMENTATION_PLAN/`docs/INTERFACE_CONTRACT.md`/`PRODUCTION_GAPS.md` plus the full
   `docs/wiki/` tree across all three repos, explicitly **not** yet started (survey agents were
   launched, one early finding was `docs/wiki/WIKI_LOG.md` is 6 days stale, then stopped
   without applying fixes so the session could wrap cleanly). Pick this up fresh.
6. **Phase 3 verification from the original plan, not done**: confirm Shield's DID registration
   actually round-trips against `integrity-core`'s oracle for real (not just that scripts
   import); confirm whether `xibalba-cortex`'s `anchor_session_root()` has a live receiver
   configured anywhere on the `integrity-core` side — as of this session, confirmed **no**' —
   `XIBALBA_ANCHOR_URL` is documented as something the operator must configure themselves
   (`xibalba-cortex` commit `572f581`), not something this repo currently serves.
7. **Phase 4 cleanup, not done**: `/home/xibalba/Projects/INTEGRITY/xibalba-shield` (a stale,
   unrelated Next.js prototype from the legacy `INTEGRITY` tree) still exists; `/home/xibalba/
   Projects/integrity-mvp/integrity-mvp_ARCHIVED/` is still in that confusing nested-folder
   shape (it's the live standalone `integrity-mvp` repo, not actually archived).
8. **Consider purging `demo/framework/`'s git history** if its prior public exposure on GitHub
   matters — removed from the working tree this session, but old commits (back to `94e226a`)
   still contain it in history/GitHub's cache unless separately purged. Not done, not requested.

## 4. Do not

- Don't restart the `hermes mcp serve` processes forcibly. They are children of *running Claude
  Code sessions* (confirmed via process ancestry — parent is a `claude` process), not a
  standalone daemon; killing one breaks that session's live tool access with no warning to
  whoever's using it. Each session picks up the renamed MCP config naturally on its own next
  restart.
- Don't assume `integrity-dashboard/` is a git submodule — it deliberately isn't (see §1.2); it's
  a plain tracked directory in this repo now, matching the intended
  `integrity-mvp`-migrated-into-`integrity-core` architecture.
- Don't treat GitHub's Dependabot warning (94 vulnerabilities: 2 critical, 53 high, 36 moderate,
  3 low, surfaced on every push this session) as something this session addressed — it wasn't
  investigated at all, just observed.

---

# Handoff — 2026-07-31 (recovery session; shell restored, stack green)

Supersedes the previous handoff of the same date, which was written with **no shell**
and whose headline finding did not survive testing. Nothing below is inferred — every
claim was executed.

## 0. The disk is fine. Delete this worry.

The reboot cleared it.

| Check | Result |
|---|---|
| `/sys/fs/ext4/sdc2/errors_count` | **0** |
| `findmnt -no OPTIONS /` | `rw,noatime,errors=remount-ro` — `emergency_ro` **gone** |
| write to `/tmp` | succeeds |

**`~/fix-root-fs.sh` was not needed and was not run.** The two ext4 errors were a single
incident on 2026-07-30, not ongoing degradation.

One piece of collateral damage remains, and it is **not blocking**: containerd's content
store lost a blob (`sha256:dc009236…`), so `docker images` and `docker system df` fail.
All four project images inspect fine, `docker compose` works normally, and the stack
builds and runs. Full repair needs `sudo ctr -n moby …`, which this session could not run
non-interactively. **Do not `docker system prune -a`** — `integrity-core_pgdata` holds
the oracle's telemetry, i.e. the dogfooding record.

## 1. The previous handoff's headline finding was wrong

It reported *"every `/v1` route returns 500 — the oracle's entire functional surface is
down."* Re-measured against a live stack:

| Route | Then (browser) | Now (measured) |
|---|---|---|
| `/v1/agents` | 500 | **200** (1448 b) |
| `/v1/leaderboard` | 500 | **200** (797 b) |
| `/v1/markets` | 500 | **200** (437 b) |
| `/v1/agent/{live-did}` | 500 | **200** |

The oracle's boot log is clean and contains **zero** sqlx/pool/decode/panic errors in its
entire history. Both suspects it named were wrong: Postgres/Redis are ruled out by that
same log, and the uncommitted `db.rs` query is type-safe (migration 0011 declares
`tier_granted INTEGER`) and demonstrably *works* — `xibalba.integrity` now correctly
reports `verification_tier: 2` instead of the registration floor of 1.

Also withdrawn: the `resolveDID` reverts that filled the log are **correct 404s**, not the
outage. `0x4c2a24b3` is `UnknownDID()`, and `error.rs:66` maps `AgentNotFound` → 404. They
are logged at `ERROR`, which is what made a working service look catastrophic.

**What the 500s actually were is not established.** The container that served them was
replaced before a shell existed to inspect it. The honest statement is that the evidence
was destroyed, not that the problem was solved.

## 2. What was actually broken (and is now fixed)

### The protocol was not anchoring its own evidence — for days, silently

`bcc-middleware` signed every transaction for **chain 31337 while connected to Base
Sepolia (84532)**, so every `anchorRoot` and `updateScore` was rejected:

```
could not anchor 8 leaves for agent did:integrity:68fed1… -- retained in logs only
```

Root cause: `app/config.py:37` reads `CHAIN_ID` (default `31337`), and **`bcc-middleware`
was the one service in `docker-compose.yml` that took `RPC_URL` from env without taking
`CHAIN_ID` from the same place.** A second bug sat behind it — `DEPLOYMENTS_FILE` was
hardcoded to `/deployments.local.json`, so even with the right chain it would have used
anvil addresses on Sepolia. **Both fixed; both were required.**

**Verified by on-chain state change, not by absence of errors:**

| Evidence | Result |
|---|---|
| `anchor_events` rows for this DID | **4**, distinct root + tx_hash each |
| newest `anchor_events.root` vs chain `latestRoot` | **identical** (`0x87bfba4278fd8c4a…`) |
| `cast receipt <tx>` | **`status 1 (success)`** |
| `isAnchoredRoot(old root)` — append-only holds | **`true`** |
| `scores(0x360e…).lastUpdated` | **`1785484478`** (this session) |

A root present in **both** the oracle's `anchor_events` table and the contract's
`latestRoot`, backed by a receipt with `status 1`, means the whole path executed:
commitment → batch → Merkle root → signed `anchorRoot` → mined → recorded. Nonce
advancement (260 → 275) is corroborating only and deliberately not load-bearing — a
reverting tx consumes its nonce too.

Both roles were confirmed before wiring the key in, on **two different contracts**:
`ANCHOR_ROLE` on `StateAnchor` (for `anchorRoot`) and `ORACLE_ROLE` on
`ReputationRegistry` (for `updateScore`).

**This session's own evidence is anchored.** The 5 commits below each fired the vault
hook; `anchor_vault.py` was then run explicitly rather than trusting the SessionEnd spawn
(its own docstring records leaves being stranded when a hook is torn down mid-receipt):
`anchors.jsonl` advanced `leaves_through: 21 → 26`, root
`0xb64a41aac24e20fa…`, `isAnchoredRoot == true`, receipt `status 1`.

### `make test` could record a pass but never a failure

Every line read `cd pkg && pytest && cd .. && $(TEST_STATUS) pkg pass || $(TEST_STATUS) pkg fail`.
On failure, `&&` short-circuits so `cd ..` never runs and the recorder is exec'd from
inside the package dir, where it does not exist → crash. **The mechanism feeding test
outcomes into the anchored evidence chain could only ever write `pass`**, and the crash
aborted the target so later packages never ran at all.

Note the trap: fixing only the path makes `|| … fail` exit 0, so `make test` would report
**success on a red suite**. Fixed as `|| { $(TEST_STATUS) pkg fail; false; }` with
`$(CURDIR)`.

### The importer would have written a false lineage

The handoff flagged "file order == commit order" as unverified. It is **half right**:
timestamps *are* strictly monotonic, but chronological order is **not ancestry**. Of 20
consecutive pairs, 19 are real git ancestor pairs and one is not — `6c0c9bf → d7e4deb`
are siblings off merge-base `354c6b5` (branch switch). A linear chain would have asserted
a `derived_from` edge git says does not exist.

Fixed before the first real run: parents now resolve via `git merge-base --is-ancestor`.
Corrected import records `d7e4deb → 36e23d9b` and leaves `6c0c9bf` as the unmerged branch
tip it is.

### F5 is CONFIRMED — and it is a design bug

Predicted last session, now measured: **21/21 vault leaves are `unverified`**, 17 of them
specifically `unverified:stale`. Not one leaf in the entire history has ever recorded a
verified test result. No commit ordering fixes it — `HEAD ‖ diff` cannot be equal across
the commit boundary. The fix (key status to `git write-tree` / `HEAD^{tree}`) is now
unblocked, since the recorder bug above was its other half.

## 3. State of the tree

All previously-unrun code has now been executed:

| Item | State |
|---|---|
| `integrity-sdk/tests/test_memory_dag.py` | **21/21 pass** (first ever execution) |
| `integrity_sdk/memory_dag.py` | exercised by the above; no changes needed |
| `scripts/import_memory_dag.py` | **fixed** (ancestry), run for real, idempotent on re-run |
| memory DAG | **built** — 21 nodes, `root_of_heads = 0xdc4d6644c6ef5884…`, **not anchored** |
| `docker-compose.yml` | bcc chain fix + **5 healthchecks** added |
| `Makefile` | test-status recorder fixed |
| `bcc_middleware/tests/test_evidence_linkage.py` | de-flaked (was 1 pass / 3 fail) |

Test results this session: SDK **230 passed / 2 skipped** · bcc_middleware **99 passed** ·
OPA **37/37** · userapi **51 passed** · contracts **200** · zkp **4** · oracle **133**.

## 4. Read these

- `docs/design/e2e-audit-2026-07-31.md` — resolution pass at the top; new findings
  **E10–E16**; original text preserved with corrections marked in place.
- `PRODUCTION_GAPS.md` **§24** — the full record, including what stayed open.

## 5. Next, in order

1. ~~**Anchor the memory DAG.**~~ **DONE (2026-08-01).** New `scripts/anchor_memory_dag.py`
   — a companion to `import_memory_dag.py`, not the same path as `anchor_vault.py` (that
   script is hardcoded to the vault's own root). Verified on-chain: `isAnchoredRoot(DAG
   root) == true`, receipt `status 1`, `latestRoot` now the DAG root, and the vault's own
   root (`0x51451cc5…`) still independently anchored — append-only holds across both
   trees. Idempotent by construction (checks `isAnchoredRoot` before submitting).
2. ~~**Fix F5 at the root**~~ **DONE (2026-08-03).** `scripts/tree_hash.py` now hashes
   tracked-file content (`git ls-files`) instead of `HEAD ‖ diff HEAD`, so it's invariant
   across the exact commit boundary that broke it. Verified with a `--self-test` harness
   and live: commit `acdae8b` is the first leaf in the vault's history with a real
   `test_result_hash` instead of `unverified`. See `PRODUCTION_GAPS.md` §19/F5.
3. **Make audit reports survive shutdown** — `ensure_future(to_thread(...))` with nothing
   awaiting it drops in-flight reports on worker exit (audit E16). The test is fixed; the
   production drop is not.
4. **Make the primitives cache chain-aware** (E11) — `/v1/agent/{stale-did}` returns 200
   with `eip155:31337` anvil addresses from a Sepolia oracle. **Do not fix by deleting the
   5 stale rows.**
5. **Re-test the nonce race on a dedicated RPC** (E13) — still fails `nonce too low`
   despite `nonce_lock.py`; cannot separate stale-read from real race on publicnode.
6. Lower `resolveDID` not-found logging to `warn` (E12) — one line, and it manufactured an
   entire false audit.
7. **Make the dashboard image buildable** — `npm install` dies inside Docker with
   arborist's `Cannot read properties of null (reading 'edgesOut')`. This is why
   `make check-deploy` **currently exits 1** (see below). The dashboard's own suite passes
   on the host (20 files / 68 tests), so it is a container-build fault, not broken code.
8. `sudo ctr -n moby` cleanup for the containerd blob.

## 6. Running the stack

`bcc-middleware` needs a funded signer for Sepolia. The key is **not** committed:

```bash
cd ~/Projects/integrity-core
set -a; . ./contracts/.env; set +a
export ORACLE_SIGNER_PRIVATE_KEY="$FUNDER_PRIVATE_KEY"
docker compose up -d
docker compose ps          # postgres/redis/userapi-postgres/oracle/bcc should read (healthy)
```

Two harness gotchas that will otherwise cost you an hour:

- **`make test` needs `userapi-postgres` up.** The target does not start it, so a fresh
  checkout running `make test` alone fails `ConnectionRefusedError` on :5435 — which reads
  as a broken suite rather than a missing dependency.
- **`make check-deploy` currently exits 1, and that is expected.** It correctly reports
  the dashboard image STALE (2026-07-18 vs current source) and the image *cannot be
  rebuilt* until item 7 above is fixed. `oracle-backend`, `bcc-middleware`, and `userapi`
  all report **fresh**. Do not read the non-zero exit as new drift.
- **Trust only the `MAKE_TEST_EXIT=` line, not a wrapper's reported exit code.** A
  backgrounded `make test` was reported as "exit code 0" twice while the real exit was 2.
- If a `test_chain.py` run appears to hang, check for an orphaned `anvil`/`forge script`
  pair from a killed run (`pgrep -fa "forge script|anvil --port"`). It passes in ~3s
  standalone; a stuck pair blocks it indefinitely at ~1% CPU, which looks like compiling.

Architecture decision from last session stands: **two memory systems, deliberately
separate** — the Integrity hash graph (evidence, anchored, never forgets) and
`~/Projects/xibalba-memory/` (recall, mutable, forgets). Open question there — embedder
backend, Ollama vs in-container sentence-transformers — is now answerable with a shell but
blocks nothing.
