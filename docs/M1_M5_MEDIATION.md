# M1–M5 mediation (production `SovereignAgent`)

Companion to `docs/IMPLEMENTATION_PLAN.md` §2.1 and `SPEC.md` §5.3.
The production account is `SovereignAgent.execute`. The experimental kernel
(`IntegrityAccountV1Experimental`) remains non-deployed and is not the v1 path.

| Gap | v1 decision | Code |
| --- | --- | --- |
| **M1** value outside mediation | Native `value` was already capped by `ConstraintExecutionPolicy.maxValue`. ERC-20/721 `transfer` / `transferFrom` / `approve` / `safeTransferFrom` amounts are now capped per token when `enforceTokenCaps` is true. |
| **M2** every path through the hook | **v1 does not ship batch, `delegatecall`, executor, or fallback execution.** `SovereignAgent.execute` is a single `CALL`. Rejecting those paths (rather than mediating them) is the v1 design. Do not build batch speculatively. |
| **M3** module install/remove | **N/A on production `SovereignAgent`** (no module registry). If/when the experimental kernel is promoted, install/remove MUST use the same policy `check` as `execute`. Until then, do not claim M3 on the experimental account. |
| **M4** kernel swap | Guardian / upgrade actions MAY bypass the execution policy. Named permanent exception: the hook cannot gate its own removal without becoming unremovable. All other paths in $E$ stay mediated. Multi-party delayed swap is still required before a mainnet proxy (§5.3, §5.4). |
| **M5** `mediation_ok` | `forge script contracts/script/MediationOk.s.sol` reports whether an agent has a non-zero `executionPolicy` and whether an optional `StateAnchor` has a non-zero `anchorPolicy`. |

## Using M1 token caps

```solidity
policy.setTokenCap(token, cap);      // 0 cap + enforceTokenCaps = deny that token
policy.setEnforceTokenCaps(true);
agent.setExecutionPolicy(address(policy));
```

Unknown selectors are still subject to native `maxValue` and the target allowlist.
They are not treated as token transfers.
