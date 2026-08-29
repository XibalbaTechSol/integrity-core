# ATCP/IP signed-intent format for `LicenceAccount.consume()` — go/no-go proposal

**Status:** proposal only. Nothing in this document is authorized. Second workstream of
whitepaper Phase II (Table 8), following the licence-account tracer bullet
(`PRODUCTION_GAPS.md` §47, `docs/plans/2026-08-24-phase2-licence-account-tracer-bullet-proposal.md`).

## What the whitepaper actually specifies (§7.1, Table, quoted precisely)

The 8-step transaction lifecycle, steps 1-4 relevant here:

| # | Step | Where |
|---|---|---|
| 1 | **Discover** — resolve the configured Integrity identity profile, read terms | off-chain, cacheable |
| 2 | **Intend** — sign scoped ATCP/IP request (session key, not root key) | off-chain, cacheable |
| 3 | **Transduce** — adapter emits **C** | off-chain, cacheable, deterministic |
| 4 | **Validate** — signature, session, domain $d^\star$ | **ERC-4337 validation phase (type-1 validator)** |
| 5 | **Gate** — `preCheck`: is $V=1$? | execution phase begins |

Step 4 is explicit: signature/session/domain validation happens in the **ERC-4337 validation
phase**, via a "type-1 validator." That is a specific, larger architectural claim — it means the
whitepaper's own target design is a licence account that is *itself* an ERC-4337 smart account
with a modular validator, receiving `UserOperation`s through a bundler/EntryPoint, exactly like
`IntegrityAccount` already is for Phase I's agent accounts.

**This slice's own prior proposal already flagged this tension and deferred it on purpose:**
"ERC-6551 token-bound accounts are a different standard — ownership resolves via `ownerOf` on an
external NFT, not via a signer or EntryPoint... Combining both correctly... is real, non-trivial
engineering" (`phase2-licence-account-tracer-bullet-proposal.md`, "Design decision" section).
That deferral is still correct and this proposal does not reopen it — full EntryPoint/ERC-4337
integration for `LicenceAccount` is **out of scope here**, same as it was for the first slice.

## What this workstream actually builds instead: a scoped intent-signature layer, not full ERC-4337

Consume calls today (`LicenceAccount.consume(uint256 units)`) are gated only by
`msg.sender == owner()` — the NFT holder must call directly. That means the *caller* must hold
the root NFT-controlling key for every single consumption call. Steps 2 and 4 of the lifecycle
name two things this tracer-bullet slice does not yet have:

1. **A session key, distinct from the root key that controls the NFT.** The owner should be able
   to authorize a scoped, revocable key (e.g. held by an automated agent process) to sign
   consumption intents without ever exposing the root key.
2. **A signed, scoped intent object** — the whitepaper's "ATCP/IP request" — that a *relayer* (not
   necessarily the owner or the session-key holder) can submit on-chain, with the account itself
   verifying the signature, the session key's current authorization, and a domain binding, before
   treating the call as authorized.

This is directly analogous to what `IntegrityAccount`'s `SignerECDSA`/`validateUserOp` already
does for Phase I (`_rawSignatureValidation` against a `PackedUserOperation` hash) — but built as a
**standalone EIP-712 signature-verification layer on `LicenceAccount` itself**, not routed through
a real EntryPoint/UserOperation, matching this slice's own "prove the narrow mechanism first"
precedent rather than building the full ERC-4337 stack a second time for a different account
standard.

## Scope: exactly what changes on `LicenceAccount`

**In scope:**
1. **Session key registration.** `authorizeSessionKey(address key, uint256 expiry)` /
   `revokeSessionKey(address key)`, both owner-gated (dynamic `ownerOf` check, matching every
   other owner-gated function on this contract).
2. **EIP-712 typed intent struct**, something in the shape of:
   ```
   ConsumeIntent {
       address account;      // this LicenceAccount — domain/replay binding, eq the whitepaper's d*
       uint256 units;
       uint256 nonce;
       uint256 expiry;
   }
   ```
   using OpenZeppelin's vendored `EIP712`/`Nonces` (both already in `node_modules`, no new
   dependency) rather than hand-rolling domain separation, matching this repo's own precedent of
   using vetted libraries for signature-adjacent primitives (`ERC4337Utils` in Phase I).
3. **`consumeWithIntent(ConsumeIntent calldata intent, bytes calldata signature)`** — a new
   function alongside (not replacing) `consume()`. Verifies: the signature recovers to either the
   current owner OR a currently-unexpired, non-revoked session key; `intent.account == address(this)`
   (domain binding — the "domain $d^\star$" the whitepaper names, preventing an intent signed for
   one licence account being replayed against another); `intent.nonce` matches
   `Nonces.useNonce(signer)`; `block.timestamp <= intent.expiry`. On success, falls through to the
   same volume-cap/royalty/expiry checks `consume()` already enforces — this is additive
   authorization, not a parallel or weaker path.
4. **`consume()` itself is unchanged** — direct-owner-call remains valid, matching how Phase I kept
   both a `vm.prank`-reachable "self" path and the real EntryPoint path simultaneously rather than
   removing the simpler one.

**Explicitly deferred, not attempted:**
- Real ERC-4337 `UserOperation`/EntryPoint routing (whitepaper's literal "type-1 validator" in the
  "ERC-4337 validation phase") — this remains the same kernel-hybrid undertaking the first slice's
  proposal already named and declined to build yet.
- Adapter transduction (step 3 — off-chain, no on-chain surface to build here).
- A real relayer/bundler service — this workstream proves the account-side verification logic
  only; something has to actually *submit* `consumeWithIntent` transactions, but building that
  submission service is separate infra, not a contract change.
- Paymaster/gas-sponsorship (§7.2) — explicitly Phase II/III-adjacent infra this slice does not
  touch.

## Design questions needing a decision before code

1. **Should `consumeWithIntent` be callable by ANY relayer**, as long as the signature checks
   out (the whitepaper's own intent: the signer authorizes the action, not the caller) — or should
   it still be `msg.sender`-gated to the owner or an approved relayer address? The whitepaper's
   model implies open relaying (that's the entire point of a signed, replayable-by-anyone
   intent) — **recommend: no `msg.sender` gate**, only the signature/session/domain/nonce checks
   gate it.
2. **Session key scope: all-or-nothing, or should a session key be boundable to a max units/max
   spend** (an even narrower delegation than the root key)? The whitepaper doesn't specify this at
   this granularity for the licence-account context specifically. **Recommend: defer per-key
   caps to a later slice** — a session key that can sign any `ConsumeIntent` up to what the
   licence's own volume cap/expiry already bound is a real, useful, and much simpler v1;
   per-session-key sub-limits are additive scope that doesn't change the shape of what's built
   now.
3. **Nonce scheme: per-signer sequential (OZ `Nonces`, one counter per address) or per-intent
   arbitrary (a used-hash mapping, allowing out-of-order/concurrent intents)?** Sequential nonces
   are simpler and match Phase I's own EntryPoint-adjacent precedent, but block a licensee from
   having two `consumeWithIntent` calls in flight concurrently (the second must wait for the first
   to land). **Recommend: sequential (OZ `Nonces`)** for this slice — concurrent-intent support is
   real added complexity with no concrete driving use case yet, and can be swapped later without
   changing the external intent shape (nonce is already a struct field either way).

## Process discipline (matching every prior workstream)

1. Dependency inventory confirmed above — OZ `EIP712`/`Nonces` already vendored, no new package.
2. Strict red-to-green TDD, one failing Foundry test at a time.
3. Mutation-tested guards specifically for: signature-recovery correctness (wrong key rejected),
   session-key expiry enforcement, session-key revocation enforcement, domain-binding (an intent
   signed for account A must not validate against account B), and nonce replay-protection.
4. A concrete guarantee-statement NatSpec addition to `LicenceAccount.sol`, matching the pattern
   already used for the first slice's guarantees.
5. `PRODUCTION_GAPS.md` updated with the next dated entry (§48).

## Acceptance criteria

- Real Foundry tests proving: a validly-signed intent from the owner succeeds; a validly-signed
  intent from an authorized, unexpired session key succeeds; an intent signed by a revoked or
  expired session key reverts; an intent with a reused nonce reverts; an intent signed for a
  different `account` (domain mismatch) reverts even if the signature itself is otherwise valid;
  an intent past its own `expiry` reverts; any relayer (not just the owner) can successfully
  submit a validly-signed intent on the signer's behalf.
- `consume()`'s existing direct-call path is untouched and still passes all 25 existing tests.
- A precise guarantee-statement NatSpec section, same register as the existing one.

## Real risk, stated before any code exists

- **This still does not implement the whitepaper's literal "ERC-4337 validation phase" claim** —
  it's a standalone EIP-712 layer, a deliberately smaller and different mechanism that achieves
  the same *practical* goal (root-key-free scoped authorization) without the full account-
  abstraction stack. That gap should stay disclosed, not implied closed, exactly like the first
  slice's own "does NOT claim ERC-4337 validation" disclosure.
- **Open relaying means gas cost falls on whoever submits the transaction**, not the signer — with
  no paymaster (explicitly out of scope), *someone* pays real ETH to submit `consumeWithIntent`.
  That's fine for a tracer bullet (the existing `consume()` path already assumes the owner pays
  gas directly) but is worth stating plainly rather than leaving implicit.

## Decision needed

1. **Authorize as scoped** — session keys + EIP-712 `ConsumeIntent` + open relaying, sequential
   nonces, no per-key sub-limits, no EntryPoint routing.
2. **Authorize with changes** — different answer to one or more of the three design questions
   above.
3. **Not yet.**

This document does not authorize itself.

## Outcome (2026-08-24)

Authorized as scoped ("yes, go ahead with all three as scoped"). Built exactly as proposed:
`authorizeSessionKey`/`revokeSessionKey`, the EIP-712 `ConsumeIntent` struct, and
`consumeWithIntent()` with open relaying and sequential OZ `Nonces`, added directly to
`contracts/src/licence/LicenceAccount.sol`. 20 new tests in
`contracts/test/licence/ConsumeWithIntent.t.sol`; 381/381 passing across the full `contracts/`
suite. All four new guards (domain binding, intent expiry, signer authorization, session-key
past-expiry rejection) mutation-tested per this doc's own process-discipline section. Full
detail, including a real via_ir/solc miscompilation found and worked around while writing the
boundary tests (not silently patched over — disclosed as a repo-wide open gap): `PRODUCTION_GAPS.md`
§48.

Neither of this document's two disclosed risks were closed, by design: this remains a standalone
EIP-712 layer, not the whitepaper's literal ERC-4337 validation-phase claim; and open relaying
still means whoever submits `consumeWithIntent` pays real gas, with no paymaster built.
Settlement integration (Table 8's third named Phase II piece) remains the next unbuilt workstream.
