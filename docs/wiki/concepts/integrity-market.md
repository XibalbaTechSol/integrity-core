---
title: Integrity Market (Prediction Markets, Binary Options, A2A Capital Allocation)
created: 2026-07-09
updated: 2026-07-15
type: concept
tags: [layer-2, tokenomics, metrics]
confidence: high
source_files:
  - contracts/src/markets/IntegrityMarket.sol
  - contracts/src/markets/MarketFactory.sol
  - contracts/src/markets/A2ACapitalPool.sol
  - contracts/script/DeployMarkets.s.sol
  - integrity-oracle/backend/src/chain.rs
  - integrity-oracle/backend/src/handlers.rs
---

The protocol's **application layer**: the first concrete extension of
[agent primitives](agent-primitives.md)' "agents own and deploy their own
contracts" thesis beyond identity, up to markets and capital allocation.
Same mechanism throughout — [AIS](ais.md)-gated participation + off-chain
[BCC](bcc.md)-committed intent bound to an on-chain action — applied to
prediction markets, binary options, and agent-to-agent capital allocation.
Real, tested, and live on Base Sepolia (not a demo mockup).

## `IntegrityMarket` — agent-owned clone, not a singleton

One EIP-1167 clone (via `MarketFactory.deployMarket(...)`) is one market.
This mirrors how the 5 clone [primitives](agent-primitives.md) work, but one
layer up: any registered agent can deploy and own its own customized market
— its own question, outcome count, AIS entry bar, deadline, and resolver —
the same way it owns its `ReputationRegistry` clone. `MarketFactory` is
deliberately ungated (any agent in `XibalbaAgentRegistry` may create a
market; gating creation would undercut the ownership thesis).

Backs both **prediction markets** (N outcomes) and **binary options** (the
2-outcome case) as the same mechanism — pari-mutuel staking across
outcomes, settled on resolution.

```solidity
function initialize(address creator, string question, uint8 outcomeCount,
                     uint256 minAisToEnter, uint256 resolveDeadline, address resolver) external initializer;

function enterPosition(uint8 outcomeIndex, uint256 amount, bytes32 bccCommitmentHash) external;
// reverts AisTooLow unless agentRegistry.resolveAgent(msg.sender)'s live
// ReputationRegistry.effectiveScore >= minAisToEnter — same live-resolution
// pattern as EHRGate.checkAccess (see concepts/compliance-gate.md).

function resolve(uint8 winningOutcome) external; // onlyRole(RESOLVER_ROLE)
function wasCorrect(address agent) external view returns (bool);
```

`enterPosition` pulls real $ITK (`safeTransferFrom`) and records the
position's `bccCommitmentHash` — binding the on-chain stake to the
off-chain [BCC commitment](bcc.md) the agent signed *before* acting, so a
position is provably pre-committed, not a reaction to information obtained
afterward. `wasCorrect` is the read [integrity-oracle](../entities/integrity-oracle.md)
is expected to use to decide reputation/[Slasher](agent-primitives.md)
action — fraud/misreporting handling itself lives outside this contract, to
keep it a small auditable escrow rather than a second slashing engine.

```mermaid
flowchart LR
    Creator["Any registered agent"] -->|MarketFactory.deployMarket| Market["IntegrityMarket clone<br/>(question, outcomes, minAIS, deadline, resolver)"]
    Agent["Participating agent"] -->|BCC commitment signed first| Enter["enterPosition(outcome, amount,<br/>bccCommitmentHash)"]
    Enter -->|AIS gate: effectiveScore >= minAisToEnter| Market
    Resolver["RESOLVER_ROLE<br/>(labeled demo resolver, not a live oracle)"] -->|resolve winningOutcome| Market
    Market -->|wasCorrect| Claim["claimPayout()<br/>losers revert LosingPosition"]
```

### Trust boundary — documented, not hidden

`resolve()` is gated to `RESOLVER_ROLE`, granted at `initialize()` time by
the market's own creator (itself, a delegate, or the protocol's demo
signer). **This is a labeled demo resolver, not a live price-feed oracle
network** (no Chainlink/UMA integration). Staking, AIS-gating,
BCC-commitment binding, and pari-mutuel payout are all real; only
ground-truth outcome resolution is a swappable trust boundary — a
production deployment repoints `RESOLVER_ROLE`, the contract interface
doesn't change.

## `A2ACapitalPool` — global singleton, not agent-clonable

Unlike `IntegrityMarket`, this is one shared contract (a many-allocator-to-
many-agent venue doesn't fit the per-creator clone pattern). Real on-chain
"delegate money to a trustworthy agent" primitive:

```solidity
function allocate(address agent, uint256 amount, uint256 minAisToMaintain) external returns (uint256 allocationId);
function release(uint256 allocationId) external;   // re-checks live AIS at release time
function clawback(uint256 allocationId) external;  // pre-release only
function flagBreach(uint256 allocationId, string reason) external; // onlyRole(BREACH_REPORTER_ROLE), records history — moves no funds
```

An allocator (a human wallet, or another agent's `SovereignAgent`) escrows
$ITK earmarked for a target agent, gated on that agent's **live** AIS both
at allocation and again at release — an agent that decayed in between
cannot still collect. **Documented limitation, not a silent gap:**
`clawback` only reaches funds still held in this contract (pre-`release`);
once released, this pool has no further custody, so a post-release breach
has no fund-reversal path here — the punitive lever is the target agent's
own [Slasher](agent-primitives.md) clone. `flagBreach` exists purely to
give the dashboard/leaderboard an honest breach-history marker.

## `ComplianceGate.Vertical` extension

`{ None, Healthcare, PredictionMarket, Trading, CapitalAllocation }` —
additive-only. Like `Healthcare`'s self-declared flags (see
[ComplianceGate](compliance-gate.md)), these are a self-declared
operating-domain badge for dashboard/discovery and do **not** gate
`IntegrityMarket`/`A2ACapitalPool` participation, which only ever check
live AIS.

## Deployment

Deployed to Base Sepolia via a separate **incremental** script,
`contracts/script/DeployMarkets.s.sol` — not a re-run of genesis
`Deploy.s.sol`, which would redeploy `IntegrityToken`/`XibalbaAgentRegistry`
from scratch and orphan every already-registered agent. It reads the
existing `deployments.baseSepolia.json`, deploys only the 3 new contracts
against the existing singletons, and merges new fields into the same file —
the general pattern for any future protocol-layer addition after genesis.
`IntegrityMarket` impl at `0x73f7B9C4Fdb83d3Cd09512737a8756aEF4794172`,
`MarketFactory` at `0xDB1cB3a45F4918e944254183bca8112e699AFB05`,
`A2ACapitalPool` at `0x388D0180725E0F757C6Ef01ef0474E718faA3776`. 21 new
`forge test` cases (`test/markets/IntegrityMarket.t.sol`,
`test/markets/A2ACapitalPool.t.sol`), full suite green.

## Oracle read API — built

`integrity-oracle` now exposes real reads over this layer — see
[integrity-oracle](../entities/integrity-oracle.md) for the full detail:
`GET /v1/markets` (cached, concurrent `MarketFactory` enumeration + per-market
`IntegrityMarket` view state), `GET /v1/markets/{id}` (single market +
per-outcome pari-mutuel pool + an optional single-address `getPosition`
read), `GET /v1/leaderboard` (real `ReputationRegistry.effectiveScore`
ranking — **no fabricated P&L**, `realized_pnl` is always `null` since that
needs event indexing not built this pass), and `GET /v1/agent/{id}/wallet`
(real `IntegrityToken.balanceOf` + open positions cross-referenced against
the markets cache — transaction history likewise `null`, honest gap, not
built).

**Contract-shape correction found while building the read API:**
`MarketFactory.allMarkets` is a public `address[]` state variable, which
only auto-generates an *indexed* `allMarkets(uint256) returns (address)`
getter — there is no single-call `allMarkets() returns (address[])`.
Enumeration is `allMarketsCount()` + a concurrent batch of `allMarkets(i)`
reads. By-creator listing uses the real `getMarketsByCreator(address)`
function, not the `marketsByCreator` mapping's auto-getter (same
indexed-getter limitation).

**Still not built:** per-holder position enumeration (needs indexing
`PositionEntered` events), realized P&L (needs indexing
`PositionEntered`/`MarketResolved`/`PayoutClaimed`), and wallet transaction
history (needs indexing ERC-20 `Transfer` + the above). All three are
documented gaps in the relevant response fields, not silently omitted. Don't
assume `integrity-dashboard` renders markets data — see
[integrity-dashboard](../entities/integrity-dashboard.md), whose "What's built" section
is limited to agent list/detail; no dashboard page consumes these new
endpoints yet.

Related: [agent primitives](agent-primitives.md), [BCC](bcc.md),
[AIS](ais.md), [contracts](../entities/contracts.md).
