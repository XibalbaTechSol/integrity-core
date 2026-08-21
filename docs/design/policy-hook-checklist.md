# Policy hook and key-custody checklist

Informative. Normative requirements live in `docs/SPEC.md` §5.3 and §5.4.

## Before merging `feat/role-split-policy-hooks`

- [ ] Restore the full `SPEC.md` from `main` and apply only the §5.3 / §5.4 insert plus the two §14 status-row edits. Do not ship the condensed rewrite.
- [ ] `forge test --match-contract PolicyHookInvariantsTest`
- [ ] `forge test --match-contract StateAnchorTest`
- [ ] `forge test --match-contract SovereignAgentTest`
- [ ] Confirm zero-address policy remains the disclosed testnet posture and does not break existing tests.

## Policy configuration

| Contract | Setter | Who may call | Mainnet requirement |
|---|---|---|---|
| `StateAnchor` | `setAnchorPolicy` | `DEFAULT_ADMIN_ROLE` | Non-zero `IAnchorPolicy` before production anchors |
| `SovereignAgent` | `setExecutionPolicy` | controller (`DEFAULT_ADMIN_ROLE`) | Non-zero `IExecutionPolicy` on any value-moving path |

A policy that returns `false` or reverts MUST deny. Denial MUST leave `latestEpoch`, `latestRoot`, `isAnchoredRoot`, `executionNonce`, and callee state unchanged.

## Mainnet key custody (§5.4) — sequential

1. Distinct keys for arbitrator, disputer, `funderWallet`, governance, `oracleSigner`, `resolverSigner`, `MINTER_ROLE`, and `DEFAULT_ADMIN_ROLE`.
2. Process-held `oracleSigner` and `resolverSigner` (not a human wallet).
3. Constrain ITK: fixed supply, or `MINTER_ROLE` held only by governance.
4. Then 2-of-3 or stricter Safe/timelock for governance, admin, and any `SovereignAgent` upgrade authority.

Do not deploy a `SovereignAgent` proxy to mainnet before steps 1–4.
