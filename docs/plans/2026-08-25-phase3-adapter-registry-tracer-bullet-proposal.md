# Phase III adapter-registry tracer-bullet slice — go/no-go proposal

**Status:** proposal only. Nothing in this document is authorized. First workstream of whitepaper
Phase III ("Registry" — `spec/integrity-protocol-v3.2.md` §6, §10.3 rollout), following Phase II's
kernel-hook slice (`PRODUCTION_GAPS.md` §51). Confirmed before writing this: **zero existing code
anywhere in this repo implements a generic constraint-vector encoding, an adapter registry, or
any part of §6/§8/§9's attestation-staking machinery** (`grep` across `contracts/src/` for
`AdapterRegistry`, `ConstraintVector`, `IConstraintAdapter` came back empty). `IntegrityKernel`
and `LicenceAccount` both hardcode their own conditions directly as Solidity conditionals — there
is no generic, adapter-compiled constraint representation anywhere to build a registry on top of.
This is a genuine greenfield undertaking, and a larger one than either Phase I's or Phase II's
first slice.

## What whitepaper §6 actually is, and what it isn't

§6.4: "Adapters are permissionless to author but admitted through a registry whose admission
criteria mechanically enforce R1–R3 (differential replay for determinism, metered call for gas
bound) and structurally enforce R4. R5 gates installability *without operator override*. Because a
share of the protocol fee routes to the author of the adapter that gated a transaction (§8.3), the
registry is a market rather than a catalogue." Table 3's five obligations (§6.2):

| Req | Name | Obligation | Mechanically checkable? |
|---|---|---|---|
| R1 | Determinism | identical payloads → identical constraints, no dependence on block state | only via an off-chain differential-replay admission SUITE, not a contract |
| R2 | Totality | always returns a decision; unparseable input → typed reject, never silent accept | partially — interface shape can force *a* return, not that it's the *right* one |
| R3 | Bounded cost | declared worst-case gas, honoured under metered call | yes — a registry can enforce this on-chain |
| R4 | Conservatism | adapters may only ADD constraints, never relax | structural — true by construction if adapters are ANDed, not a separate check |
| R5 | Attestation | published source + spec + independent audit before install-without-override | economic/social — "requires the staking design of Section 8" (§6.2's own words) |

Only R3 and R4 are things a smart contract can actually enforce today. R1 needs off-chain tooling
this repo has never built (a differential-replay harness). R5 needs the full §8 token/staking
economics (θ_i = s_i/S capacity shares, slashing, §8.3's fee-routing market, §8.3's stablecoin
yield) — genuinely out of scope for a first slice, matching how Phase I's own kernel-swap
governance and Phase II's own marketplace/escrow wiring were each deferred past their first
slices too.

**The gate FROM Phase II TO Phase III was never itself closed** (Table 8: "sustained real
licensing volume from counterparties who are not the protocol's own contributors" — an adoption
metric). Per this session's own standing decision, that does not block starting Phase III work; it
only means Phase III's own eventual completion claim inherits the same non-code adoption
dependency Phase II's does.

## Scope: exactly two mechanically-checkable pieces, nothing else

**In scope:**
1. **A minimal, fixed constraint-vector encoding** — NOT the general DSL whitepaper §7.5.2
   proposes (`integrity-dsl`, explicitly its own later Trusted-tier compiler toolchain). A small
   closed enum of constraint *kinds* already proven elsewhere in this codebase — spend-budget
   (per-op/cumulative, `IntegrityKernel`'s own shape), reputation-floor (`ReputationRegistry`,
   also already proven), timestamp-bound (`LicenceAccount`'s expiry shape) — each with packed
   `uint256` parameters, matching Table 4's "constraints read from packed storage" cost note. This
   is the ONE real design risk in this slice: get the encoding wrong and every future adapter
   inherits it.
2. **`AdapterRegistry.sol`**: permissionless `register(address adapter, uint256 declaredGasBound,
   bytes32 specHash)`; a metered-call wrapper that invokes the adapter with a gas stipend capped
   at `declaredGasBound` and marks it non-compliant (not merely "reverted") if it runs out; an
   `isInstallable(address adapter)` view that returns `false` for every adapter until R5
   attestation exists — i.e. EVERY adapter in this slice requires an explicit
   `operatorOverride` to actually install, matching §6.4's own "R5 gates installability without
   operator override" language precisely rather than silently treating "registered" as "vetted."

**Explicitly deferred, not attempted:**
- **R1's differential-replay admission suite** — off-chain tooling, no on-chain component;
  separately scoped later work, same category as ATCP/IP's session-key layer was for Phase II.
- **R5's staking/attestation economics in full** — no `stakedITK`, no slashing, no ERC-7484-style
  vetting record, no fee-routing (§8.3's `μ_ad` split). This slice's registry can only ever answer
  "registered, gas-bound-declared" — never "attested," and `isInstallable` says so honestly by
  always requiring override.
- **The general DSL/compiler toolchain (§7.5.2, `integrity-dsl`)** — a separately audited,
  Trusted-tier component per the whitepaper's own words; nothing in this slice is a step toward
  that compiler.
- **Wiring the registry into `IntegrityKernel` or `LicenceAccount`'s actual `preCheck`/
  `preConsume` path** — this slice proves the registry can admit and gas-meter an adapter in
  isolation; making either existing account type actually CALL a registered `IAdapter` instead of
  its own hardcoded checks is real, separately-scoped follow-on work (and arguably shouldn't
  happen until the interface has proven itself on at least one real adapter beyond the two seeded
  here).
- **Composition/conjunctive evaluation across multiple installed adapters** (Proposition 2) — this
  slice registers and gas-meters ONE adapter at a time; multi-adapter AND-composition is not
  exercised.

## Design decision: bespoke-contract adapters behind a minimal `IAdapter` interface, not a packed enum

**Resolved by `docs/design/phase3-adapter-encoding-strategy-2026-08-25.md`, adopted here.** That
note compared a packed-enum constraint vector (a closed set of constraint *kinds*, dispatched by
an on-chain interpreter) against bespoke-contract adapters (each adapter its own deployed
contract behind one shared minimal interface, the registry storing only metadata). Finding: the
packed-enum approach does not actually satisfy whitepaper §6.1's own stated reason adapters
exist — a closed enum requires a core-interpreter change for every genuinely new constraint
shape, which is exactly the "protocol upgrade per policy class" problem adapters are supposed to
eliminate. Bespoke-contract adapters do not have this ceiling, and the pattern is already proven
in this codebase: `ILicenceHook.sol`/`ReputationFloorLicenceHook.sol` (landed this session,
`PRODUCTION_GAPS.md` §51) is Approach B in miniature.

**Decision: `IAdapter`, a new, shared, minimal interface** (`check(...)`, revert-to-reject, no
bool/status return — matching every existing check in this codebase's own style). Whether
`ILicenceHook` and `IAdapter` end up being the SAME interface or deliberately separate is left
open per the design note's own unresolved-questions section; this proposal's first slice does
not need that answered — it can seed `AdapterRegistry.sol` against two reference `IAdapter`
implementations without touching `LicenceAccount` or `ILicenceHook` at all.

**Two seed adapters, as reference `IAdapter` implementations, not enum variants:**
`SpendBudgetAdapter.sol` (mirrors `IntegrityKernel`'s per-op/cumulative native-value check) and
`ReputationFloorAdapter.sol` (mirrors `ReputationFloorLicenceHook`'s effectiveScore check) —
proving the registry's admission/metered-call machinery against two structurally different
adapters (one needs a live balance read, one needs a live external-contract read) without
inventing any constraint this codebase hasn't already proven correct in isolation, and without
closing off what a THIRD, unanticipated adapter author could later register.

## Process discipline (matching every prior kernel-adjacent proposal)

1. **Dependency inventory first, written down** (done above — confirmed zero existing generic
   constraint-vector code before scoping this).
2. **Strict red-to-green TDD**, one failing Foundry test at a time.
3. **Mutation-tested guards** on the metered-call gas-bound enforcement specifically — the one
   mechanism this slice trusts to make R3 real rather than aspirational.
4. **No claim of R1 or R5 compliance anywhere in NatSpec or `PRODUCTION_GAPS.md`** — `isInstallable`
   returning `false`-without-override for everything is the honest statement, not a placeholder to
   silently relax later without a dated entry recording the change.

## Acceptance criteria

- Real Foundry tests proving: a registered adapter within its declared gas bound executes
  normally; an adapter that would exceed its declared bound is caught by the metered-call wrapper
  and marked non-compliant, not merely left to revert-and-look-like-any-other-failure; `register`
  is permissionless and idempotent-safe (re-registering the same adapter address does not
  silently overwrite a different `declaredGasBound`/`specHash` without an explicit re-registration
  path); `isInstallable` returns `false` for every registered adapter absent an explicit
  `operatorOverride`, proven directly, not assumed from the absence of a staking mechanism.
- Both seed adapters (`SpendBudgetAdapter`, `ReputationFloorAdapter`) register, gas-meter, and
  evaluate correctly through the registry, and produce the same accept/reject decision as
  `IntegrityKernel`'s/`ReputationFloorLicenceHook`'s own existing logic on the same inputs —
  proving `IAdapter` is faithful to shapes already trusted, not merely internally consistent.
- A guarantee statement in the same register as `IntegrityKernel`'s and `LicenceAccount`'s own
  NatSpec: precisely what this registry proves (R3 gas-bound enforcement, permissionless
  registration) and does NOT prove (R1 determinism, R5 attestation, R4 as anything beyond
  "structural by construction," composition across multiple adapters).
- `PRODUCTION_GAPS.md` updated with a dated entry, same as every prior slice.

## Real risk, stated before any code exists

- **`IAdapter`'s exact method signature is the one decision this slice can't easily walk back.**
  Every future adapter — including ones authored outside this repo, if the registry is ever
  genuinely permissionless in practice — implements whatever shape this slice picks. Getting this
  wrong doesn't just cost a rewrite of this slice; it costs a rewrite of everything built on top
  of it. This risk is smaller than it was under the packed-enum approach (a new adapter no longer
  requires a core-interpreter change), but the interface itself is still a one-way door. Recommend
  treating the two-seed-adapter scope above as deliberately small BECAUSE of this risk, not
  despite it.
- **Metered call in the EVM is not free to get right.** `gasleft()`-based stipend enforcement has
  known sharp edges (the 63/64ths rule, cold/warm access cost differences between the metering
  call and a real call) — this slice needs the same "measure, don't assume" discipline that caught
  `IntegrityKernel`'s own Table-4 gas crossing (`PRODUCTION_GAPS.md` §41) and `LicenceAccount`'s
  `via_ir` timestamp-caching miscompilation (§48). Expect a real measurement pass before trusting
  any declared-gas-bound claim.
- **`isInstallable` always requiring override for everything may read as "the registry does
  nothing."** That is the honest state of an unattested registry, not a bug — but it means this
  slice provides real R3 enforcement and real bookkeeping, and nothing that changes what an
  operator can safely install without their own judgment. Worth naming explicitly so "Phase III
  started" is never mistaken for "adapters are now safely permissionless."

## Decision needed

1. **Authorize as scoped** — two seed reference `IAdapter` implementations (`SpendBudgetAdapter`,
   `ReputationFloorAdapter`), `AdapterRegistry.sol` with permissionless registration and
   metered-call gas-bound enforcement, `isInstallable` always requiring override, R1/R5
   explicitly not attempted.
2. **Authorize with changes** — different seed adapter pair, or further changes to the interface
   design.
3. **Not yet** — further resolution needed before committing to this scope.

This document does not authorize itself.

## Outcome (2026-08-25)

Option 2 exercised in one round: the original packed-enum encoding was split out for its own
design pass (`docs/design/phase3-adapter-encoding-strategy-2026-08-25.md`), which found the
packed-enum approach does not satisfy whitepaper §6.1's own goal and recommended bespoke-contract
adapters behind a minimal `IAdapter` interface instead. This document is revised above to adopt
that finding. Scope is now: **authorized as revised** — `IAdapter.sol`, `AdapterRegistry.sol`,
`SpendBudgetAdapter.sol`, `ReputationFloorAdapter.sol`, exactly as the revised sections above
describe. Implementation proceeds next.
