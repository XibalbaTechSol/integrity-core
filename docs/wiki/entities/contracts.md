---
title: contracts
created: 2026-07-07
updated: 2026-11-20
type: entity
tags: [layer-2, identity, tokenomics, compliance, control-layer, wallet-stack, erc8004]
confidence: high
source_files:
  - contracts/src/framework/AgentRegistry.sol
  - contracts/src/framework/AgentLineageRegistry.sol
  - contracts/src/framework/AgentPrimitivesFactory.sol
  - contracts/src/wallet/IntegrityHook.sol
  - contracts/src/wallet/IntegrityGuard.sol
  - contracts/src/wallet/SafeAccountVerifier.sol
  - contracts/src/trust/StakeVault.sol
  - contracts/src/trust/AISRegistry.sol
  - contracts/src/trust/ActionAnchor.sol
  - contracts/src/trust/PolicyRegistry.sol
  - contracts/src/kernel/IntegrityERC8004Registry.sol
  - contracts/src/core/SovereignAgent.sol
  - contracts/src/health/ComplianceGate.sol
  - contracts/src/health/SmartBAA.sol
  - contracts/script/Deploy.s.sol
---

The Solidity/Foundry package (solc 0.8.28): the on-chain substrate of the AI Agent Control Layer.
It implements the [3-tier agent identity](../concepts/did.md), the modular [SovereignAgent wallet stack](../concepts/agent-primitives.md) (`IntegrityHook`, `IntegrityGuard`, `SafeAccountVerifier`), the shared [Trust Layer v2 singletons](trust-layer.md) (`AgentRegistry`, `StakeVault`, `AISRegistry`, `ActionAnchor`), the `$ITK` token, the ERC-8004 / Agent0 Public Passport bridge, and the [Integrity Health](../concepts/compliance-gate.md) HIPAA vertical on Base Sepolia / EVM.

## Table of contents

- [Dependency-resolution evidence](#dependency-resolution-evidence)
- [Contents](#contents)
- [Key invariants](#key-invariants)
- [State](#state)
- [Honest gaps](#honest-gaps)

## Dependency-resolution evidence

The Chainlink CCIP sources pin imports to the OpenZeppelin 5.3.0 namespace.
`contracts/remappings.txt` therefore includes an explicit
`@openzeppelin/contracts@5.3.0` remapping to the installed OpenZeppelin 5.x
package. Without that entry, deployment-backed Software Development Kit
(SDK) and command-line interface (CLI) tests fail during Foundry compilation
even though the ordinary contract unit tests can pass.

## Contents

- **Modular Wallet Stack (`contracts/src/wallet/`):**
  - `IntegrityHook.sol`: standard ERC-7579 hook enforcing pre/post-state constraints, daily outbound token limits, AIS reputation floors, and staking gates. Reverts any unauthorized execution.
  - `IntegrityGuard.sol`: Safe v1.4.1 transaction guard preventing direct execution bypass or tampering with Safe7579 fallback handlers.
  - `SafeAccountVerifier.sol`: verifies that an enclosed Safe account adheres to canonical single-owner, threshold=1, and Safe7579 sole-module requirements.
- **Trust Layer Singletons (`contracts/src/trust/`):**
  - `AgentRegistry.sol` & `AgentLineageRegistry.sol`: canonical identity registry of active agents, controllers, lineage, and policy parameters.
  - `StakeVault.sol`: shared collateral vault ($ITK) with per-action locking, unbonding delay, dispute slashes, and latching freeze logic.
  - `AISRegistry.sol`: oracle-posted score checkpoints (basis points, `0..10000`) and evidence Merkle roots.
  - `ActionAnchor.sol`: shared tamper-evident action trace Merkle root anchor.
  - `PolicyRegistry.sol`: per-domain call policy and Merkle-verified action graphs.
  - `TrustConfig.sol`: governance-owned registry wiring the active vault, policy, and reward contracts.
- **Discovery & ERC-8004 (`contracts/src/kernel/`):**
  - `IntegrityERC8004Registry.sol`: ERC-8004-shaped Identity Registry for public discovery, linking agentURIs with cryptographic two-way `did:integrity:...` service backlinks and CAIP-10 registrations.
  - `IntegrityIdentityReadV1.sol`: read-only discovery facade resolving DID documents and account metadata.
- **Agent Accounts & Anchors (`contracts/src/core/`, `contracts/src/oracle/`):**
  - `SovereignAgent.sol`: policy-confined smart contract account.
  - `StateAnchor.sol`: durable state and memory head anchor.
- **Integrity Health Stack (`contracts/src/health/`):**
  - `CoveredEntityRegistry`, `SmartBAAFactory`, `SmartBAA`, `HIPAAGuardrailRegistry`, `AgentAuthorityResolver`, `EHRGate`.
- **Markets (`contracts/src/markets/`):**
  - `IntegrityMarket.sol`, `MarketFactory.sol`, `A2ACapitalPool.sol`.
- **`XibalbaNameService` (XNS, `contracts/src/framework/XibalbaNameService.sol`,
  added 2026-07-11):** maps human-readable handles (`"hermes.integrity"`) to a
  registered agent's `SovereignAgent` address. Self-service and
  first-come-first-served (`register()` checks `XibalbaAgentRegistry.
  isRegisteredAgent(msg.sender)` live, no admin in the critical path) —
  **deliberately not a port of the legacy prototype's same-named contract**,
  which required an admin-only `REGISTRAR_ROLE` to register handles on an
  agent's behalf, violating this rewrite's self-sovereign thesis. Modeled
  instead on `DomainRegistry.registerDomain`'s existing self-service pattern
  in this codebase; `XNS`'s own `REGISTRAR_ROLE` is reserved for dispute
  intervention only (`revokeByRegistrar`), same scope as `DomainRegistry`'s.
  Was `[PLANNED]` (see the old `docs/wiki/concepts/xns.md`, now removed per
  that page's own "replace when a real contract lands" instruction) — no
  contract existed anywhere in this rewrite's `contracts/src/` until now.
- **`IntegrityGovernance` (`contracts/src/oracle/IntegrityGovernance.sol`,
  added 2026-07-25):** token-weighted, timelocked governance over protocol
  parameters. **Lock-to-vote** (ITK is locked to propose/vote, not
  checkpoint-counted) — the right fit because `$ITK` is a plain ERC20 with no
  `ERC20Votes` surface and deliberately no fee-on-transfer, so locking real
  ITK for the voting window is both exact and flash-loan/sybil resistant. The
  execute leg is hand-rolled but hard-constrained: the `(target, value,
  callData)` action is fixed at propose time and run verbatim (no
  accept-actions-at-execute path → actions can't be mutated between vote and
  execute), `nonReentrant`, gated on an ETA + a bounded `GRACE_PERIOD`. Full
  design + lifecycle: [Governance](../concepts/governance.md).
- **`IntegrityIdentityReadV1` (`contracts/src/kernel/IntegrityIdentityReadV1.sol`,
  added 2026-08-17):** a read-only Integrity identity discovery facade over
  `XibalbaAgentRegistry`. It resolves by DID, DID hash, and `SovereignAgent`,
  verifies forward/reverse and declared-DID consistency, returns the seven
  primitives and agent-controlled `profileURI`, and checks controller candidates
  against live account roles. It is informed by a pinned ERC-8004 Draft revision
  but explicitly non-conformant: no ERC-721 token, owner, transfer, approval,
  wallet-proof, metadata-write, event, reputation-feedback, validation, or ERC-165
  surface. See [Interface Contract](../../INTERFACE_CONTRACT.md) §6.1a.
- **`AgentAuthorityResolver` (`contracts/src/framework/AgentAuthorityResolver.sol`):**
  a read-only adapter used by `EHRGate` to resolve AIS for both sovereign clone-set
  agents and enterprise StateAnchor-only agents. It reads sovereign AIS from the
  agent's `ReputationRegistry` primitive and enterprise AIS from the registered
  account's `ais()` cache; it cannot set AIS. Incremental `EHRGate` deployments
  require this resolver to already be serialized in `deployments.<network>.json`;
  they do not deploy it against legacy registry bytecode as a side effect.

- **IntegrityKernel / IntegrityAccount — archived 2026-11-16.** The Phase I ERC-7579 kernel
  (spend budgets, a cached reputation floor, an optional assurance tier) and its guardian-governed
  account were removed from `main` after the owner's kernel review: nothing connected them to
  registration v3 (they read per-agent `ReputationRegistry` clones v3 agents never get), and no
  product used them. Source, tests, Halmos proofs and deploy scripts are recoverable from tag
  `kernel-phase1-archive`; the Base Sepolia `experimentalPhase1Reference` contracts remain deployed
  and unused. See the [archive record](../../archive/2026-11/kernel-phase1/README.md) for the revival trigger and port steps.

## Key invariants

- **Call-routing:** every clone's admin is the agent's `SovereignAgent` contract;
  state changes route through `SovereignAgent.execute` (one bootstrap exception —
  see [agent primitives](../concepts/agent-primitives.md)).
- **Clone-init footgun guarded:** inline field initializers (`= 3 days`) compile
  into the constructor, which clones never run — every such default is set in
  `initialize` instead (`Slasher.disputeWindow`, `ReputationRegistry.reportingPeriod`).
- **`via_ir = true`** — `registerPrimitives` clones+inits 5 contracts in one
  function and hits "stack too deep" under legacy codegen.

## State

- **497 tests** (`forge test`, confirmed via a real run 2026-09-08), all green
  — including full end-to-end coverage of the registration sequence in
  `test/AgentPrimitivesFactory.t.sol`, 21 market-layer tests, 14
  `test/XibalbaNameService.t.sol` tests, 3 tests covering
  `CCIPReputationBridge`'s per-agent-clone rework (see below), and **26 new
  `test/IntegrityGovernance.t.sol` tests** (full lifecycle + adversarial:
  double-vote, both-sides, withdraw-while-locked, quorum-unmet/tie/against-wins
  → Defeated, execute-before-timelock, execute-after-grace, only-Succeeded-can-queue,
  cancel authz, failing-action rollback).
  The total includes 10 `IntegrityIdentityReadV1` tests covering negative
  ERC-8004 conformance, identity consistency, controller rotation, URI behavior,
  duplicate-agent rejection, malformed registry states, and isolation of fixed
  identity reads from a reverting profile contract.
- `SovereignAgent.execute` and `StateAnchor.anchorRoot` are frozen host chokepoints
  with agent-pinned, swappable `IExecutionPolicy` and `IAnchorPolicy` contracts. Policy
  false returns and reverts fail closed. The SDK anchors agent-only genesis before pinning
  the oracle-only anchor policy; a real Anvil registration test verifies both policy
  pointers. This describes future deployment source, not a retrofit of existing agents.
- **Deployed to Base Sepolia** (chainId 84532): `XibalbaAgentRegistry` at
  `0x72e21e44AdD6d6e7CAa02eaedF078630afC40819`, `AgentPrimitivesFactory` at
  `0x215f39C8a2Cea2F8c6976fA10bbf48479825aD6e`, plus the market-layer
  singletons (see [Integrity Market](../concepts/integrity-market.md)). Full
  set in `deployments.baseSepolia.json`. **`XibalbaNameService` and
  `IntegrityGovernance` are both wired into `Deploy.s.sol` (genesis) and
  verified against local anvil, but not yet broadcast to Base Sepolia** —
  a live-contract, gas-costing action needing explicit sign-off, not taken
  automatically. Until then, the oracle read endpoints for both return a clean
  `MissingSingleton` (**HTTP 400**) and the dashboard degrades to an honest
  "not deployed yet" state (never a fabricated result). See `PRODUCTION_GAPS.md`
  §4.
- `IntegrityIdentityReadV1` is wired into future `Deploy.s.sol` genesis runs but
  is **not deployed to Base Sepolia**. Existing agents require no migration. An
  incremental deployment remains an approval-gated external write; see
  `PRODUCTION_GAPS.md` §28.
- `EHRGate` is wired for future genesis deployments and has an incremental
  script, but existing networks whose registry bytecode predates the enterprise
  registry API require a separately approved registry/resolver migration first.
  `DeployEHRGate.s.sol` fails before broadcasting if
  `singletons.AgentAuthorityResolver` is absent.

## Honest gaps

- The source `XibalbaAgentRegistry` now rejects registering the same
  `SovereignAgent` under multiple DIDs, and the identity facade still detects
  declared-DID mismatches. Existing Base Sepolia bytecode has not been updated,
  and native ERC-8004 convergence is still deferred; generic ERC-8004 or
  ERC-721 tooling must not be pointed at this facade.

- The repository's `UltraPlonkVerifier.sol` is now the real generated verifier and
  has valid/tampered/malformed proof coverage. `ReputationRegistry` checks its six
  logical inputs against pinned identity, monotonic nonce, current chain, its own
  clone address, and the exact anchored leaf, and prevents leaf reuse. The
  **existing Base Sepolia address
  still contains the older fail-closed placeholder bytecode**, so source capability
  must not be described as deployed capability until a separately approved verifier
  deployment is read back and exercised on-chain. See [ZKP](integrity-zkp.md) and
  `PRODUCTION_GAPS.md` §26.
- `CCIPReputationBridge.sol` — **reworked 2026-07-11**, no longer a gap in the
  sense of being architecturally incompatible with the per-agent clone model: it
  now holds `XibalbaAgentRegistry` and resolves each agent's own
  `ReputationRegistry` clone via `resolveAgent(agent).primitives.reputationRegistry`
  (the same idiom `EHRGate`/`IntegrityMarket`/`A2ACapitalPool` already use) instead
  of one immutable pre-clone-model registry address. Bridging is now correctly
  per-agent opt-in — an agent's `SovereignAgent` controller must grant this bridge
  `BRIDGE_ROLE` on its own clone before `_ccipReceive` can update its score, since
  each clone's `DEFAULT_ADMIN_ROLE` belongs to that specific agent, not a global
  admin. Still not deployed by `Deploy.s.sol` — but that's now a genuine
  operational decision (a peer bridge needs a second real chain to be meaningful),
  not a remaining code gap.

**`DeployProtocolEvidenceAnchor.s.sol`, added 2026-10-05 (B4)**: an incremental deploy
script (same pattern as `DeployXns.s.sol`) for a single, protocol-wide `StateAnchor`
instance dedicated to BCC/receipt evidence — same contract code as every per-agent
memory `StateAnchor`, but admin is the funder EOA directly (a protocol singleton, not
an agent-owned primitive, so no `SovereignAgent.execute` routing is needed). Writes
`.singletons.ProtocolEvidenceAnchor` when that key already exists in the deployments
file, otherwise logs the address for a reviewed manual edit, exactly like `DeployXns`.
See [bcc_middleware](bcc_middleware.md)'s "Evidence anchoring now targets a dedicated
contract" section for why this exists. Verified end to end against a real local anvil.
The Base Sepolia manifest still has no `ProtocolEvidenceAnchor` entry. The owner approved
that incremental broadcast on 2026-11-03; the identical script passed an Anvil dry run
(chain 31337, 852,992 gas). No testnet transaction has been sent. Live use is pending a
rotated testnet-only signer with owner-only permissions; local evidence is not deployment proof.

Related: [agent primitives](../concepts/agent-primitives.md),
[ComplianceGate](../concepts/compliance-gate.md),
[Interface Contract](../../INTERFACE_CONTRACT.md).
