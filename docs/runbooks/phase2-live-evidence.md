# Phase II live licence evidence

This runbook records the final Phase II reference-account validation sequence. The
reference account is experimental and its terms are illustrative; this procedure
does not create or represent a commercial licence.

## Preconditions

1. Confirm the target is the latest deployment record under
   `experimentalPhase2LicenceReference` in `deployments.baseSepolia.json`.
2. Run `VerifyLicenceReference.s.sol` against the same RPC and retain its successful output;
   this confirms the current hook/registry/paymaster/economy bindings.
3. Use a funded `FUNDER_PRIVATE_KEY` whose address is the current ERC-721 owner.
4. Review the transaction cost and authorize spending one unit of Base Sepolia ETH.

## Deployment

Run a forked Anvil dry run first:

```sh
anvil --fork-url "$BASE_SEPOLIA_RPC_URL"
forge script script/DeployLicenceReference.s.sol --rpc-url http://127.0.0.1:8545
```

The dry-run script does not write the deployment record unless
`PHASE2_WRITE_DEPLOYMENT_RECORD=true` is explicitly set. Inspect the simulated output and do not
broadcast until the transaction sequence is approved:

```sh
GIT_COMMIT_SHA="$(git rev-parse HEAD)" \
forge script script/DeployLicenceReference.s.sol \
  --rpc-url base_sepolia --broadcast
```

The deployment script creates a fresh `LicenceToken`, implementation, NFT, and
canonical ERC-6551 token-bound account. It never replaces the existing singleton
or Phase I reference keys.

## Live consumption and settlement

After deployment, execute exactly one owner-authorized consumption:

```sh
GIT_COMMIT_SHA="$(git rev-parse HEAD)" \
forge script script/DemoLicenceConsumption.s.sol \
  --rpc-url base_sepolia --broadcast
```

`DemoLicenceConsumption.s.sol` refuses a missing, expired, inactive, exhausted,
or incorrectly-owned account. It verifies the consumed-unit increment and the
protocol-fee balance delta when the fee recipient is not the submitting signer.
Capture the complete forge output, transaction hash, receipt, and post-state
reads in the dated audit ledger. A successful script run is live testnet
evidence only; it is not production or external-adoption evidence.

## Remaining Phase II gates

- The account-side ERC-4337 path and allowlisted paymaster are implemented locally, but no live
  bundler/paymaster UserOperation has been captured; the paymaster must be funded explicitly.
- The broader economy is now deployed as `LicenceEconomy`, but stablecoin yield, DEX/oracle-backed
  buyback, and production multi-party governance remain open. The six additional terms are
  implemented by the opt-in `LicenceTermsPolicy` hook and typed consumption paths, not by the
  default unconfigured account.
- External-counterparty licensing volume must be measured independently before
  the Phase II-to-III adoption gate can be claimed.
- Independent audit, bytecode-source verification, monitoring, rollback, and production parameter
  governance remain required before production use.

## Deployment verification and operations

After broadcasting `DeployLicenceReference.s.sol`, run the read-only verifier against the same
RPC and archive its complete output with the broadcast receipt files:

```bash
cd contracts
forge script script/VerifyLicenceReference.s.sol --rpc-url base_sepolia
```

The verifier intentionally refuses the superseded deployment record, checks non-empty bytecode,
and cross-checks the ERC-6551 account, registry adapter, canonical EntryPoint, paymaster
allowlist, and economy attribution bindings. A successful verifier run is deployment evidence,
not an independent audit.

For monitoring, poll these read-only values at least once per block during the evidence window:
`consumedUnits`, `volumeCapTotal`, `licenceEndTime`, `registryAdapter.cumulativeSpentWei(owner)`,
`LicencePaymaster.getDeposit()`, `LicenceEconomy.treasuryReserve()`, and
`LicenceEconomy.buybackReserve()`. Alert on any failed transaction, cap exhaustion, expiry,
adapter cumulative-budget approach, paymaster deposit below the sponsorship budget, or economy
reserve mismatch against the `FeeReceived` event stream.

Emergency rollback is containment, not deletion: stop the relayer, call
`LicencePaymaster.setSponsoredAccount(account, false)`, and stop routing new licences to the
economy. Do not transfer the NFT or withdraw reserves until receipts and balances have been
captured. The account's immutable volume/price/expiry terms cannot be edited in place; a bad
reference deployment is retired and replaced, with its address kept in the audit ledger.

Production parameter changes require multisig ownership, a recorded proposal, the economy's
two-day fee-share delay, deployment-record update, verifier output, and an independent review.
