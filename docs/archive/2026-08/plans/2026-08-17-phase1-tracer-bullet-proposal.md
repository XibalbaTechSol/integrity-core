# Phase I tracer-bullet slice — go/no-go proposal

**Status:** proposal only. Nothing in this document is authorized. Written after independently
verifying the active plan's (`/home/xibalba/.claude/plans/where-are-we-with-dapper-gem.md`)
core factual claims against actual code and reviewing the Devil's Advocate findings already on
record (`CLAUDE_HANDOFF_2026-08-17.md` §9). Do not begin implementation from this document
alone — it exists to make the go/no-go decision concrete, not to replace it.

## Why a slice, not the whole kernel

The full Phase I plan (`IntegrityAccount` + `IntegrityKernel` + constraint grammar + module
governance + reference adapters + canonical intent encoding, ~7 substantial pieces) is too large
a unit to authorize or decline as one block. The Devil's Advocate review already narrowed the
honest claim considerably — a hook can enforce *enumerated post-state predicates over a
deliberately restricted execution grammar*, not general projected post-state — and named specific
prerequisites (exact dependency pinning, a dedicated governance state machine, a versioned
identity/controller interface, hook-frame authentication) that don't yet exist. A minimal,
disclosed-scope slice is what the review's own §10 recommends: something small enough to be a
real decision, not a down payment on the whole architecture.

## What this is NOT

- **Not** the full `IntegrityAccount`/`IntegrityKernel` from the plan — most of Phase I stays
  explicitly out of scope (see below).
- **Not** deployed anywhere. Foundry-test-only for the duration of this slice; no Base Sepolia
  broadcast under any circumstance as part of this slice's completion criteria.
- **Not** adopted as v0.4/v0.5 accepted behavior regardless of outcome — same authority
  discipline as every other spec-adjacent artifact this session.
- **Does not** touch any existing agent, registry, or live contract. `SovereignAgent` and its
  registered agents are structurally untouched (confirmed: `AgentPrimitivesFactory` clones only
  the other 5 primitives, `SovereignAgent` itself is constructor-deployed, not a proxy — nothing
  about this slice can retrofit or migrate an existing agent).

## Scope: the slice itself

Verbatim from the Devil's Advocate review's own recommendation (`CLAUDE_HANDOFF_2026-08-17.md`
§9), made concrete:

- Non-deployable, **non-upgradeable** experimental account.
- **Exactly pinned** OZ `AccountERC7579Hooked` + ERC-4337 `EntryPoint` version — a real
  dependency-inventory step done and written down *before* any Solidity is touched (the review
  flagged this as not yet done: "the manifest range, lockfile version, EntryPoint version...
  must be pinned and characterized").
- Atomic kernel binding at construction. The hook slot is immutable — no later repoint, no
  upgrade path, by construction not by policy.
- **Single default `CALL` execution mode only.** No `delegatecall`. No batch. No
  `EXECTYPE_TRY`.
- No executor modules, no fallback modules, no recursive self-calls, no post-bootstrap module
  install/uninstall. Module mutation as a constrained transition (complete-mediation condition
  (iii)) is **explicitly deferred, not solved** by this slice — must be stated as a disclosed
  limitation in every doc/test touching this code, never silently assumed.
- Authenticated, one-shot hook frames: each `preCheck`/`postCheck` pair correlates account,
  execution depth, action digest, pre-state digest, configuration epoch, and nonce, consumed
  exactly once. A shared "latest snapshot" is explicitly unsafe per the review.
- No prefund, no ERC-4337 `UserOp` gas-sponsorship path exercised.
- **One** conserved quantity: a single, immutable native-value budget (per-operation and
  cumulative), checked in `postCheck`. Deliberately not general value conservation — the review
  is explicit that's invalid until each asset profile defines a closed accounting universe, and
  this slice defines exactly one.

## Explicitly deferred — real Phase I work, not attempted here

- Module governance / timelocked, multi-party kernel removal (plan item 4).
- Any reference adapter beyond the one spend-cap check (reputation-floor and assurance-tier
  adapters wait for AIS's still-unmade floor-value decision and the pre-boost accessor's
  first real consumer, respectively).
- Canonical intent encoding / the BCC `chain_id`+verifier-address binding fix — real, verified
  gap (`integrity_sdk/bcc.py`'s signed fields genuinely carry neither), but separable work.
- ERC-6551, Phase II entirely.
- Any Base Sepolia deployment, testnet or otherwise.

## Process discipline

1. **Dependency inventory first**, written down, not assumed: exact installed OZ version from
   the lockfile (not just the `^5.3.0`/`^5.6.1` manifest ranges), exact ERC-7579 draft interface
   in use, `EntryPoint` version compatibility. A real research step with a citable answer before
   any contract code exists.
2. **Strict red→green TDD** — one failing Foundry test first, confirmed failing for the right
   reason, smallest implementation that passes, repeat. No horizontal pile of stub contracts or
   speculative interfaces ahead of a test that needs them.
3. **Complete-mediation test suite scoped to what this slice actually claims** — enumerate the
   one execution path (single `CALL`) and assert it reverts under an over-budget attempt.
   Explicitly do **not** claim or imply coverage of paths this slice doesn't implement (batch,
   executor, fallback, module mutation): test names and docs must say "disabled by construction,
   not applicable" for those, never silently omit them the way a coverage gap normally would.
4. **Gas assertions from day one** — `preCheck` ≤ 40k (paper's Table 4 budget), enforced as a
   real regression test even for this one constraint, not measured once and forgotten.

## Acceptance criteria for this slice specifically

- Real Foundry tests, passing, proving: (a) an in-budget `CALL` succeeds and commits; (b) an
  over-budget `CALL` reverts before any state change; (c) `delegatecall`/batch/module-install
  attempts revert or are structurally impossible to construct, not merely untested; (d) a hook
  frame cannot be replayed — the same account/depth/digest/epoch/nonce tuple consumed twice
  fails on the second attempt.
- A short spec note, in the same register as the whitepaper's own Proposition 1 language,
  stating **exactly** what this slice's guarantee covers and does not cover. No aspirational
  language — the standing rule this whole codebase is built around.
- `PRODUCTION_GAPS.md`/`HANDOFF.md` updated the same as every other piece of work this session.
  No exception for kernel code just because it's more technically interesting.
- Explicitly **not** deployed to Base Sepolia as part of "done" — that is a separate, later,
  separately-approved decision, not an automatic next step once tests pass.

## Real risks even at this reduced scope

- This is still smart-contract security work — a materially larger blast-radius category than
  anything else done this session (which was read-only research, local-anvil-tested code, or a
  well-understood, previously-precedented governance role grant).
- "Non-deployable" protects against on-chain risk, not against burning real time on an approach
  that gets revised once the dependency inventory surfaces something the plan didn't anticipate.
- No external audit applies at this stage. The review's own gate to Phase II is "audit +
  machine-checked invariance" — neither applies here. This slice, even fully complete, must
  never be cited as "the kernel is built" or "Proposition 1 holds" — it proves a narrower,
  explicitly-scoped claim only.

## Decision needed

This document does not authorize itself. Options, for the record:

1. **Authorize as scoped above** — build exactly this slice, strict TDD, Foundry-only, no
   deployment.
2. **Authorize with changes** — narrower or differently-scoped than above.
3. **Not yet** — stay at plan + review stage; revisit later.
