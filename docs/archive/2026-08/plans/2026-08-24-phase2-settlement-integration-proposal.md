# Settlement integration (protocol fee split) — go/no-go proposal

**Status:** implemented locally after scoped authorization; awaiting commit/testnet sequencing.
Third and final named
workstream of whitepaper Phase II ("Metered IP" — Table 8: "ERC-6551 licence accounts with live
consumption ledgers; ATCP/IP intent format; **settlement integration**"). Follows the licence
account tracer bullet (`PRODUCTION_GAPS.md` §47) and the ATCP/IP signed-intent layer (§48).

## What the whitepaper actually specifies, and what it doesn't

**Eq (12), value conservation in settlement** (§4.4, quoted precisely): "For a participant set
$P$, balances $b(j)$, and a fee $\varphi$ routed to a declared recipient:
$\sum_{j \in P} \Delta b(j) + \varphi = 0$. Any transition failing (12) is either a mint, a burn,
or a leak, and is rejected unless a constraint explicitly authorises it." Table (lifecycle) step
6: "**Settle** — pay, split fee $\mu$, decrement $q$" — happening in the SAME transaction as the
gate and meter decrement, not a separate reconciliation (§8.3: "The fee split is settled
atomically within step 6 of the lifecycle").

**Eq (24)/(25), §8.3 (revenue and its allocation)** is a much larger claim than eq (12) alone:
$R = \sum_i V_{A2A,i}\mu_i \approx \mu\Phi$, $\mu = \mu_{core} + \mu_{ad}$ (protocol fee +
adapter-author fee, the latter requiring the adapter registry/market from §6 — not built, not in
scope for this repo at all yet), then allocated $R = \alpha R$ (stablecoin yield to ITK stakers) +
$\beta R$ (buy-back-and-burn) + $\gamma R$ (treasury/audits/insurance). **This is a full
tokenomics/staking system** — confirmed not to exist anywhere in this repo (`grep` for
`treasury`/`feeRecipient`/`buyback`/`stakers` across `contracts/src/` returns nothing live, only
NatSpec prose referencing the OLD prototype's fee-on-transfer design in `IntegrityToken.sol`,
which this rewrite deliberately does not carry forward).

**This proposal scopes ONLY eq (12)'s φ term** — a single flat protocol fee, atomically split at
settlement time, routed to one declared recipient address. It does NOT attempt eq (24)/(25)'s
staker-yield/buy-back-burn/treasury allocation, or the adapter-author fee share $\mu_{ad}$ (no
adapter registry exists to attribute a share to). That is real, separate, much larger future
scope, named here so it isn't silently conflated with what this slice actually builds.

## Scope: a single immutable fee split on the existing settlement path

**In scope:**
1. Two new immutable constructor parameters on `LicenceAccount`: `protocolFeeRecipient` (address)
   and `protocolFeeBps` (uint256, basis points of `royaltyDue`, NOT of `msg.value` — see design
   question 1). `protocolFeeBps == 0` is valid (no fee; every existing test's behavior is
   unaffected without this being a breaking change in spirit).
2. `_consume()` (the internal function both `consume()` and `consumeWithIntent()` already share)
   computes `feeAmount = royaltyDue * protocolFeeBps / 10_000`, sends it to
   `protocolFeeRecipient` via a native `call` **atomically within the same transaction** — if that
   transfer fails, the WHOLE `consume`/`consumeWithIntent` call reverts (matching eq 12: a
   transition where the fee leg fails is a leak, not representable). The remainder
   (`msg.value - feeAmount`) lands in the account's own balance exactly as today.
3. Constructor validation: if `protocolFeeBps > 0`, `protocolFeeRecipient` must not be
   `address(0)` (a nonzero fee with no recipient is a burn, i.e. exactly the failure mode eq (12)
   names).

**Explicitly deferred:**
- $\mu_{ad}$ / adapter-author revenue share (§6, §8.3) — no adapter registry exists.
- Eq (25)'s $\alpha/\beta/\gamma$ allocation to stakers/buy-back/treasury — needs a real staking
  system this repo does not have. `protocolFeeRecipient` here is a single plain address; what it
  does with received funds is entirely outside this contract's concern, exactly like
  `IntegrityKernel`'s existing budget checks don't care what a recipient does with released funds.
- Per-adapter or per-licence-term fee-rate variation — one flat `protocolFeeBps` per licence
  account instance, set once at construction, matching every other licence term's
  immutable-at-construction pattern in this slice.
- Any fee on the transfer-drain guard's `armTransfer`/`disarmTransfer`/`execute` withdrawal path
  — the fee applies only at the consumption/royalty-payment moment (eq 12's settlement step),
  not to the licensee later withdrawing their own accrued balance.

## Design questions needing a decision before code

1. **Fee base: `royaltyDue` (the required amount) or `msg.value` (including any overpayment)?**
   `consume()`/`consumeWithIntent()` currently credit the account's FULL `msg.value` on
   overpayment, no refund. If the fee were taken as a percentage of `msg.value`, an overpaying
   caller would silently pay a larger absolute fee for the exact same units consumed — an
   unadvertised, caller-value-dependent side effect. **Recommend: base the fee on `royaltyDue`
   only** (the units × declared price), so the fee amount is fully determined by what was
   actually consumed, not by how much extra the caller happened to send; 100% of any overpayment
   still lands in the account's own balance, unchanged from today.
2. **What is `protocolFeeRecipient` for this tracer bullet?** No treasury/staking contract exists
   in this repo to point at. Options: (a) a plain placeholder EOA/multisig address supplied at
   deploy time (e.g. the existing `governance` address already in
   `deployments.baseSepolia.json`'s `protocolAddresses`, reused as a stand-in, disclosed as such);
   (b) defer this workstream entirely until a real fee-sink contract exists. **Recommend (a)** —
   matching how Phase I's kernel reference deployment used real, disclosed placeholder values
   (e.g. `trackedToken` pointed at a real but arbitrary ERC-20) rather than waiting for a fully
   mature system before proving the mechanism works.
3. **What `protocolFeeBps` value?** This is a real economic parameter, not an engineering
   decision — the whitepaper does not pin a specific $\mu$ value. **Recommend a small, clearly
   placeholder value (e.g. 100 bps = 1%)**, explicitly disclosed as illustrative, not a considered
   tokenomics decision — matching this slice's own "prove the mechanism, not the economics"
   posture. Needs your input either way since it's a real number that will appear on testnet.

## Process discipline (matching every prior workstream)

1. Strict red-to-green TDD, one failing Foundry test at a time.
2. Mutation-tested guards specifically for: fee computed correctly off `royaltyDue` not
   `msg.value`; fee-transfer failure reverts the whole settlement (no partial state change);
   constructor rejects `protocolFeeBps > 0` with a zero recipient; `protocolFeeBps == 0` behaves
   identically to the current no-fee contract (regression coverage against all 31+20 existing
   tests).
3. A concrete guarantee-statement NatSpec addition to `LicenceAccount.sol`, same register as the
   existing two sections.
4. `PRODUCTION_GAPS.md` updated with the next dated entry (§49).

## Acceptance criteria

- Real Foundry tests proving: a `consume()` call with `protocolFeeBps > 0` atomically splits the
  payment (fee recipient's balance increases by exactly `feeAmount`, account balance increases by
  exactly `msg.value - feeAmount`); the same holds through `consumeWithIntent()`; a fee-recipient
  `call` that reverts (e.g. a recipient contract with no `receive()`) reverts the WHOLE consume
  call, with zero state change (`consumedUnits` unchanged); `protocolFeeBps == 0` reproduces every
  existing test's exact numeric behavior; constructing with `protocolFeeBps > 0` and
  `protocolFeeRecipient == address(0)` reverts.
- A precise guarantee-statement NatSpec section, same register as the existing ones.

## Real risk, stated before any code exists

- **A fee-recipient `call` that reverts blocks ALL consumption on this licence**, not just the fee
  leg — this is the deliberate, eq-(12)-mandated behavior (no partial settlement), but it does
  mean a misconfigured or malicious `protocolFeeRecipient` (e.g. a contract that always reverts on
  receive) can fully deny service to a licence. No circuit-breaker or fee-bypass path is proposed
  here — disclosed as a real availability risk this slice accepts, matching Phase I's own
  "reentrancy guard blocks legitimate reentrant self-calls too" disclosure style.
- **This is real, on-testnet economic plumbing, however small** — unlike volume-cap/royalty/expiry
  (pure access-control logic), a live fee percentage and recipient address are genuinely
  economically meaningful even at illustrative values, and will be visible in
  `deployments.baseSepolia.json` once deployed. Worth being deliberate about, not just fast.

## Decision needed

1. **Authorize as scoped** — fee based on `royaltyDue`, atomic revert-on-fee-failure, needs your
   answer on the recipient address and bps value (design questions 2–3).
2. **Authorize with changes.**
3. **Not yet.**

This document does not authorize itself.

## Outcome

Implemented in `contracts/src/licence/LicenceAccount.sol` as the scoped eq (12) fee split:
`protocolFeeRecipient` and `protocolFeeBps` are immutable constructor terms; nonzero fee bps with
a zero recipient reverts; `protocolFeeBps == 0` preserves the prior no-fee behavior. `_consume()`
computes the fee from `royaltyDue` only, transfers it atomically to the recipient, and reverts the
whole consumption path if that transfer fails.

Added `contracts/test/licence/ProtocolFeeSettlement.t.sol` covering direct `consume()`,
`consumeWithIntent()`, overpayment, zero-fee behavior, constructor validation, and recipient
failure rollback. `LicenceAccount.sol`'s own guarantee-statement NatSpec now states the precise
settlement claim and the tokenomics pieces still not implemented.
