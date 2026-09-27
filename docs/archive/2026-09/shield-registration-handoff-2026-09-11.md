# Shield registration handoff — 2026-09-11

## Current state

- Replacement DID: `did:integrity:b3324032b6248bec2b61b8d3ccb46df708680aab6c57762e3303e14437a861fb`
- Replacement agent wallet/controller: `0xcA9b9d1131041eADDcE9616AFef993F7E5e05E74`
- Agent wallet balance observed: approximately `0.04709 ETH` on Base Sepolia.
- SovereignAgent deployed: `0xB3521d8daE3a2932909AD5D4f9060ABE1ba62004`
- StateAnchor deployed: `0xae36df19bE862Ba6aA60a991d3827066f6e35400`
- Registration is **not complete**; the registry record has not been confirmed for the replacement DID.

## Blocking condition

The CLI was run with `0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266`, which has no `IntegrityToken.MINTER_ROLE`. The revert was OpenZeppelin `AccessControlUnauthorizedAccount` (selector `0xe2517d3f`). Additional ETH cannot fix a missing role.

The configured account `0x67bA5D723E1F5517afF7eb980E2f73a9e17aD556` also lacks `MINTER_ROLE`. The authorized minter observed on Base Sepolia is `0x7530bd7Cb142C50d5cC742EdF02263f368e89E2f`.

## Resume procedure

1. Fund the authorized minter with a small Base Sepolia ETH reserve, if needed; do not drain the agent wallet.
2. Rerun `scripts/register_shield_with_funder.sh`.
3. Enter the private key that derives to `0x7530…e89E2f`; keep it local and never paste it into chat or source control.
4. Use the same agent-wallet password so the existing `shield-replacement.wallet.json` is reused.
5. Confirm the CLI reuses the two deployed contracts, mints the ITK bond, grants `ANCHOR_ROLE`, anchors the root, and completes `registerPrimitives`.
6. Save the resulting transaction hash and configure Cortex with it using `scripts/configure_core_sync.sh`.

## Security notes

- A credential was pasted into the chat during troubleshooting. Treat it as compromised; do not use it for production funds or roles. Rotate/revoke it and move funds if it was real.
- Never put raw private keys in command arguments, committed files, or support messages. Prefer encrypted keystores or a hardware wallet.
- The historical `0xB583…` identity belongs to local chain `31337`; it is not evidence of the current Base Sepolia controller.

