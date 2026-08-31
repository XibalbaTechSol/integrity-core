# Phase II live consumption evidence — 2026-08-28

Status: verified on Base Sepolia. This is testnet evidence, not production readiness or external
adoption evidence.

## Deployment bindings

- Chain ID: `84532`
- LicenceToken: `0x9d6d2F3F7CE910DaE6E66E36e5c6437A985d4dA4`
- LicenceAccount implementation: `0x168b31620f535ff6B33Fd4Abff92b1427eb55beE`
- ERC-6551 token-bound account: `0x62526e8B67F04A5ea3F09Bd48C171A7e1dBA7373`
- AdapterRegistry: `0x41aCE438fA1550D095d4DC4563D07c8252522105`
- SpendBudgetAdapter: `0xc7F7E68ABFe7B8Cb2162b867c3Db18785Ee7161f`
- LicencePaymaster: `0xf50f52B64fD0ED724c5cE8E706bD9784eDadeD68`
- LicenceEconomy: `0x8E0E480275c030542108eb38d24cd24d985add97`
- Owner/funder: `0x7530bd7Cb142C50d5cC742EdF02263f368e89E2f`

The read-only `VerifyLicenceReference.s.sol` verifier passed before this transaction, confirming
non-empty bytecode and the account, adapter, paymaster, and economy bindings. The deployment was
broadcast by `DeployLicenceReference.s.sol`; its receipt records are under
`contracts/broadcast/DeployLicenceReference.s.sol/84532/run-latest.json`.

## Consumption receipt

- Transaction: `0x1573d80423209da211730cbcc3728dcdf8e211b10885bff9fc0ff71a1eee3112`
- Block: `0x2bf71aa` (`46100906`)
- Block hash: `0xf0de528ef2f07bb9ba878c7bcf234408970202d85974f5b955567d6811fea08a`
- Receipt status: `0x1`
- Transaction type: `0x2`
- Gas used: `0x323e2` (`205,794`)
- Effective gas price: `0x5b8d80` (`6,000,000` wei)
- Call: `consume(1)` with `100000000000000` wei

## Reconciled post-state

- `consumedUnits`: `0 -> 1`
- Account balance: `0 -> 99000000000000` wei
- Adapter cumulative spend for owner: `0 -> 100000000000000` wei
- Economy balance: `1000000000000` wei
- Economy adapter-author reserve: `200000000000` wei
- Economy treasury reserve: `600000000000` wei
- Economy buyback reserve: `200000000000` wei
- Protocol fee: `1000000000000` wei (1% of the `100000000000000` wei royalty)

The three receipt logs include the economy `FeeReceived` event, the account
`ProtocolFeeSettled` event, and the account `Consumed` event. The deltas reconcile exactly:
`99000000000000 + 1000000000000 = 100000000000000`, and the economy allocations sum to the
fee (`200000000000 + 600000000000 + 200000000000 = 1000000000000`).

## Caveats

The paymaster deposit is still zero, so no sponsored UserOperation has been demonstrated. The
transaction is from the protocol funder and therefore does not satisfy the external-counterparty
adoption gate. Independent audit and production governance remain open.
