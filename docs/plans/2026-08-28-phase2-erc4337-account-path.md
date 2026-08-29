# Phase II ERC-4337 account path

**Status:** account-side validation implemented locally; live EntryPoint/bundler and paymaster
validation remain open.

`LicenceAccount` now implements the canonical ERC-4337 v0.9 `IAccount` surface in addition to
its ERC-6551 interface. `validateUserOp()` accepts only the canonical EntryPoint, verifies an
owner or currently authorized session-key signature over `userOpHash`, pays missing account
prefund, and stores a one-transaction authorization bound to the exact `execute()` calldata.

Owner-signed UserOperations retain the existing ERC-6551 CALL surface. Session-key UserOperations
are restricted to `execute(address(this), royalty, abi.encodeCall(consume, (units)), 0)`. The
nested self-call lets the EntryPoint-driven account execution transfer the account's own balance
as the royalty payment while preserving `consume()`'s existing checks and settlement path.

## Evidence

`contracts/test/licence/LicenceAccount4337.t.sol` covers owner validation and execution, session
key restriction, invalid signatures, and byte-identical call-data binding. The focused suite
passes 4/4; the full contracts suite passes 458/458 after the subsequent account, paymaster,
typed-term, and economy changes.

## Still open

- `LicencePaymaster` exists as allowlisted sponsorship plumbing, but it is not funded or proven
  through a live sponsored UserOperation.
- No bundler/client integration or live EntryPoint transaction has been captured.
- The account uses the OpenZeppelin-pinned canonical v0.9 EntryPoint address; other EntryPoint
  versions require a separately versioned deployment.
- This path does not implement the broader licence economy or external adoption gate. The opt-in
  typed-term policy and shared delegation read model are documented separately in
  `LicenceTermsPolicy.sol` and `ILicenceDelegationView.sol`.

## Sponsorship

`contracts/src/licence/LicencePaymaster.sol` adds an owner-funded paymaster for
the same canonical EntryPoint. It requires an explicit sender allowlist and a
per-UserOperation maximum-cost bound, and exposes deposit/withdrawal operations
for the EntryPoint deposit. `contracts/test/licence/LicencePaymaster.t.sol`
covers allowlisting, cost rejection, and EntryPoint-only enforcement.

The paymaster is included in `DeployLicenceReference.s.sol` and the reference
token-bound account is allowlisted during deployment. It is not automatically
funded; funding and a live sponsored UserOperation remain explicit operator
actions.
