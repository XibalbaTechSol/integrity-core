---
title: On-Chain Governance
acronyms: [ITK]
created: 2026-07-25
updated: 2026-07-25
type: concept
tags: [tokenomics, layer-2]
confidence: high
source_files:
  - contracts/src/oracle/IntegrityGovernance.sol
  - contracts/test/IntegrityGovernance.t.sol
  - contracts/script/Deploy.s.sol
  - integrity-oracle/backend/src/chain.rs
  - integrity-oracle/backend/src/handlers.rs
---

`IntegrityGovernance` (`contracts/src/oracle/IntegrityGovernance.sol`) is the
protocol's token-weighted, timelocked governance over on-chain parameters. It
implements the exact lifecycle the dashboard's `GovernancePanel` had long
documented as roadmap: **propose → vote → queue → execute**, with voter funds
reclaimable once a proposal is terminal.

## Table of contents

- [Lock-to-vote (not ERC20Votes)](#lock-to-vote-not-erc20votes)
- [Lifecycle & states](#lifecycle-states)
- [The execute leg (the dangerous surface, constrained hard)](#the-execute-leg-the-dangerous-surface-constrained-hard)
- [Read surface (designed for the oracle)](#read-surface-designed-for-the-oracle)
- [Genesis params & deploy status](#genesis-params-deploy-status)
- [Deferred by design](#deferred-by-design)

## Lock-to-vote (not `ERC20Votes`)

Vote weight is **locked ITK**, not checkpoint-counted balance. This is the
correct model for this token, for two concrete reasons:

- `$ITK` ([IntegrityToken](../entities/contracts.md)) is a plain ERC20 with no
  `ERC20Votes`/`getPastVotes` surface — there are no historical checkpoints to
  weight a vote against.
- It deliberately removed fee-on-transfer, so `transferFrom(voter, contract,
  amount)` credits **exactly** `amount` (a documented property the Slasher and
  SmartBAA also depend on). Locking real ITK for the voting window is therefore
  both exact and flash-loan/sybil resistant: a flash-borrowed balance can't vote,
  because it can't stay locked across the window.

Proposing locks `proposalThreshold` ITK, recorded as the proposer's initial FOR
vote — so proposing is itself flash-loan resistant and the proposer has skin in
the game. Voters reclaim locked ITK via `withdraw` once the proposal is terminal
(`Defeated`/`Executed`/`Expired`/`Canceled`); while `Active`/`Succeeded`/`Queued`
the stake stays locked.

## Lifecycle & states

`state(id)` is derived purely from stored data + `block.timestamp`:

`Active` (voting open) → after the window closes, `Defeated` (quorum unmet **or**
`againstVotes >= forVotes`) or `Succeeded` → `queue()` sets a timelock ETA →
`Queued` → `execute()` after the ETA and within `GRACE_PERIOD` → `Executed`. A
queued proposal not executed within the grace window becomes `Expired` (its locked
ITK reclaimable — a stuck proposal can never permanently trap funds). `cancel()`
(proposer or guardian/owner, before execution) → `Canceled`.

## The execute leg (the dangerous surface, constrained hard)

The single highest-risk part of any governance contract is delayed execution of
arbitrary calls. Here it is hand-rolled but bound tightly:

- The `(target, value, callData)` action is **fixed at propose time and executed
  verbatim** — there is no accept-actions-at-execute path, so a proposal's actions
  cannot be mutated between vote and execution (a classic governance bug).
- `execute` is `nonReentrant` and gated on both the timelock ETA and the bounded
  `GRACE_PERIOD`.
- A failing action reverts the whole call (rolls back `executed`), leaving the
  proposal `Queued` and re-executable rather than consumed.

## Read surface (designed for the oracle)

`proposalCount()` + `getProposal(id)` + `state(id)` view getters let the
[oracle](../entities/integrity-oracle.md) enumerate with a simple 1-based index
loop (`ChainClient::read_proposals`) — deliberately not log-scanning. Exposed as
`GET /v1/governance/proposals`; the dashboard's `GovernancePanel`/`GuardianPilot`
render live proposals + FOR/AGAINST tallies from it.

## Genesis params & deploy status

Wired into genesis `Deploy.s.sol` with testnet defaults (voting period 3 days,
timelock 2 days, `proposalThreshold` 1,000 ITK, quorum 10,000 ITK; guardian = the
`governance` protocol role). **Not yet broadcast to Base Sepolia** ("build now,
defer deploy") — a gas-costing operator action. Where the singleton is absent the
oracle returns `MissingSingleton` (**HTTP 400**) and the panels stay in their honest
"Not Yet Live" state, never a live-but-empty list. `deployments.local.json` is also
deliberately not regenerated for it, since a fresh local deploy would remint every
address and break the seeded audit DB. See `PRODUCTION_GAPS.md` §4.

## Deferred by design

The dashboard wiring is **read-only**: the write half (propose / castVote / queue /
execute — all wallet-signed txs) is deliberately not in the UI yet (done via CLI/SDK),
noted inline in `GovernancePanel` and in `PRODUCTION_GAPS.md` — an explicit deferral,
not a silent gap.

Related: [contracts](../entities/contracts.md),
[integrity-oracle](../entities/integrity-oracle.md),
[Interface Contract](../../INTERFACE_CONTRACT.md).
