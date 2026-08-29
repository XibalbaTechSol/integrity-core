# ZK circuit `chain_id` binding into `intent_commitment` (scoping only)

**Status:** Implemented and landed (2026-08-18/19) — full scope, not the smaller circuit+verifier-
only option. The user explicitly chose to also wire `integrity-sdk`'s `prover.py` to the real
circuit for the first time (discovered mid-planning that it had never been connected at all —
see below), rather than deferring that piece. Both `chain_id` AND `verifying_contract` are bound
(the user's explicit choice, matching §30's non-ZK precedent, not chain_id alone). Full writeup:
`PRODUCTION_GAPS.md` §36. Circuit: 6/6 `nargo test --workspace` passing (was 4). Contracts:
`forge build` + full `forge test` 310/310, zero regressions, against the regenerated verifier and
real fixtures. SDK: new `tests/unit/test_prover.py` (6 tests, real end-to-end proof generation +
verification, no mocking) plus full suite 270 passed / 3 skipped, zero regressions. One
architectural discovery not anticipated in the scoping below: `integrity-zkp` needed restructuring
into a two-member Nargo workspace (`circuit/` + `tools/commitment_calc/`) because there is no
Python Pedersen-hash implementation anywhere in this repo and `prover.py` needs
`agent_id_commitment`/`intent_commitment` before it can write `Prover.toml` — `commitment_calc`
computes both through the real toolchain instead. Not committed, not deployed — same standing
rule as every prior Phase I slice. The rest of this document is preserved as written (the original
scoping) for the historical record — see the writeup above for what specifically diverged
(the `VerifierRegistry` migration-policy question below was resolved as "not applicable": nothing
is deployed against the old circuit shape and no real proofs exist against it, so there is no live
population to migrate).

## Why this slice

`PRODUCTION_GAPS.md` §30 closed the general-purpose half of canonical intent encoding: the BCC
wire-format commitment now signs `chain_id`/`verifying_contract`, closing cross-chain/cross-
deployment replay for every non-ZK BCC-signed action. It explicitly did not touch the ZK proof
pipeline: `integrity-zkp/src/main.nr`'s Pedersen hash for `intent_commitment` still covers only
`secret_key`, `intent_payload_hash`, `agent_id_commitment`, `nonce` — a real proof generated for
one chain/deployment remains valid, byte-for-byte, if replayed against `ReputationRegistry.
submitZkAttestation` on any other chain or deployment sharing the same agent DID and Merkle root
structure. This proposal scopes closing that specific remaining gap.

## Why this is the largest of the six, named precisely rather than left vague

This is not "one field added to one hash." It is a change that propagates through every layer of
a pipeline this codebase treats as load-bearing precisely because it's real (not mocked):

1. **Circuit change.** `integrity-zkp/src/main.nr`'s Pedersen hash gains a new public input
   (`chain_id`). This changes the circuit's ABI — every existing caller that assembles
   `publicInputs` for `nargo execute`/`bb prove` must be updated in lockstep, not independently.
2. **Verifying-key regeneration.** A circuit's VK is a function of its exact constraint system —
   adding a public input changes it. `make vk` must be rerun, and the new VK is not
   backward-compatible with proofs generated against the old one.
3. **Solidity verifier regeneration.** `UltraPlonkVerifier.sol` is `bb`-generated from the VK
   (CLAUDE.md's own description: "the real `bb`-generated verifier... not the placeholder"). A
   new VK means a new generated verifier contract, which must be redeployed.
4. **`VerifierRegistry` per-agent pinning.** CLAUDE.md documents `VerifierRegistry` exists
   specifically for "per-agent verifier-version pinning" — this is the exact mechanism that makes
   a verifier upgrade safe without breaking already-registered agents, but it means this change is
   not "swap one verifier," it's "add a new pinned verifier version and decide the rollout policy
   for the 7 agents already registered" (CLAUDE.md: "All 7 agents registered before this change
   still report `latestRoot == 0`" — a precedent for how partial-rollout state gets disclosed, not
   hidden, from a prior primitive-adoption slice).
5. **Fixture invalidation.** CLAUDE.md: "Four Foundry tests now exercise a checked-in real proof
   and reject malformed, tampered-proof, and tampered-public-input cases." A new public input
   shape invalidates the checked-in real proof fixture those tests use — they must be regenerated
   against the new circuit/VK, not just re-pointed at new bytes.
6. **Prover call-site updates.** `integrity-sdk/prover.py` (the real `nargo execute` + `bb prove`
   driver) and any equivalent in `integrity-cli` must supply `chain_id` as a new proof input,
   sourced correctly (presumably `Settings.chain_id`, matching the pattern §30 already established
   for the BCC wire format — reuse that source, don't introduce a second one).
7. **`submitZkAttestation` call-site / ABI shape.** `ReputationRegistry.submitZkAttestation`'s
   `publicInputs` parameter shape changes to match the new circuit. Any off-chain code that
   constructs this call (SDK, CLI, dashboard demo if it exercises ZK proving) needs the matching
   update.

Six of these seven items are pure migration mechanics that a single-package slice never has to
deal with — this is why the item is scoped as the largest, not because the actual cryptographic
change (one more field in one Pedersen hash) is conceptually hard.

## What this does NOT close, even once built

- Does not bind `verifying_contract` into the circuit, only `chain_id` — the proposal should
  state explicitly whether both fields are in scope (matching §30's BCC precedent, which bound
  both) or `chain_id` alone (smaller, but leaves a real asymmetry between the BCC wire format's
  guarantee and the ZK proof's guarantee that must be disclosed if chosen).
- Does not retroactively invalidate or migrate any already-submitted on-chain attestation — this
  only changes what a *newly generated* proof must contain; old attestations already recorded in
  `ReputationRegistry` storage (score, `zkBoostExpiry`) are untouched by a circuit change, since
  the boost from a prior proof either already expired or continues under whatever guarantee it
  was originally submitted under.
- Does not resolve the known, disclosed BCC-adjacent gap noted in CLAUDE.md: "Rust's `serde_json`
  doesn't escape non-ASCII by default while the Python side's `ensure_ascii=True` does" — unrelated
  encoding issue, orthogonal to this proposal.

## Scope decision needed before a full proposal can be written

Given the size, recommend the real proposal (once authorized to proceed) be split into its own
explicit sub-phases rather than one atomic slice, mirroring how every other Phase I extension in
this repo has been landed incrementally:

1. Circuit change + VK regen + verifier regen + fixture regen (self-contained within
   `integrity-zkp` + the generated `UltraPlonkVerifier.sol`, testable with `nargo test`/`make
   build` before touching any calling code).
2. `VerifierRegistry` pinning/rollout policy for the new verifier version — a real decision about
   whether the 7 already-registered agents get migrated, grandfathered on the old verifier
   indefinitely, or something else; this needs its own explicit go/no-go, not a default.
3. `integrity-sdk`/`integrity-cli` prover call-site updates + cross-package round-trip tests (this
   codebase's own stated discipline for SDK/CLI parity, since CLI doesn't import SDK and carries
   its own copy).

## Scope: out (regardless of how the eventual full proposal splits phases)

- Any change to the BCC wire-format binding itself — §30 already closed that; this proposal is
  strictly the ZK-proof-specific remaining half.
- Deployment of any regenerated verifier to Base Sepolia or anywhere else — a separate,
  later-gated decision, same standing rule as every other Phase I item.
- Migrating already-registered agents' existing attestations — out of scope per "What this does
  NOT close" above, unless the eventual VerifierRegistry-pinning decision (sub-phase 2) explicitly
  calls for it.

## Decision needed

1. **Authorize scoping to proceed to a full, phased proposal** — the sub-phase split above as a
   starting point, `chain_id`-only vs. `chain_id` + `verifying_contract` as an explicit choice to
   make in that proposal.
2. **Not yet** — stay at this sketch stage; this is the item most likely to warrant its own
   dedicated session rather than being folded into the same pass as the other five.
