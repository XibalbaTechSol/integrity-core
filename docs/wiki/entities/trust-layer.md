---
title: trust-layer
created: 2026-11-11
updated: 2026-11-11
type: entity
tags: [layer-2, tokenomics, staking, control-layer, security]
confidence: high
source_files:
  - contracts/src/trust/ITK.sol
  - contracts/src/trust/AISRegistry.sol
  - contracts/src/trust/StakeVault.sol
  - contracts/src/trust/PolicyRegistry.sol
  - contracts/src/trust/OpenPolicyModule.sol
  - contracts/src/trust/RewardRegistry.sol
  - contracts/src/trust/DiscountRewardModule.sol
  - contracts/src/trust/ActionAnchor.sol
  - contracts/src/trust/TrustConfig.sol
  - contracts/src/core/SovereignAgent.sol
  - contracts/src/framework/AgentPrimitivesFactory.sol
  - contracts/script/Deploy.s.sol
  - integrity-sdk/tests/test_trust_wiring.py
---

# Trust layer (Integrity Token v2)

The trust layer is the on-chain economic tier of the protocol: it turns an agent's
[Agent Integrity Score](../concepts/ais.md) into consequences. A registered agent stakes ITK, each
action it executes locks some of that stake, and a score that falls below a threshold freezes the
agent until governance acts. It is the slowest of the protocol's control loops and is opt-in:
policy evaluation and signed receipts work without it.

## Table of contents

- [Contracts](#contracts)
- [The gated execute path](#the-gated-execute-path)
- [Why the gate cannot be unwired](#why-the-gate-cannot-be-unwired)
- [Staking, freezing and unbonding](#staking-freezing-and-unbonding)
- [The action graph](#the-action-graph)
- [Genesis deployment](#genesis-deployment)
- [Two tokens named ITK](#two-tokens-named-itk)
- [Known limits](#known-limits)

## Contracts

All are singletons keyed by agent address. None is cloned per agent.

| Contract | Job |
|---|---|
| `ITK` | Capped ERC20 stake asset. 100M lifetime mint; burning never reopens headroom. |
| `AISRegistry` | Latest score checkpoint per agent (basis points, `0..10000`) plus an evidence root. Posting a checkpoint drives the vault and the reward path. |
| `StakeVault` | Stake, per-action locks, the latching freeze, disputes that burn, and the unbonding queue. |
| `PolicyRegistry` | Per-domain policy: a module, or a Merkle root over the allowed action graph. |
| `RewardRegistry`, `DiscountRewardModule` | A rising score lowers the stake an agent must lock per action, capped at 50%. |
| `ActionAnchor` | Per-agent Merkle root anchor for the audit trail. |
| `TrustConfig` | Governance-owned record of which vault, policy registry and discount module the gate reads. |
| `OpenPolicyModule` | Explicit allow-all module for domains that have no call-level policy yet. |

## The gated execute path

`SovereignAgent.execute` runs these in one transaction, after the agent's existing execution
policy hook:

1. **Freeze.** Revert `Frozen` if the vault has the agent frozen. This applies to zero-value calls too.
2. **Policy.** In a graph domain the caller must use the edge-claim overload and prove the edge;
   plain `execute` reverts `EdgeClaimRequired`. Otherwise the domain's module decides.
3. **Stake lock.** Lock `domainFloor + value × riskWeightBps / 10000`, reduced by the agent's trust discount.
4. **The call.**

The oracle later posts a checkpoint that releases compliant locks, and may freeze.

## Why the gate cannot be unwired

An agent deploys its own `SovereignAgent` and is its own controller, so anything the agent could
set, it could also swap for a harmless fake. Three bindings close that:

- **The modules are governance-pinned.** The agent reads them at call time through
  `factory.registry().trustConfig()`. It has no setter for any of them.
- **The domain comes from the registry record**, not from the agent.
- **Registration pins the bytecode.** The factory deploys one reference agent in its constructor,
  stores its runtime codehash, and refuses to register anything else (`NotCanonicalAgent`). Checking
  only what `factory()` returns was not enough: arbitrary code can return the right address.

The gate is deliberately inert for an agent that is not yet registered, because onboarding itself
routes calls through `execute` before registration completes.

## Staking, freezing and unbonding

- **Freeze latches.** A checkpoint below `freezeThreshold` sets `frozen`. A later good checkpoint
  does not clear it, and neither does resolving a dispute. Only governance `unfreeze` does.
- **Disputes burn.** A slashed amount is burned, so no address profits from a slash.
- **Withdrawal is two-step.** `requestUnstake` queues free stake; `withdraw` pays it after
  `unbondingDelay` (7 days by default, governance-settable from 1 to 30). Without the delay an agent
  could see its failing checkpoint in the mempool and pull its stake before the freeze landed.
- **Queued stake is still at risk.** A freeze blocks `withdraw`, and a dispute can take stake back
  out of the queue. Queuing a withdrawal never shrinks what can be slashed.

The vault's bookkeeping invariant is `locked + disputeLockedOf + unbonding ≤ amount`.

## The action graph

A graph domain commits to a Merkle root over its allowed edges. One leaf is

```
keccak256(abi.encode(fromNode, relation, toNode, target, targetSelector, riskWeightBps))
```

The leaf binds the callee address and the function selector, so a proof for one call cannot
authorize another. Arguments are left out on purpose, so an edge can mean "tool X with any
arguments". The risk weight is inside the leaf and cannot be under-reported. The same leaf is
computed off-chain by the navigation engine in `xibalba-cortex`; a pinned golden vector in both
repositories keeps the two byte-identical. See `docs/INTERFACE_CONTRACT.md` §4.4c.

## Genesis deployment

`Deploy.s.sol` deploys and wires the whole layer, so the gate is live from the first block:

- the registry is pointed at `TrustConfig` before anything is able to freeze an agent;
- `AISRegistry` receives the vault and reward roles its checkpoint needs;
- the two bootstrap domains get `OpenPolicyModule`, because a domain with no policy fail-closes
  every call;
- the freeze threshold defaults to 1000 basis points (`FREEZE_THRESHOLD_BPS`). It sits below the
  tier-0 [identity ceiling](../concepts/identity-ceiling.md) of 3000, so an unverified agent is not
  frozen by its first checkpoint.

`integrity-sdk/tests/test_trust_wiring.py` runs the real deploy on a local chain and checks the
full chain of custody: a failing checkpoint freezes an SDK-onboarded agent, and its next action
reverts.

## Two tokens named ITK

`ITK` (this layer's stake asset) and `IntegrityToken` (the registration-bond and market token used
by the oracle, SDK and BCC middleware) are different contracts at different addresses. Both display
as "ITK". The deployments file distinguishes them by key: `ITK` and `IntegrityToken`.

## Known limits

- Bootstrap domains are permissive at the call level until governance sets a module or a graph root.
- Lock release trusts the oracle's reported amount; there is no per-action on-chain lock ledger.
- If governance repoints `TrustConfig` at a different vault, freezes recorded in the old vault stop
  gating execution. Migrate by keeping the same vault, or re-apply freezes.
- `SovereignAgent.updateAIS` and its cached `ais` still exist alongside `AISRegistry`.
