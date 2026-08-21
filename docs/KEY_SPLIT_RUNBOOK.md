# Key-split runbook (§5.4 / MAINNET_READINESS P0-1)

Status: `[OPEN]` on testnet. Required before any mainnet `SovereignAgent` proxy.
Decided sequence (consequence order): distinct keys → process-held signers → constrain $ITK$ → then multisig/timelock.

Today `deployments.baseSepolia.json` `protocolAddresses` maps
`arbitrator`, `disputer`, `funderWallet`, `governance`, `oracleSigner`, `resolverSigner`
to one EOA (`0x67bA5D723E1F5517afF7eb980E2f73a9e17aD556`), which also holds
`MINTER_ROLE` and `DEFAULT_ADMIN_ROLE`. That is an accepted **testnet** posture.
It is non-conformant as a **mainnet** posture.

Do not paste private keys into chat, git, or CI logs. Use a hardware wallet or a
secret manager. Fill addresses into `deployments/<network>.json` only.

## Roles (eight seats, eight keys)

| Seat | Holds | Must not also hold |
| --- | --- | --- |
| `arbitrator` | Dispute first-look | `MINTER_ROLE`, upgrade admin |
| `disputer` | Open a dispute | `oracleSigner`, `resolverSigner` |
| `funderWallet` | Testnet gas / seeding | Any protocol admin role on mainnet |
| `governance` | Parameter changes after step 4 | Live oracle signing |
| `oracleSigner` | AIS / score updates (`ORACLE_ROLE`) | `DEFAULT_ADMIN_ROLE`, `MINTER_ROLE` |
| `resolverSigner` | Dispute resolution attestations | `oracleSigner` |
| `MINTER_ROLE` | $ITK$ mint (until supply is fixed) | Upgrade admin |
| `DEFAULT_ADMIN_ROLE` | Role grants on protocol contracts | `oracleSigner` |

`SovereignAgent` upgrade authority (beacon owner or equivalent), if a proxy is used,
is a ninth seat and MUST be the step-4 Safe, never a single EOA.

## Step 1 — Distinct keys (do this first, even on Sepolia)

1. Create eight empty addresses (no shared seed phrase across seats).
2. Record them in a private operator sheet: seat, address, custody tool, backup location.
3. Grant the new address the role, **then** revoke the old EOA. Never revoke first.
4. Update `protocolAddresses` in the deployment JSON in the same PR as the txs.
5. Pass criterion: `cast call` / `hasRole` shows no two named seats share an address.

Related: `contracts/script/RotateOperatorKeyGrant.s.sol` and `docs/signer-role-rotation-2026-08.md`.

## Step 2 — Process-held signers

`oracleSigner` and `resolverSigner` MUST be keys held by the oracle / BCC middleware
processes, not a human wallet.

1. Generate the keys on the host (or KMS) that already runs `integrity-oracle`.
2. Restrict filesystem mode `0600`; do not check them into `.env` committed to git.
3. Grant `ORACLE_ROLE` / resolver role to those addresses on each agent or shared registry.
4. Confirm a score update tx is signed by the process key, not the funder EOA.

## Step 3 — Constrain $ITK$

Until minting is bounded, "governance owns upgrades" is the funder EOA with extra steps.

Pick one and write it into the deployment notes:

- **Fixed supply:** cap or burn `MINTER_ROLE` after initial allocation, or
- **Governance-only mint:** `MINTER_ROLE` held only by the step-4 Safe.

Do not claim decentralized control before this lands.

## Step 4 — Safe / timelock (last)

Only after steps 1–3:

1. Deploy a 2-of-3 (or stricter) Safe as `governance` and `DEFAULT_ADMIN_ROLE`.
2. Move any `SovereignAgent` upgrade authority to that Safe.
3. Optional: timelock on upgrades. Emergency pause is **not** decided here (§5.4).

A `SovereignAgent` proxy MUST NOT ship to mainnet before steps 1–4.

## Checklist (copy into the mainnet deploy PR)

- [ ] Eight distinct addresses recorded (no shared EOA).
- [ ] `oracleSigner` / `resolverSigner` are process keys.
- [ ] $ITK$ mint path is fixed-supply or Safe-only.
- [ ] Safe holds governance + default admin + upgrade authority.
- [ ] Old concentrated EOA has zero protocol roles on the target network.
- [ ] `deployments/<network>.json` matches on-chain `hasRole` reads.
