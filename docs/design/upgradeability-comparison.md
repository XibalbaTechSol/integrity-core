# Beacon proxy vs. frozen-plus-indirection — comparison

Companion to [`upgradeability-decision.md`](upgradeability-decision.md), written because
the "append a contract and re-point" instinct turned out to describe a real third option
that the first decision under-weighted. Read this before implementing; it may amend the
decision.

## The three positions

| | **A. Beacon + pin** | **B. Frozen + indirection** | **C. Frozen, no hooks** |
|---|---|---|---|
| Contract code | `delegatecall`s a swappable implementation | Immutable forever | Immutable forever |
| How behavior changes | Replace the implementation | Swap a policy contract the code already consults | It doesn't |
| Precedent in this repo | none (new) | **`VerifierRegistry`** — per-agent, versioned, agent-controlled pointer | `IntegrityToken`, registries |
| Can fix an unanticipated bug | Yes | Only where a hook happens to sit | No |

Position B is the one already proven here: `VerifierRegistry` is a frozen clone holding a
versioned pointer to whichever `IZkVerifier` an agent trusts, precisely so a circuit
upgrade doesn't force every agent to move at once.

## What each can actually fix

Change classes drawn from real items in `MAINNET_READINESS.md` and the current contracts,
not hypotheticals:

| Change needed | A. Beacon | B. Indirection | Notes |
|---|---|---|---|
| §7.2 — forbid `ANCHOR_ROLE` from anchoring genesis | ✅ | ✅ *if* `anchorRoot` consults an anchor-policy hook | A **restriction**; a satellite contract cannot do it, since the old path stays callable |
| Emergency pause of a compromised agent | ✅ | ✅ *if* the hook exists at `execute` | Same chokepoint requirement |
| Add lineage recording (§7.4) | ✅ | ✅ | Purely **additive** — a satellite contract suffices, no upgrade needed at all |
| New anchor semantics (per-domain roots, etc.) | ✅ | ✅ | Additive |
| Bug that locks ITK inside `SovereignAgent` | ✅ | ❌ | Value sits at the address governed by frozen code |
| Bug in `execute`'s call/return handling | ✅ | ❌ | Core logic, no hook can intercept it |
| Storage-corruption bug | ✅ | ❌ | — |
| Bug **in the policy contract itself** | ✅ | ✅ (swap the policy) | B's hook is itself replaceable |

The pattern: **indirection handles restrictions and policy, but only at chokepoints you
designed in advance. It cannot reach core logic or recover value.** A proxy reaches
everything, including things you did not anticipate — which is the entire point, since
unanticipated is the category that actually hurts.

## The asymmetry that matters most: blast radius of a compromised key

This is the argument I did not weigh properly the first time.

- **Under A**, whoever controls the beacon can replace an agent's *entire* implementation.
  A compromised upgrade key can rewrite `execute` to drain every non-pinned agent's ITK and
  stake. Authority compromise is **theft**.
- **Under B**, whoever controls the policy contract can only change what the hook governs.
  A compromised policy key can *block* anchoring or *deny* execution — denial of service,
  recoverable by swapping the policy back. It cannot rewrite fund-handling code, because
  that code is frozen. Authority compromise is **disruption**.

Given readiness item 1 — all six protocol roles are currently one EOA, and the beacon owner
would start as a multisig that has not yet been created — bounding the blast radius of key
compromise is worth a great deal. B fails safer under exactly the failure mode this
protocol is most exposed to today.

## Cost and risk

**A. Beacon + pin**
- New bespoke proxy: pin-or-beacon resolution is not a stock OpenZeppelin pattern, so it is
  audited as novel code rather than as a known-good library.
- Introduces the entire storage-collision/layout-discipline vulnerability class, permanently,
  from the first mainnet deploy.
- `delegatecall` + an extra `SLOAD` on every call, forever.
- Fleet fragments by version once agents pin; needs version telemetry to stay legible.

**B. Frozen + indirection**
- Standard, auditable contracts. No storage-layout discipline, no collision class.
- Hooks must be placed correctly *up front*; a missing hook is unfixable later. This is the
  real cost — it front-loads the requirement to predict what will need to change.
- A policy contract is a new trust dependency and a new brick risk: a misconfigured
  anchor policy stops every agent anchoring until it is swapped back.
- The "who controls the policy" question recurses exactly as it does for the beacon — same
  multisig-then-governance sequencing applies.

**C. Frozen, no hooks** — smallest attack surface, zero recourse. Already demonstrated
inadequate: the §7.2 fix cannot reach the 7 existing Sepolia agents.

## Where the hooks would go under B

Only two chokepoints matter, because everything consequential funnels through them:

```solidity
// StateAnchor
function anchorRoot(bytes32 root) external returns (uint256 epoch) {
    IAnchorPolicy(anchorPolicy).check(msg.sender, latestEpoch, root);   // <- swappable
    ...
}

// SovereignAgent
function execute(address target, uint256 value, bytes calldata data)
    external onlyController returns (bytes memory)
{
    IExecutionPolicy(executionPolicy).check(target, value, data);        // <- swappable
    ...
}
```

`anchorPolicy` and `executionPolicy` are agent-settable pointers, defaulting to a
protocol-published policy, following `VerifierRegistry`'s versioned-pin pattern exactly.
Note this reproduces the beacon+pin *governance shape* — shared default, per-agent opt-out —
without the proxy machinery.

Also worth deciding under B: policies must fail **open or closed** explicitly. A policy that
reverts when unreachable bricks the agent; one that passes on failure is not a control.

## Recommendation

**Switch to B (frozen + indirection), with the two hooks above** — unless you expect to need
recovery from unanticipated core-logic bugs more than you expect to need a bounded blast
radius on key compromise.

Reasoning: it fixes the concrete bug we actually have (§7.2), it fails safer under the
failure mode this protocol is most exposed to right now, it reuses a pattern already proven
in this codebase, and it avoids permanently adopting the storage-collision vulnerability
class in the contracts that hold agent funds.

**What would change my mind:** if agents will hold materially large balances early, the
inability to recover value from a stuck-funds bug becomes the dominant risk and A wins —
because under B, that money is simply gone.

**They compose, and that is probably the honest end state:** hooks for policy that is known
to vary, plus a proxy on `SovereignAgent` only (where the funds are) if recovery capability
is judged worth the added surface — leaving `StateAnchor`, whose whole value is
immutability, frozen with a hook. That is the "split" option from the original decision,
arrived at from the other direction.
