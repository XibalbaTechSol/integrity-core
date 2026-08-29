# Halmos-compatible test harness — go/no-go proposal

**Status:** proposal only. Nothing in this document is authorized. Follow-up to
`docs/plans/2026-08-24-phase1-formal-verification-proposal.md`'s dependency-inventory finding:
Halmos 0.3.3 is installed, confirmed functional and unbounded-proof-capable against this repo's
pinned `solc 0.8.28`, but fails immediately against `IntegrityAccountTest`'s real `setUp()` with
`Unsupported cheat code: getNonce(address)` — the CREATE-address-prediction dance every kernel/
account test in that file depends on to break the two contracts' immutable mutual reference
(kernel binds to an account address at construction; account installs a kernel address at its
own construction). This is a real design question, named but not resolved in that document.
Scoped here per its own recommendation: "before any of the four named properties are attempted —
not a detail to resolve inline."

## Why this is a real question, not a test-only inconvenience

The circularity is architectural, not incidental to testing. `IntegrityKernel`'s `boundAccount`
is `immutable`, set once at construction; `IntegrityKernel.onInstall` reverts unless
`msg.sender == boundAccount` (`onlyBoundAccount`). So a kernel MUST be deployed already knowing
the exact address of an account that doesn't exist yet, and that account's constructor must
install a kernel whose immutable binding matches it exactly. Production deployment (workstream 4)
will face this identical problem — it hasn't been solved there yet either (README: the kernel
slice is "never referenced by `Deploy.s.sol` or any deployment script"). Whatever this proposal
picks has a real chance of also informing that later, separate deployment-scripting decision —
worth noting, not a reason to widen this proposal's own scope to solve deployment too.

## Additional empirical grounding gathered before drafting this (2026-08-24)

Beyond the `getNonce` failure already reported, three more facts were checked directly against
Halmos 0.3.3 rather than assumed, since this proposal's comparison depends on them:

- **`vm.prank(address)` works**, including with a fully symbolic address argument — proven
  unbounded (2 paths, both the prank-matches and identity branches implicitly covered) in 0.02s
  against a minimal probe contract.
- **`vm.warp(uint256)` works**, including with a fully symbolic timestamp — same probe, same
  unbounded result.
- **Native CREATE2 deployment (`new Contract{salt: salt}()`) works**, including with a fully
  symbolic `salt` — proven unbounded in 0.01s. This needs no cheatcode at all; it's a core EVM
  opcode Halmos's symbolic executor already has to support to deploy any contract.

Not yet measured: the full "compute a CREATE2 address via `keccak256(0xff ++ deployer ++ salt ++
keccak256(initcode))`, deploy against it, verify prediction == actual" round trip end-to-end. This
is pure arithmetic over data Halmos already handles (hashing, address computation), so it is
very likely to work, but "very likely" is an estimate, not a measurement — stated as the first
concrete step below, not assumed complete here.

## Option A: patch the existing pattern — hardcode the expected CREATE nonce

Replace `vm.getNonce(address(this))` with a literal integer, keeping `vm.computeCreateAddress`
(a pure, non-state-changing cheatcode — not directly proven above, but not implicated in the
`getNonce` failure either, and reasonable to expect works since it doesn't touch chain nonce
state, just formats an address from given inputs).

**What this costs:**
- The literal nonce value is only correct for one exact, fixed deployment sequence preceding it.
  This is fragile in the specific way this repo's own conventions warn against — a "magic number"
  whose correctness depends on invisible context (every earlier `new`/`Clones.clone` call in the
  same harness) rather than being self-evident at the call site.
- Reusing `IntegrityAccountTest`'s actual 112-test `setUp()` is not viable regardless of this
  fix alone — that fixture deploys a second token-tracking pair, has many concerns beyond what a
  minimal Halmos harness needs, and changes over time as the concrete test suite evolves,
  meaning the hardcoded nonce would silently go stale the next time someone touches `setUp()`
  for an unrelated reason, well outside this proposal's own visibility.
- Therefore Option A's real form is not "patch `setUp()`" but "write a small, DEDICATED,
  Halmos-only harness contract with its own minimal deployment sequence and its OWN hardcoded
  nonce" — decoupled from the concrete test suite specifically so it doesn't drift with it. This
  is a real design commitment (a new file, a new maintenance surface), not a one-line patch, and
  should be sized as such.

**What this buys:** closest to today's existing pattern conceptually (still "predict then
deploy"), minimal new Solidity to write, self-checking via the same `assertEq(actual,
predicted, ...)` pattern already used, which fails loudly (not silently) if the hardcoded nonce
ever drifts from the harness's own real deployment sequence.

## Option A′: CREATE2 with a known salt — cheatcode-free, empirically confirmed compatible

Deploy both `IntegrityKernel` and `IntegrityAccount` via `new X{salt: someSalt}(...)` instead of
plain `new`. A CREATE2 address depends only on `(deployer, salt, keccak256(initcode))` — never on
deployment order or the deployer's nonce — so the account's future address can be computed by
pure Solidity arithmetic (`keccak256` over the standard CREATE2 preimage) **before deploying
anything**, with zero cheatcode dependency at all. Breaks the circularity the same logical way
(predict, then deploy the dependency, then deploy the dependent, then verify), but the prediction
step needs nothing Halmos might not support, because it needs nothing beyond `keccak256` and
`abi.encodePacked` — ordinary Solidity, already proven to execute correctly and unboundedly
under Halmos via the CREATE2-deployment probe above (a stronger, more directly-relevant capability
than the prediction arithmetic itself, which is strictly simpler).

**What this costs:**
- More setup code than Option A: computing an address via the CREATE2 formula by hand (or via
  OpenZeppelin's `Create2.computeAddress`, if that's available and itself Halmos-compatible —
  needs the same "measured, not assumed" check as everything else here, since it's a different
  code path than the native `new{salt:}` opcode already confirmed) requires getting the
  `initcode` (creation bytecode + ABI-encoded constructor args) exactly right, which is more
  surface for a mistake than a single literal integer.
- Diverges from the concrete-test-suite's own pattern (CREATE-nonce prediction) — two different
  circularity-breaking idioms exist in the repo afterward, one per test framework, which is a
  real (if small) comprehension cost for whoever reads both later.

**What this buys:**
- **No hardcoded, context-dependent magic number.** The salt is a free, self-contained choice
  (e.g. a fixed `bytes32` constant); the predicted address only depends on values already known
  at the point of prediction, not on "how many things were deployed before this in the file,"
  so it can't silently drift the way Option A's literal nonce can.
- **Directly reuses exactly the two Halmos capabilities already empirically confirmed** (CREATE2
  deployment, arbitrary symbolic arithmetic) rather than resting on an untested cheatcode
  (`vm.computeCreateAddress`) whose Halmos-compatibility is inferred, not measured.
- Incidentally produces something closer to what a real CREATE2-based deployment script
  (workstream 4) might want anyway, if that path is ever chosen for production — not a goal of
  this proposal, but a genuine, free side benefit worth naming.

## Option B: placeholder kernel, then a real governance kernel-swap

Deploy the account first with a trivial, unconditionally-passing placeholder hook module (no
`boundAccount` restriction at all, so it can be installed by any freshly-constructing account
without knowing its address in advance) — genesis-installed the same way the real kernel is
today, just with a do-nothing module. Once the account exists (address now concrete), deploy the
REAL, fully-configured `IntegrityKernel` bound to that now-known address, then drive it through
the account's own real governance path (`proposeKernelSwap` → guardian approvals → `vm.warp` past
the timelock → `executeKernelSwap`) to install it for real.

**What this costs:**
- Meaningfully more moving parts per test: an extra contract deploy, a `propose` call, two
  `approve` calls (2-of-3 guardian quorum in the existing concrete fixture), a `warp`, an
  `execute` — each an additional opportunity to hit a different unsupported cheatcode or a
  performance cliff, which directly works against the point of building a *minimal* harness.
  `vm.prank`/`vm.warp` are now confirmed to work, which de-risks this somewhat, but the surface
  is still substantially larger than either address-prediction option.
- Exercises code (the kernel-swap governance state machine) this proposal's own parent document
  explicitly deferred as "a much larger state space... deserves its own scoped verification
  slice" — Option B would entangle harness setup with governance-path execution on every single
  property test, making it harder to keep the four target properties' own symbolic proofs
  minimal and fast, which matters because Halmos's tractability against this kernel's
  external-call-heavy code is itself still an open question (the parent proposal's own named
  risk), and every unnecessary extra state transition makes a scaling problem more likely.

**What this buys:**
- Closest to "how this would really have to work in production" if production deployment ever
  needs the same placeholder-then-swap pattern (e.g. if CREATE2 salt-mining turns out to be
  impractical for the real deployment pipeline for some reason not yet known) — but this is
  speculative, not a currently-identified production requirement, and shouldn't weigh heavily
  against the added complexity cost above.
- Would, as a side effect, be the first real (if narrow) exercise of the kernel-swap path under
  symbolic conditions — arguably valuable, but that's the *next* workstream's job
  (`docs/plans/2026-08-24-phase1-formal-verification-proposal.md`'s own explicitly-deferred
  scope), not this one's, and folding it in here undoes that deferral without a separate
  decision to do so.

## Recommendation

**Option A′ (CREATE2 with a known salt).** It is the only option resting entirely on Halmos
capabilities already measured, not inferred or assumed — both the deployment mechanism itself
(native CREATE2) and the general symbolic-arithmetic capability the address-prediction formula
needs are proven, unbounded, and fast. It avoids Option A's context-dependent magic number
(a real, if minor, drift risk this repo's own conventions consistently flag elsewhere) without
Option B's much larger state-transition surface, which risks compounding with the already-open
question of whether Halmos scales to this kernel's cross-contract-call-heavy code at all. Option
B's one genuine advantage — exercising the governance path — belongs to a separately-scoped
future workstream, not this one.

## First concrete step if authorized

Exactly the "not yet measured" item named above: write the smallest possible standalone Halmos
test proving the full predict → deploy-kernel → deploy-account (both via CREATE2) → verify
round trip, using dummy/trivial constructor arguments (not the real `ReputationRegistry`/
`trackedToken` wiring yet), before building the real dedicated harness contract against this
repo's actual `IntegrityKernel`/`IntegrityAccount`. Matches the same "one property/one step at a
time, confirm before building on it" discipline the parent proposal already committed to.

## Decision needed

1. **Authorize Option A′** — CREATE2-salt harness, smallest-round-trip step first, then the real
   dedicated harness contract, then (separately, per the parent proposal) the four named
   properties.
2. **Authorize Option A** — hardcoded-nonce harness instead, accepting the magic-number
   maintenance risk in exchange for staying closer to the existing concrete-test idiom.
3. **Authorize Option B** — placeholder-then-swap, accepting the larger per-test state-transition
   surface in exchange for exercising the real governance path early.
4. **Not yet** — hold pending further Halmos scaling checks against something closer to the real
   kernel's actual complexity (e.g. a `ReputationRegistry` clone deploy + one cross-contract read)
   before committing to any harness design, in case the deeper scaling risk this proposal doesn't
   resolve turns out to dominate the harness-design choice anyway.

This document does not authorize itself.

## Outcome (2026-08-24)

**Option A′ was authorized first, then found infeasible during implementation — not a Halmos
limitation, a mathematical one.** Attempting the "smallest round trip" step this document itself
named surfaced two real findings, in order:

1. **Option A (hardcoded CREATE-nonce) is dead.** Reading Halmos 0.3.3's own source
   (`halmos/sevm.py`'s `create()`) shows plain `CREATE` addresses are assigned from an internal
   synthetic counter (`new_address()`, `magic_address + offset + counter`), never computed via
   real RLP/nonce semantics. Confirmed empirically too: a hand-written RLP-based address
   predictor, cross-validated correct against `vm.computeCreateAddress` and a real deployment
   under plain `forge test` (nonces 0–20, all matching), failed unconditionally under Halmos for
   every nonce tried.
2. **Option A′ (CREATE2-salt prediction) is dead for a deeper reason.** Halmos's CREATE2
   addressing DOES match the standard formula exactly (verified directly, unbounded, for a fully
   symbolic salt) — the tool isn't the problem. The problem is structural: `IntegrityKernel`'s
   real constructor args must embed `IntegrityAccount`'s real final address, and vice versa, so
   both contracts' CREATE2 addresses depend on each other's address through a one-way hash — a
   genuine two-variable fixed point with no closed-form solution, true on real Ethereum as much
   as under Halmos. No salt choice resolves it.

**Option B was authorized next and built successfully.** `contracts/test/halmos/
KernelSwapHarness.t.sol`: a trivial `AlwaysPassingPlaceholderKernel` (no `boundAccount`
restriction, so it needs no address known in advance) is genesis-installed on a real, unmodified
`IntegrityAccount`; the REAL `IntegrityKernel` (bound to `address(account)`, now concrete, never
predicted) is then installed for real through the account's own actual governance path —
`proposeKernelSwap` → two guardian `approveKernelSwap` calls → `vm.warp` past the timelock →
`executeKernelSwap`. Two `check_` functions, both passing **unbounded** (`bounds: []`) in under
1 second combined: the swap mechanism alone (placeholder → placeholder, 0.15s) and the real target
(placeholder → real `IntegrityKernel` with a real `ReputationRegistry` clone, 0.64s).

**Two more real, disclosed Halmos incompatibilities found and worked around along the way, both
cross-validated against plain `forge test` before being trusted:**
- `vm.prank`/`vm.warp` — confirmed **supported**, including with fully symbolic arguments.
- `vm.getNonce`/`vm.computeCreateAddress` — confirmed **unsupported** (the original finding this
  whole document exists to resolve).
- `vm.store`/`vm.load` — confirmed **supported**.
- `stdStorage`'s `checked_write` (used by the concrete test suite's own `_setZkBoostExpiry`) —
  confirmed **unsupported**: it depends on `vm.record()`, which Halmos does not implement. Fixed
  by writing the storage slot directly (`forge inspect ReputationRegistry storage-layout` gives
  `scores` at slot 1; a mapping-entry-plus-struct-offset computation, cross-validated against the
  real `scores(address)` getter under concrete `forge test` before trusting it symbolically).
- A separate, unrelated build-config gap: Halmos requires `forge build --ast` — without it, every
  contract's artifact is silently skipped (`KeyError: 'ast'`) rather than erroring, which looks
  exactly like "no tests found" if not caught. `Makefile`'s new `verify-kernel` target always
  passes `--ast`.

**Reproducible, not a one-off:** `make verify-kernel` (Halmos 0.3.3, pinned, isolated in
`contracts/.venv-halmos`, created on first run) runs both checks from a clean state. Full write-up:
`PRODUCTION_GAPS.md` §42. The harness itself is complete — the four target properties from
`docs/plans/2026-08-24-phase1-formal-verification-proposal.md` are unblocked and are the next,
separately-scoped step, not yet attempted here.
