# Upgradeability of the per-agent contracts — decision record

**Decided 2026-07-29.** Resolves `docs/MAINNET_READINESS.md` item 6, the one pre-mainnet
choice that cannot be revisited after the first agent registers.

**Decision: beacon proxy with a per-agent pin, beacon owned by a multisig initially and
transferred to `IntegrityGovernance` once ITK supply is constrained.**

> **UNDER RECONSIDERATION (2026-07-29, same day).** A third option — keeping the contracts
> frozen and swapping *policy* behind designed-in hooks, the pattern `VerifierRegistry`
> already uses here — was under-weighted when this was decided. It fixes the concrete §7.2
> bug, reuses a proven in-repo pattern, and crucially bounds the blast radius of a
> compromised authority key to denial-of-service rather than theft. See
> [`upgradeability-comparison.md`](upgradeability-comparison.md), which currently
> recommends switching. Do not implement from this document until that is settled.

---

## The problem

`SovereignAgent` and `StateAnchor` are deployed **directly per agent** (`chain.py`
`deploy_sovereign_agent` / `deploy_state_anchor`), not cloned from a shared upgradeable
implementation. Each agent's copy is frozen at whatever bytecode shipped that day, and
`XibalbaAgentRegistry` has `registerPrimitives` plus **read functions only** — no rotate,
update, or migrate path anywhere. A DID is permanently welded to its seven addresses.

This is not theoretical. The spec §7.2 memory fix (restricting genesis anchoring to the
agent) **cannot reach the 7 agents already registered on Base Sepolia**. On mainnet the
same shape means any bug in these two contracts is permanent for every agent registered
before the fix.

## Why not "just migrate the DID to new addresses"

Because the *address*, not the DID, is what everything else keys on:

| Keyed on the SovereignAgent address | Where |
|---|---|
| Bonded stake | `Slasher.stakeOf[msg.sender]`, `lockedStakeOf` |
| $ITK balance | ERC-20 balance at the contract address (xibalba holds 10,500 ITK) |
| Agent legitimacy | `isRegisteredAgent(msg.sender)` — 4 contracts gate on this |
| Market positions | `IntegrityMarket` / `A2ACapitalPool` per-address accounting |
| Anchored memory | `StateAnchor` roots live at that contract |

Rotation therefore is not a pointer update — it is a value migration (move ITK, unwind and
re-stake, port or close positions, re-anchor memory) plus a new laundering vector: rotate
away from a pending dispute. **Keeping the address stable is strictly simpler**, and that
is exactly what a proxy does.

## Why a beacon rather than per-agent UUPS

Per-agent UUPS with agent-only authority preserves the self-sovereignty thesis perfectly,
but a critical security fix then reaches only the agents that individually choose to act.
On mainnet, with real value at stake, that means known-vulnerable agents running
indefinitely and no one able to do anything about it.

A beacon makes the fleet fixable atomically. The per-agent **pin** is what keeps the thesis
honest: any agent may permanently opt out and manage its own implementation. Sovereignty
becomes an *exercisable right* rather than a default — and the 14-day governance timelock is
what makes exercising it possible, because an agent can see a change coming and pin before
it lands.

## Why governance owns the beacon — and why not yet

`IntegrityGovernance` is already deployed and is technically capable: `propose(target,
value, callData)` executes an arbitrary call after a timelock, with a 14-day grace period.

**It is not yet a meaningful authority.** Voting power is *locked ITK*, and ITK is mintable
by whoever holds `MINTER_ROLE` — today the funder EOA and xibalba's SovereignAgent.
Unlimited mint is unlimited votes, so "governance controls upgrades" currently reduces to
"the funder EOA controls upgrades, with extra steps."

Sequencing that follows:

1. Beacon owner = a **multisig** at launch (not the current single EOA — see readiness item 1).
2. Constrain ITK: fixed supply, or `MINTER_ROLE` held only by governance itself.
3. **Then** transfer beacon ownership to `IntegrityGovernance`.

Until step 2, transferring to governance would be theatre.

## Shape of the implementation

```
AgentBeacon (one per implementation kind: SovereignAgent, StateAnchor)
  owner: multisig -> IntegrityGovernance
  implementation(): address

AgentProxy (per agent, deployed by the agent's own wallet)
  storage: pinnedImplementation (address, 0 = follow beacon)
  _implementation() = pinned != 0 ? pinned : beacon.implementation()
  pin(address impl)   -- controller only, and only to a beacon-published implementation
  unpin()             -- controller only, re-joins the beacon
```

Non-negotiable constraints:

- **Pin authority is the agent's controller, never the protocol.** If the protocol can
  unpin, the opt-out is fake.
- **Storage layout is append-only forever.** No reordering, no type changes, reserved gaps
  on both implementations. This discipline is permanent from the first mainnet deploy.
- **`StateAnchor` upgrades are constrained further than `SovereignAgent`'s.** Its entire
  value is that anchored history cannot change: `isAnchoredRoot`, `rootAtEpoch`, and the
  monotonic `latestEpoch` are sacred. An upgrade may add behavior; it may never rewrite,
  reorder, or un-anchor a root. Any proposal touching that storage should be treated as an
  attack on the protocol's core claim, not a routine upgrade.
- **The agent still deploys its own proxy**, preserving the "deployment transaction proves
  self-sovereign control" property. The beacon is a shared implementation source, not a
  registrar.

Touch points: `contracts/src/core/`, `contracts/script/Deploy.s.sol` (deploy beacons),
`AgentPrimitivesFactory`, and `integrity_sdk.chain.deploy_sovereign_agent` /
`deploy_state_anchor` (deploy proxies rather than raw contracts).

## Consequences accepted

- **The 7 existing Sepolia agents cannot be retrofitted.** They are frozen and stay frozen;
  they are testnet artifacts. Mainnet starts clean with proxies from the genesis deploy.
- **Custom proxy logic is new audit surface.** Pin-or-beacon resolution is not a
  stock OpenZeppelin pattern and must be audited as bespoke code.
- **Fleet version fragmentation is now possible** by design, so version telemetry is needed:
  the oracle should report each agent's implementation address so pinned/stale agents are
  visible rather than silent.
- **Timelock delays emergency response.** A 14-day window is protection for agents and a
  liability during an active exploit. An emergency path (guardian pause, or a shorter
  emergency timelock with a higher quorum) is **an open question**, deliberately not decided
  here — a protocol-controlled pause on an agent's own account contract reopens the
  sovereignty question and deserves its own decision.

## Open items before implementation

1. Emergency response path (above).
2. ITK supply policy — blocks the governance handover.
3. Whether `pin` should be restricted to beacon-published implementations only (safer, but
   limits genuine sovereignty) or any address the controller chooses (fully sovereign, lets
   an agent pin malicious-to-itself code). Leaning restricted-to-published, because an agent
   pinning arbitrary code while other contracts trust `isRegisteredAgent` is a systemic risk,
   not merely self-harm.
