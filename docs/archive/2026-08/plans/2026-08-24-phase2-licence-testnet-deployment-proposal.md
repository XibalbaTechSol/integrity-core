# Phase II reference deployment to Base Sepolia — go/no-go proposal

**Status:** proposal only. Nothing in this document is authorized. Testnet deployment of the
Phase II licence-account slice, mirroring Phase I's own testnet deployment workstream
(`PRODUCTION_GAPS.md` §44, §46, `docs/plans/2026-08-24-phase1-testnet-deployment-proposal.md`).

## Dependency: sequenced after settlement integration, not parallel to it

This proposal assumes `docs/plans/2026-08-24-phase2-settlement-integration-proposal.md` (§49) is
authorized and built FIRST. Deploying now (volume cap + royalty + expiry + transfer-drain guard +
ATCP/IP intents only, no fee split) and then redeploying once settlement integration lands would
repeat Phase I's own §44→§46 supersession churn (a real, disclosed, but avoidable repeat of the
same pattern) for no benefit — there is no user of a Phase II testnet reference yet, so there is no
cost to sequencing correctly instead. **If settlement integration is declined or deferred, this
deployment should proceed without it** (a `protocolFeeBps` of 0 is a fully valid, real
configuration per that proposal's own scope) — this is a preference for order, not a hard block.

## What gets deployed

1. **`LicenceToken`** (`contracts/src/licence/LicenceToken.sol`) — a fresh instance, owner-gated
   mint, exactly as tested.
2. **One `LicenceAccount` implementation contract** — a concrete reference licence, with real
   (illustrative, disclosed) terms: e.g. `volumeCapTotal = 1000`, `royaltyPricePerUnitWei` a small
   real testnet-ETH amount, a real `licenceStartTime`/`licenceEndTime` window, and (if §49 lands
   first) a real `protocolFeeRecipient`/`protocolFeeBps`. These are deploy-time parameters, not
   contract logic — no code changes needed here beyond what §47/§48/§49 already build.
3. **A minted reference licence NFT** (`LicenceToken.mint(...)`) — needs a real recipient address;
   the deploy script's own EOA (the funder wallet already used for Phase I's reference deployment)
   is the simplest disclosed choice, matching Phase I's own reference-instance pattern.
4. **A real ERC-6551 token-bound account, created via the LIVE canonical registry** — calling
   `IERC6551Registry.createAccount(implementation, salt, chainId, address(licenceToken), tokenId)`
   against the real, already-confirmed-live registry at
   `0x000000006551c19487814612e58FE06813775758`, NOT merely deploying the implementation and
   stopping there. This is deliberate and new relative to Phase I's pattern: Phase I's reference
   `IntegrityAccount`/`IntegrityKernel` were deployed directly (`new IntegrityAccount(...)`)
   because there is no external registry in the ERC-7579/ERC-4337 world playing the role ERC-6551's
   registry plays here. Deploying via the real registry on testnet is what actually proves the
   registry-integration finding from `Erc6551RegistryIntegration.t.sol` (a Base Sepolia FORK test)
   holds against the real, un-forked network too — closing the gap between "proven on a fork" and
   "proven live."

## Design questions needing a decision before executing

1. **Reference licence terms (volume cap, royalty price, duration) — real placeholder numbers
   needed.** Recommend mirroring Phase I's own disclosed-placeholder posture: small, clearly
   illustrative values (e.g. `volumeCapTotal = 1000` units, `royaltyPricePerUnitWei = 0.0001
   ether`, a 30-day window from deploy time) — explicitly NOT a considered commercial licence,
   same as Phase I's reference kernel's budget values. Needs your confirmation or preferred
   numbers.
2. **Salt for `createAccount`** — ERC-6551 salts let the same `(implementation, tokenContract,
   tokenId)` triple produce multiple independent TBAs. For a single reference instance,
   `bytes32(0)` is the simplest, most legible choice (matching how
   `Erc6551RegistryIntegration.t.sol`'s tests already use it) — no reason to complicate this for
   a tracer-bullet reference deployment. Flagging only because it's a real, visible-on-chain
   choice, not because there's a real decision to make.
3. **Where the reference NFT's owner key lives** — the deploy script's funder EOA, the same
   already-funded wallet used for Phase I's reference deployment (per `FAUCET_INFO.md`), or a
   fresh dedicated address? **Recommend reusing the existing funder wallet** — no new key
   management surface for a reference instance nobody but this repo's own tooling will ever call
   `consume()` against.

## Process discipline (matching Phase I's own testnet deployment workstream exactly)

1. **Local anvil dry run FIRST** — deploy the full sequence (`LicenceToken` → `LicenceAccount`
   implementation → mint → real registry `createAccount`) against a local anvil fork BEFORE
   touching Base Sepolia, exactly as Phase I's `DeployKernelReference.s.sol` caught a real
   CREATE-nonce off-by-one and a JSON dotted-key bug this way. The ERC-6551 registry is NOT
   deployed on a fresh local anvil by default (it's a real testnet/mainnet singleton) — the dry
   run will need either a local fork of Base Sepolia (`anvil --fork-url`) so the real registry
   bytecode is present, or a locally-deployed copy of the registry for the dry run only (never for
   the real deployment, which must use the real canonical address). Recommend forking, since it
   also exercises the real registry bytecode rather than a hand-deployed stand-in.
2. **Simulation-vs-broadcast discipline** — `PRODUCTION_GAPS.md` already discloses (§44's
   incident) that a `forge script` SIMULATION (no `--broadcast`) still executes `vm.writeJson` and
   silently overwrote real deployment records once this session. This new deploy script must be
   written and reviewed with that specific gap in mind — verified via a real anvil dry run before
   any simulation against the live Base Sepolia RPC is run at all, and the resulting JSON diff
   inspected before any `--broadcast`.
3. **A new, additive `deployments.baseSepolia.json` key** —
   `experimentalPhase2LicenceReference`, following the exact `experimentalPhase1Reference`
   convention: implementation address, proxy (TBA) address, `LicenceToken` address, the minted
   `tokenId`, `deployedFromCommit`, and an explicit disclosure string (experimental, not audited,
   illustrative terms only, not a real commercial licence).
4. **A dated `PRODUCTION_GAPS.md` entry** (next in sequence) recording exactly what got deployed,
   at what addresses, real gas costs, and — critically — that this reference instance's terms are
   illustrative, not a real licensing offer.

## Acceptance criteria

- `cast call` against the real, live `LicenceAccount` proxy address confirming `token()` resolves
  to the correct `(chainId, LicenceToken address, tokenId)`, `owner()` resolves to the minted
  NFT's holder, and (if a test consumption is authorized separately — see below) `consume()`
  behaves identically to the Foundry test suite's proven behavior.
- The registry's `account(...)` prediction matches the address `createAccount(...)` actually
  returned, checked live via `cast call`, not merely re-trusted from the fork-test result.
- `deployments.baseSepolia.json` updated additively (new key, no existing key overwritten).

## Real risk, stated before any code exists

- **This is a REAL, broadcast, gas-costing transaction sequence against Base Sepolia** — same
  category of action as Phase I's kernel deployment, requiring the same explicit go-ahead before
  any `--broadcast` flag is used, not implied by this proposal's own authorization.
- **No real consumption/settlement transaction is proposed as part of THIS deployment** — deploying
  the reference instance proves the deployment mechanics work; actually calling `consume()` against
  it with real testnet ETH is a separate, later action this document does not request authorization
  for. If you want a live end-to-end demonstration (mint → consume → verify balance), that should
  be its own explicit ask.

## Decision needed

1. **Authorize as scoped**, sequenced after §49 (settlement integration) — needs your input on
   design questions 1–3 (reference terms, salt, key custody) before the deploy script is written.
2. **Authorize now, decoupled from §49** — deploy without the fee split, accept a future
   supersession if settlement integration lands later (repeats Phase I's §44→§46 pattern).
3. **Not yet.**

This document does not authorize itself.
