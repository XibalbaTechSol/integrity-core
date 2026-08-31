# Phase III adapter encoding strategy — packed-enum vs. bespoke-contract adapters

Companion to `docs/plans/2026-08-25-phase3-adapter-registry-tracer-bullet-proposal.md` (that
proposal's own decision-needed section split this question out rather than committing to an
encoding inside the same document). This note compares two ways to represent what an adapter
"is" on-chain, before any `AdapterRegistry.sol` code exists. Nothing here is authorized; this is
research, not a scope decision.

## The question

Whitepaper §6.1: "A kernel that hardcoded any of them would require a protocol upgrade per policy
class — which is to say, it would not scale... Adapters invert this... the enforceable policy set
grows permissionlessly." That is the actual bar a Phase III design has to clear. Two candidate
shapes were on the table in the original registry proposal:

**A. Packed-enum constraint vector** — a fixed, closed enum of constraint *kinds*
(`SPEND_BUDGET`, `REPUTATION_FLOOR`, ...), each instance a `(kind, packed uint256[] params)`
tuple. A single on-chain interpreter dispatches on `kind` and evaluates. Adapters compile external
payloads (a licence document, a mandate) into arrays of these typed constraints off-chain,
submitted on-chain for the interpreter to check.

**B. Bespoke-contract adapters behind a minimal shared interface** — each adapter is its own
deployed contract implementing one small interface (a `check(...)`/`preCheck(...)`-shaped
function, revert-to-reject). The registry stores metadata about arbitrary adapter contracts
(address, declared gas bound, spec hash) and evaluates by calling the adapter directly, metered.
No generic on-chain representation of "what a constraint is" exists at all — the adapter contract
IS the constraint, in Solidity, not in data.

## Finding: Approach A does not actually satisfy §6.1's own stated goal

This is the central result of this note, and it changed the recommendation from what the original
registry proposal assumed. A packed enum is closed by construction: representing a genuinely new
constraint shape — one the enum's authors didn't anticipate — requires adding a new enum variant
and a new interpreter branch, which is a change to the SAME shared contract every adapter depends
on. That is precisely the failure mode §6.1 names as the reason adapters exist at all ("a protocol
upgrade per policy class"). A packed-enum registry is a strictly more indirect version of what
`IntegrityKernel` and `LicenceAccount` already do today (hardcoded Solidity conditionals) — it
adds a dispatch layer without adding the actual property (permissionless growth of the policy
vocabulary) that makes the adapter architecture worth building.

This was not obvious before writing it down. The original Phase III registry proposal's own "two
seed adapter kinds" scoping (`SPEND_BUDGET`, `REPUTATION_FLOOR`) is honest about being a small,
disclosed first slice, but it inherits this ceiling silently — nothing in that proposal flagged
that the packed-enum shape itself, not just the two-kind seed, caps how far the design can grow
without a future core change. Recorded here so that ceiling is explicit before any code commits
to it.

## Approach B is already proven, in this exact codebase, this session

`ILicenceHook.sol` / `ReputationFloorLicenceHook.sol` (`PRODUCTION_GAPS.md` §51, landed
2026-08-25) is Approach B in miniature: a minimal interface (`preConsume(...)`, revert-to-reject),
one bespoke reference implementation, and `LicenceAccount` calling it via a metered-nothing
(unbounded, in that slice's disclosed scope) external call. Generalizing this pattern into a
Phase III registry means:

1. Define one shared interface, `IAdapter`, roughly `check(bytes calldata context) external`
   (revert-to-reject, matching every existing check in this codebase's own style — no bool/status
   return anywhere else here, no reason to start now).
2. `AdapterRegistry.sol` stores `(address adapter, uint256 declaredGasBound, bytes32 specHash)`
   per registration — metadata ABOUT an arbitrary contract, never a representation of what that
   contract checks.
3. The metered-call wrapper (R3) calls `adapter.check{gas: declaredGasBound}(context)` — this
   works identically regardless of what the adapter internally does, unlike Approach A where the
   interpreter must understand every constraint kind to meter it correctly.
4. A NEW constraint shape never anticipated by this repo — field-of-use, exclusivity-count,
   whatever a future licence needs — is just a new deployed contract implementing `IAdapter`.
   Nothing in `AdapterRegistry.sol` or `IAdapter.sol` changes. This is the actual property §6.1
   asks for.

### R1 (determinism / differential replay) works at least as well under Approach B

The original registry proposal treated R1 as needing off-chain tooling regardless of encoding —
that holds for both approaches, but it's worth confirming Approach B doesn't make it WORSE.
Differential replay means: submit the same payload/context twice against the same adapter, at the
same state, and confirm identical output. That works by literally calling the adapter contract
twice (or once on a fork, once locally) and diffing results — it needs no declarative
representation of the constraint at all. A bespoke Solidity contract is exactly as replayable as a
packed-enum tuple; R1's admission-suite tooling is genuinely encoding-agnostic. This removes what
looked like a possible argument for Approach A (a fully declarative encoding does not become
obviously auditable in any way a plain small contract isn't) and it was worth checking explicitly
rather than assuming.

### Where Approach A still legitimately wins

Named honestly, not glossed over:

- **Gas.** A packed `uint256[]` read from storage and dispatched through an interpreter is
  cheaper than an external `CALL` to a separate contract (cold-access cost, `CALL` overhead)
  for the SAME simple constraint. `IntegrityKernel`'s own Table-4 gas discipline
  (`PRODUCTION_GAPS.md` §41) exists precisely because ≤40k gas for `preCheck` is a real, measured
  constraint for anything wired into ERC-4337's validation-phase path. If Phase III's registry is
  ever wired into that specific path (explicitly out of scope for the tracer-bullet slice, per the
  registry proposal's own deferred list), Approach B's per-adapter `CALL` cost could reopen the
  same crossing §41 already found once.
- **On-chain auditability of the constraint itself.** A packed enum's parameters are directly
  readable from storage by any observer without needing to trust that an arbitrary contract's
  bytecode actually implements what its `specHash` claims. This is exactly R5's job in the full
  whitepaper design (attestation closes this gap economically) — but R5 is explicitly deferred in
  both approaches' first slice, so today, under EITHER approach, "the adapter's bytecode really
  does what it says" is unverified. Approach A only looks more auditable while R5 doesn't exist;
  once it does, this advantage mostly disappears (an attested bespoke contract is just as
  legible as an attested enum entry, from an auditor's perspective).

Neither of these is disqualifying for a tracer-bullet slice that explicitly doesn't wire into the
ERC-4337 validation-phase path and explicitly doesn't claim R5 attestation yet.

## Recommendation

**Approach B — bespoke-contract adapters behind a minimal `IAdapter` interface, with
`AdapterRegistry.sol` storing metadata only.** It is the only one of the two that actually
satisfies whitepaper §6.1's stated reason adapters exist, it is already proven in this codebase
(`ILicenceHook.sol`, landed and tested this session), and it does not foreclose a future,
separately-scoped, gas-optimized packed encoding for a NARROW subset of high-frequency constraint
kinds if that ever becomes load-bearing (nothing about choosing Approach B for the registry
prevents `IntegrityKernel`/`LicenceAccount` from continuing to hardcode their own hot-path checks
inline, exactly as they do today).

Concretely, this means the Phase III registry proposal's own "two seed adapter kinds" section
should be revised, if and when that proposal is re-authorized, from "two enum variants" to "two
reference `IAdapter` implementations" — `SpendBudgetAdapter.sol` and `ReputationFloorAdapter.sol`
(the latter can likely be `ReputationFloorLicenceHook.sol` itself, generalized to the shared
`IAdapter` interface rather than `LicenceAccount`'s own bespoke `ILicenceHook`, if the two
interfaces can be reconciled — a real open question this note does not resolve, flagged for the
revised proposal to address explicitly).

## What this note does not settle

- Whether `ILicenceHook` and a new generic `IAdapter` should be the SAME interface (making
  `LicenceAccount`'s existing hook slice directly registry-compatible) or deliberately separate
  (keeping `LicenceAccount`'s narrow, already-shipped interface stable and untouched, with
  `IAdapter` as a new, wider one). Both are defensible; this is a real decision for the revised
  registry proposal, not a foregone conclusion of this note.
- The exact shape of `check`'s parameters (a single opaque `bytes calldata context` vs. typed
  parameters closer to `ILicenceHook.preConsume`'s explicit `(account, consumer, units,
  royaltyPaid)`) — opaque bytes maximizes generality (any future caller shape) at the cost of
  every adapter needing its own ABI-decode step; typed parameters are cheaper and clearer but tie
  the interface to today's known callers (kernel-style and licence-style checks). Not resolved
  here.
- Anything about R5/staking, fee routing, or wiring into `IntegrityKernel`'s or
  `LicenceAccount`'s actual gate path — all still out of scope per the registry proposal's own
  deferred list, unaffected by this encoding decision.
