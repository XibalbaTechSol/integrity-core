# Formal verification tooling and first-slice scope — go/no-go proposal

**Status:** proposal only. Nothing in this document is authorized. Workstream 3 of completing
whitepaper Phase I (`spec/integrity-protocol-v3.2.md` §10.3, Table 8), following workstream 1
(promotion, `PRODUCTION_GAPS.md` §40) and workstream 2 (declared-asset value conservation,
accepted with a disclosed gas-budget boundary, `PRODUCTION_GAPS.md` §41).

## What the whitepaper actually requires here, precisely

Two passages, both load-bearing, neither vague:

- **Table 8, Phase I gate:** "Independent audit complete; **invariance argument machine-checked**
  for the reference implementation."
- **§9.3, Assurance programme:** "a public formal specification of the constraint grammar with
  **machine-checked proofs of the invariance argument** for the reference implementation."

"The invariance argument" has one specific referent — **Proposition 1** (§4.3, Forward
invariance): for account $A$ mediated by rule (11), if $x_0 \in S_\mathbf{C}$ then $x_k \in
S_\mathbf{C}$ for all $k \ge 0$, for every adversarial input sequence, including one chosen with
full knowledge of $\mathbf{C}$ and possession of the account's signing keys. The proof itself is
a two-line induction and is not in question — what's missing is machine verification that the
**actual deployed Solidity** (`IntegrityAccount`/`IntegrityKernel`, not the paper's abstract
$T$/$V$/$S_\mathbf{C}$) actually implements rule (11) faithfully: that `preCheck`/`postCheck`
really do reject every non-conforming transition and really do leave state unchanged on
rejection, for every reachable input, not just the ones this repo's 321 concrete Foundry tests
happened to construct. Foundry tests are existence proofs ("this specific attack fails"); a
machine-checked argument is a universal claim ("no attack of this shape succeeds"). Mutation
testing (already used throughout this kernel's development) checks that a guard does *something*;
it does not check the guard is *complete* over its input domain.

## Tool options considered

**Certora Prover.** Industry standard for this exact claim class (deployed on essentially every
major DeFi protocol's audit). Spec language (CVL) states invariants and rules independently of
the implementation, proven by an SMT-backed static analysis over the actual bytecode/AST. Real
costs: a new spec language to learn and maintain (not Solidity, not Foundry), typically a cloud
submission (their local/CI mode still calls out to the Certora service for solving), and
licensing (a free tier exists for open-source repos but terms should be confirmed, not assumed,
before relying on it) — the first genuinely non-local, possibly-non-free dependency this repo
would take on for kernel work. Overwhelmingly the tool an external auditor (workstream 5) will
either use themselves or expect to see used.

**Halmos.** Symbolic execution / bounded model checking for Foundry projects (Foundry-native,
Python package, MIT-licensed, developed by a16z crypto's research team). Runs entirely locally
against `forge build` artifacts, no cloud submission, no new spec language — it interprets
existing (or purpose-written) Foundry test functions with **symbolic** arguments instead of
concrete/fuzzed ones, so a property already expressible as a Foundry `assert`-style test is close
to directly reusable. Real cost: bounded, not unbounded — it explores paths up to a configured
loop-unrolling/call-depth bound, so a Halmos "pass" is a genuine proof over that bounded domain,
not an unconditional one; must be stated precisely, never oversold as equivalent to Certora's
unbounded guarantees.

**Foundry invariant/fuzz testing (already in use throughout this kernel).** Property-based, not
exhaustive — samples the input space rather than covering it, even with a high run count. This is
what every existing kernel test already is (including the "mutation-tested" ones — mutation
testing checks a guard isn't dead code, it does not check the guard is complete). **Does not
satisfy "machine-checked proof"** on its own, no matter how many runs; stated here because it's
tempting to conflate "we fuzz aggressively" with "we formally verified this," and this repo's own
no-aspirational-current-tense discipline forbids that conflation.

**K framework / KEVM.** The most rigorous option (full EVM semantics, used for e.g. ERC-20/ERC-777
formal specs and some L1 client verification) and the least tractable here — steep authoring
cost, no existing project expertise, no precedent anywhere in this repo's toolchain. Named for
completeness, not recommended.

## Recommendation

**Halmos first, as this workstream's own deliverable; Certora named explicitly as workstream 5's
tool, not this one's.** Reasoning:

- Matches this repo's standing preference for local, reproducible, pinned tooling over an
  external cloud service (`docs/INTERFACE_CONTRACT.md`'s pinned toolchain is entirely
  local-executable today — forge/anvil, cargo, nargo/bb, opa, node, uv — introducing Certora here
  would be the first exception, for a workstream that doesn't yet need it).
- A bounded symbolic proof is a genuine, real improvement over fuzz/mutation testing and directly
  answers this workstream's own precise gap ("no attack of this *shape* succeeds" vs. "this
  specific attack fails") — it is not the full unbounded guarantee Certora would give, and this
  proposal does not claim otherwise, but it is honestly describable as "machine-checked" in a way
  321 concrete tests are not.
- Certora is better spent once, deliberately, alongside or by the external auditor in workstream
  5 — who will bring CVL expertise this repo doesn't have yet, and whose spec should be written
  against the FINAL reference implementation (after this workstream and any further Phase I
  changes), not re-authored twice.

## First-slice scope: which properties, precisely

Not "verify Proposition 1" as a single undertaking — that's the same mistake the original
tracer-bullet proposal explicitly avoided ("too large a unit to authorize or decline as one
block"). Four properties, each already stated as a concrete guarantee in `IntegrityKernel`'s own
NatSpec and already covered by a corresponding concrete Foundry test — Halmos's job is to promote
each from "true for the tests we thought to write" to "true for all reachable symbolic inputs up
to the configured bound":

1. **Native-ETH budget containment.** For any symbolic `perOpBudgetWei`/`cumulativeBudgetWei` and
   any symbolic sequence of `execute()` calls, no single call's native-balance decrease exceeds
   the per-op budget and no cumulative sequence exceeds the cumulative budget — or the call
   reverts. Directly machine-checks the property `test_overPerOpBudgetCallRevertsBeforeAnyStateChange`/
   `test_overCumulativeBudgetCallRevertsEvenWhenEachCallIsIndividuallyInBudget` each check for one
   concrete case.
2. **Declared-token budget containment.** Same as (1), for `trackedToken`'s two-tier budget
   (`PRODUCTION_GAPS.md` §41) — including the conjunction with (1): a call within the token budget
   but over the native budget must still revert, and vice versa.
3. **Reputation/assurance-tier gating cannot be bypassed while stale or below floor.** For any
   symbolic `snapshotScore`/`snapshotTakenAt`/`block.timestamp` combination, `preCheck` reverts
   whenever the cached score is below `minEffectiveScore`, whenever the snapshot exceeds
   `epochLengthSeconds`, or whenever `isZkBoosted` is false — no combination of these three that
   should fail-closed instead silently passes.
4. **The `armed` reentrancy guard is sound.** No symbolic reentrant call sequence can pass two
   `preCheck`/`postCheck` pairs' worth of budget accounting for what is actually one nested call —
   generalizes the existing single concrete reentrancy test
   (`test_reentrantExecuteDuringAnInFlightCallIsRejected`) to the shape of attack, not one
   instance of it.

**Explicitly deferred, not attempted in this slice:** the kernel-swap governance state machine
(guardian quorum, timelock, rescue sweep) — a much larger state space (multiple pending-action
types, nonce tracking, guardian set mutation) that deserves its own scoped verification slice
rather than being folded in here; the ZK attestation pipeline (Noir circuit correctness is a
different formal-methods problem entirely, arguably already partially addressed by the circuit's
own `nargo test` suite, out of scope for Halmos which reasons about EVM bytecode, not Noir);
anything about `IntegrityAccount`'s ERC-7579 mode-restriction logic beyond what's already
exercised concretely (`test_batchExecutionModeIsRejected` etc.) unless a first attempt shows
Halmos handles it cheaply.

## Dependency inventory — done, findings below (2026-08-24)

Run against a throwaway `uv`-managed venv (`.halmos-probe`, not committed, not the repo's real
pinned location — this was a probe, not the install), per the discipline named below.

- **Halmos 0.3.3 installs cleanly** via `uv pip install halmos` — 19 packages, ~lightweight (a
  bundled `z3-solver` 4.12.6.0 is the default SMT backend; `yices-solver` also pulled in as an
  alternative; no heavy web3/brownie dependency chain). No conflict with this repo's pinned
  Python 3.12/uv 0.11.
- **Confirmed working against real, non-trivial solc 0.8.28 output**, not just documentation
  claims: a minimal standalone Foundry project (`solc_version = "0.8.28"`, matching
  `contracts/foundry.toml` exactly) produced a genuine unbounded symbolic pass
  (`check_addCommutes(uint256,uint256)`, `bounds: []`, i.e. proven for literally all `uint256`
  inputs, not a sampled subset) in 0.01s. The tool itself works correctly in this environment.
- **Real, blocking incompatibility found against THIS repo's actual test fixture — not a
  hypothetical risk, a measured one.** Pointing Halmos at `IntegrityAccountTest`'s real `setUp()`
  (`--contract IntegrityAccountTest --function test_zeroTokenBudgetsAreAllowedWhenTrackedTokenIsDisabled`,
  the simplest test in the file) fails immediately with `Unsupported cheat code: getNonce(address)`
  — Halmos does not implement `vm.getNonce`, which `setUp()`'s CREATE-address-prediction dance
  (`vm.computeCreateAddress(address(this), vm.getNonce(address(this)) + 1)`) depends on to break
  the kernel/account mutual-reference circularity. Result: `HalmosException: No successful path
  found in setUp()` — none of the four named properties can be attempted against the existing
  fixture as written. (The earlier ~150s timeouts before this was isolated were `forge`
  recompiling/relinting the full 133-file project on a cold cache, not Halmos itself being slow —
  once build artifacts were warm, Halmos's own failure surfaced in 0.18s.)
- **This is a real design question, not a mechanical fix, and is being surfaced rather than
  patched unilaterally.** The kernel/account circularity this pattern breaks is not a test-only
  artifact — the *production* contracts have the same immutable mutual reference (kernel binds to
  an account address at construction; account installs a kernel address at its own construction).
  A Halmos-compatible harness needs either (a) a fixed/hardcoded expected nonce (deployment order
  inside `setUp()` is itself deterministic, not symbolic, so this is very likely a correct,
  low-risk substitution, but should be verified, not assumed) or (b) a different circularity-
  breaking construction entirely (e.g. CREATE2 with a known salt, or a two-phase
  placeholder-kernel-then-swap using the existing kernel-swap governance path) — a genuine design
  choice with its own tradeoffs, not something to decide inside a "dependency inventory" step.

**Recommendation given these findings:** proceed with Halmos (the tool itself is confirmed
compatible and functional in this environment) but treat "design a Halmos-compatible test harness
for `IntegrityAccountTest`'s constructor circularity" as its own explicit, scoped step before any
of the four named properties are attempted — not a detail to resolve inline while writing the
first property. This document does not choose between (a)/(b) above; that decision should be its
own go/no-go, matching the granularity discipline every prior kernel-adjacent proposal in this
repo has followed.

## Process discipline

1. **Dependency inventory first**, matching every prior kernel-adjacent proposal's own discipline:
   confirm Halmos's actual current version, its Python/Foundry version compatibility against this
   repo's pinned `forge`/`solc` (`docs/INTERFACE_CONTRACT.md`), and install it in a way that
   doesn't disturb the existing `contracts/` Foundry-only toolchain (a separate `uv`-managed
   virtualenv, matching how every other Python package in this repo is isolated — not a bare
   global `pip install`).
2. **One property at a time**, red-to-green: write the symbolic Halmos test, confirm it fails
   against a deliberately broken kernel (a version with the relevant `require`/`revert` removed,
   reusing the mutation-testing discipline already standard here) before trusting a pass against
   the real one — the formal-methods equivalent of this repo's existing mutation-testing
   requirement, and for the same reason: a symbolic test that can't fail proves nothing.
3. **State the bound explicitly in every result** — loop-unrolling depth, call-count bound, any
   `sound? / unsound?` flag Halmos itself reports — never present a bounded pass as an unbounded
   guarantee.
4. **`docs/INTERFACE_CONTRACT.md`'s pinned toolchain gains a Halmos entry** if this is authorized,
   same as every other tool in that table.

## Acceptance criteria

- Halmos installed, pinned, documented; runnable via a `make`-style target
  (`make verify-kernel` or similar, matching this repo's existing `make test`/`make sync-abis`
  pattern) rather than a one-off manual invocation nobody can reproduce.
- All four named properties either (a) pass with a stated bound, or (b) are reported as an honest
  finding if Halmos cannot complete within a reasonable resource budget — matching this repo's own
  "report it, don't silently work around it" precedent from the Table 4 gas finding
  (`PRODUCTION_GAPS.md` §41).
- A short, precise statement — same register as this kernel's own guarantee-statement NatSpec —
  of exactly what was machine-checked and to what bound, added to `IntegrityKernel`'s doc comment
  and to `PRODUCTION_GAPS.md`. No claim beyond what Halmos actually proved.
- `docs/INTERFACE_CONTRACT.md` updated with the new pinned tool version.

## Real risk, stated before any tooling is installed

- **Halmos may not scale to this kernel's actual state space** within reasonable time/memory —
  external-call-heavy code (the `ReputationRegistry`/`trackedToken` cross-contract reads) is a
  known harder case for symbolic execution than pure-arithmetic contracts; this must be measured,
  not assumed tractable because the properties above sound simple.
- **A bounded proof is genuinely weaker than what "machine-checked" might imply to a reader who
  doesn't read the bound.** This proposal's own acceptance criteria require stating the bound
  every time specifically to prevent this workstream's result from being read as more than it is
  — the same overclaiming risk this whitepaper's own §1.2 spends real effort warning against in
  ERC-8004's case.
- **This does not, on its own, clear Table 8's Phase I gate**, which requires BOTH machine-checked
  invariance AND independent audit (workstream 5) — completing this workstream is necessary, not
  sufficient.

## Decision needed

1. **Authorize as scoped above** — Halmos, four named properties, dependency inventory first,
   one-property-at-a-time discipline.
2. **Authorize with changes** — different tool choice, different property scope, or defer the
   dependency-inventory step to its own separate go/no-go.
3. **Not yet** — hold until workstream 4 (testnet deployment) or workstream 5 (external audit)
   scoping clarifies whether the auditor would rather author their own Certora spec against a
   kernel with no prior Halmos work, making this workstream's own effort partially redundant.

This document does not authorize itself.
