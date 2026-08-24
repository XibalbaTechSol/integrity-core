# Phase II licence-account tracer-bullet slice — go/no-go proposal

**Status:** proposal only. Nothing in this document is authorized. First workstream of whitepaper
Phase II ("Metered IP" — `spec/integrity-protocol-v3.2.md` §10.3 Table 8), following Phase I's
full closure (promotion, declared-asset conservation, four machine-checked properties, testnet
deployment, Devil's Advocate governance/EntryPoint hardening — `PRODUCTION_GAPS.md` §40-46).
Confirmed before writing this: **zero existing code anywhere in this repo touches ERC-6551,
licence accounts, or ATCP/IP** (`grep` across `contracts/src/`, `integrity-sdk/`, and
`node_modules` for all three came back empty). This is a genuine greenfield undertaking, not an
extension of anything already built.

## What Table 8's Phase II actually is, and what it isn't

"ERC-6551 licence accounts with live consumption ledgers; ATCP/IP intent format; settlement
integration" (Table 8) — but the GATE to Phase III is "sustained real licensing volume from
counterparties who are not the protocol's own contributors" (same table). That gate is an
**adoption metric**, not a code-completion metric — no amount of building gets there without
someone else actually using it. This proposal is scoped to the buildable part only; it does not
and cannot claim to close the Phase II→III gate on its own, matching this repo's own standing
discipline against overclaiming (Phase I's own testnet deployment made the identical distinction
against Table 8's audit gate).

## Whitepaper grounding (§5, not re-derived, quoted precisely)

- **§5.2, eq (15)/(16):** a licence is an ERC-6551 token-bound account (TBA) attached to an
  ERC-721. Its state subset is $S_I = (b_I, L_I, q_I, H_I)$ — accrued royalties, terms, a
  consumption meter, a usage-history commitment. Control follows `ownerOf` the NFT; transferring
  the token atomically transfers command of everything the account holds.
- **§5.3, eq (17), "the transfer-drain problem":** while a transfer is armed, balance may not
  fall below the level committed to in the sale — "a withdrawal attempt during that window is not
  detected and disputed afterwards; it reverts." Named explicitly as the reason a kernel
  (constraint-checking hook) belongs **on the licence account itself**, not only on agent
  accounts — "the same mechanism serves both."
- **Table 2 (§5.4):** nine licence terms and their constraint decomposition. Volume cap
  ($q_{k+1} = q_k - c_k \ge 0$, pre-check on every consumption call) and royalty ($\Delta b_I \ge
  p(c_k)$ atomically with release, i.e. equation (12)'s value conservation) are the two simplest
  — no external signal, no off-chain state, no typed-intent decoding required. The other seven
  (term/expiry, field of use, licensee identity, exclusivity, derivative rights, assurance tier,
  memory continuity) each pull in a dependency this slice can defer without weakening the core
  claim being proven.

## Scope: exactly two licence terms, nothing else

**In scope:**
1. A minimal ERC-6551 licence account (a token-bound account attached to a licence ERC-721),
   using the **canonical ERC-6551 registry already live on Base Sepolia** — confirmed by direct
   `cast code` check before writing this (real bytecode at
   `0x000000006551c19487814612e58FE06813775758`, the same address on every EVM chain by design),
   not a repo-deployed registry.
2. Volume-cap enforcement: a consumption meter that only depletes, never resets, reverts once
   exhausted.
3. Royalty enforcement: a consumption call must atomically pay at least the declared per-unit
   price into the licence account's own accrued-royalty balance, or revert.
4. The transfer-drain guard (eq 17): while a transfer of the underlying NFT is armed/pending, the
   royalty balance cannot be withdrawn below the level committed to at sale time.

**Explicitly deferred, not attempted:** ATCP/IP signed intents (§7.1 steps 1-4 — this slice's
consumption calls are called directly, matching how Phase I's own tracer-bullet slice used
`vm.prank` before EntryPoint integration existed); the adapter registry (§6) — terms are
hardcoded into this one reference licence account, not compiled from an external payload;
state channels (§7.5.1) — every consumption call settles on-chain individually, gas-prohibitive
above ~10Hz per the whitepaper's own admission, acceptable for a tracer bullet; the other seven
Table 2 terms (expiry, field of use, licensee identity, exclusivity, derivative rights, assurance
tier, memory continuity); and any integration with `IntegrityKernel`/`IntegrityAccount` — see the
design decision below for why.

## Design decision: a bespoke minimal account, NOT a hybrid with the existing Phase I kernel

The whitepaper states plainly that "the kernel installed on the licence account... the same
mechanism serves both" (§5.3) — implying the eventual architecture reuses `IntegrityKernel`'s own
hook pattern on licence accounts too. That is a real, larger undertaking: `IntegrityKernel`/
`IntegrityAccount` are built around ERC-4337 (smart account, EntryPoint validation) + ERC-7579
(hook module installation or removal via governance). ERC-6551 token-bound accounts are a
**different standard** — ownership resolves via `ownerOf` on an external NFT, not via a signer or
EntryPoint, and a TBA's canonical `execute()` shape differs from ERC-7579's
`execute(mode, executionCalldata)`. Combining both correctly (a licence account that is
simultaneously a valid ERC-6551 TBA AND a valid ERC-7579-hooked account) is real, non-trivial
engineering — precisely the kind of thing Phase I's own original tracer-bullet proposal avoided
by choosing the narrowest possible slice first.

**Recommendation: a standalone, bespoke ERC-6551 account for this slice**, with volume-cap and
royalty checks hardcoded directly into its own `execute()`-equivalent function — no hook
abstraction, no kernel reuse, matching exactly how Phase I's OWN first slice hardcoded one
conserved quantity before any adapter/hook abstraction existed. The "kernel serves both account
types" architecture is real Phase II work, but is its own, later, separately-scoped extension —
attempting it in the FIRST slice repeats the exact scope-creep risk Phase I's original proposal
named and declined.

## Process discipline (matching every prior kernel-adjacent proposal)

1. **Dependency inventory first, written down.** No vendored ERC-6551 interfaces exist in this
   repo's `node_modules` (checked, not assumed) — `IERC6551Registry`/`IERC6551Account` need to be
   hand-written against the actual EIP-6551 spec text, not guessed. Cross-validate the hand-written
   interface against the REAL registry's actual behavior (a `cast call` against
   `0x000000006551c19487814612e58FE06813775758`'s `account(...)` view function on Base Sepolia,
   with concrete parameters, checked against the hand-computed CREATE2 address formula) before
   trusting it, matching the "verify the manually-derived formula against real behavior" discipline
   from the Phase I kernel deploy script's own CREATE-address work.
2. **Strict red-to-green TDD**, one failing Foundry test at a time.
3. **Mutation-tested guards** on the two conserved-quantity checks (volume-cap depletion, royalty
   payment) and the transfer-drain guard specifically, same discipline as every Phase I check.
4. **A concrete licence ERC-721** — this slice needs SOME NFT contract to attach the TBA to; a
   minimal, purpose-built one (mint-by-owner, no marketplace logic, no metadata beyond what's
   needed to test) rather than depending on or modifying anything from the existing 7-primitive
   agent model, which this slice is deliberately NOT touching.

## Acceptance criteria

- Real Foundry tests proving: a consumption call within the volume cap and with sufficient
  royalty payment succeeds and correctly decrements the meter / increments the balance; a call
  exceeding the remaining meter reverts before any state change; a call with insufficient royalty
  reverts before any state change; the transfer-drain guard genuinely blocks a withdrawal attempt
  made while a transfer is armed, and permits one when no transfer is pending (matching Phase I's
  own boundary-case testing discipline — exact-boundary and one-unit-over cases, not just interior
  ones).
- The hand-written ERC-6551 interfaces cross-validated against the real, live registry on Base
  Sepolia, not merely assumed correct from reading the EIP text.
- A short, precise guarantee statement in the same register as `IntegrityKernel`'s own NatSpec —
  exactly what this slice proves and does not prove, no aspirational language.
- `PRODUCTION_GAPS.md` updated with a dated entry, same as every Phase I slice.

## Real risk, stated before any code exists

- **ERC-6551's `execute()` and ERC-7579's `execute()` are genuinely different shapes** — this
  slice's account will NOT be interchangeable with `IntegrityAccount` in any tooling that expects
  one or the other; that's a deliberate, disclosed scope boundary, not an oversight to fix later
  by accident.
- **The transfer-drain guard (eq 17) needs a real notion of "a transfer is armed"** — ERC-721
  doesn't have a native "pending sale" concept; this slice needs to define what "armed" means
  concretely (e.g. an explicit escrow/commit step this account itself exposes, since there's no
  existing marketplace contract in this repo to hook into). This is real design work, not merely
  implementation, and may surface its own sub-decision before code is written.
- **Value conservation here is a hard invariant**, same category as Phase I's own declared-token
  conservation (§41) — the royalty payment check cannot be cached or approximated; expect a
  similar gas-measurement discipline to matter here too, though likely less acute since this
  slice has no analogue to Phase I's reputation/assurance-tier caching complexity to interact with.

## Decision needed

1. **Authorize as scoped** — bespoke minimal ERC-6551 licence account, volume-cap + royalty +
   transfer-drain guard only, dependency inventory (interface hand-write + live cross-validation)
   first.
2. **Authorize with changes** — different term pair, or authorize attempting the kernel-hybrid
   architecture instead of the bespoke-account path (a materially larger first slice).
3. **Not yet** — the "what does 'a transfer is armed' concretely mean absent a marketplace
   contract" question above may warrant its own resolution before committing to this scope.

This document does not authorize itself.

## Outcome (2026-08-24)

Authorized as scoped, Option 2 in one respect: the user added expiry as a third licence term
("lets add expiration in 1 above") on top of the original volume-cap/royalty pair, otherwise
confirming every other design question as recommended (bespoke standalone account, not a
kernel hybrid; explicit `armTransfer`/`disarmTransfer` for the transfer-drain guard).

Built exactly as scoped, plus the registry-integration test this document's own acceptance
criteria named but that wasn't explicitly enumerated as a separate deliverable up front:
`IERC6551.sol`, `LicenceToken.sol`, `LicenceAccount.sol` (three terms + transfer-drain guard),
`LicenceAccount.t.sol` (25 tests), `Erc6551RegistryIntegration.t.sol` (6 tests, forked against
the real live canonical registry on Base Sepolia, not a mock). 31/31 passing. All three hard
guards mutation-tested per this document's own process-discipline section. Full detail:
`PRODUCTION_GAPS.md` §47.

Not deployed to any live network as part of this slice — that remains separate, later scope.
This slice does not and cannot close the Phase II→III gate (Table 8's adoption-volume metric);
it closes only the buildable part this document scoped.
