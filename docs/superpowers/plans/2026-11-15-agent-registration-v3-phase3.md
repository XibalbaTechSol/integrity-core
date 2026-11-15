# Agent Registration v3 — Phase 3: repoint onto `AgentRegistry`, pack compiler, new deploy graph

**Parent plan:** `docs/superpowers/plans/2026-11-14-agent-registration-v3.md`
**Spec:** `docs/superpowers/specs/2026-11-14-agent-registration-v3-design.md`, Parts 4–5, plus the Phase 3 acceptance criteria.
**Builds on:** Phase 2, which added `AgentRegistry` (#220, merged as 07dfb32).
**Branch / worktree:** `feat/registration-v3-phase3`, `/mnt/storage/xibalba/Projects/worktrees/integrity-core/registration-v3-phase3`.

## Owner decisions, 2026-11-15 (these override Part 5 where they conflict)

1. **IntegrityKernel hold.** The owner is reviewing the kernel ("I need to review Kernal dont delete").
2. **Defer deletions.** The owner chose this when the hold collided with Part 5's deletions:
   - `ReputationRegistry` imports `StateAnchor`.
   - `DeployKernelReference.s.sol` deploys the whole primitives graph and reads `IntegrityIdentityReadV1`'s primitive fields.
   - `IntegrityAccount.t.sol` uses `AgentPrimitivesFactory`.

   So Phase 3 **repoints** the protocol onto `AgentRegistry` and **deletes nothing the kernel needs**.

**Kept unchanged until the post-review deletion PR:**
- `XibalbaAgentRegistry`, `AgentPrimitivesFactory`, `AgentProfile`, `StateAnchor`, `ReputationRegistry`, `Slasher`, `VerifierRegistry`, `health/ComplianceGate`;
- `IZkVerifier`, `RejectAllZkVerifier`, `IAnchorPolicy`, `AllowlistAnchorPolicy`;
- `IntegrityKernel`, `IntegrityAccount`, `IntegrityIdentityReadV1`, `IntegrityERC8004Registry`;
- the `DeployKernel*` scripts, their tests, and the Halmos files.

**Compile consequence for `SovereignAgent`.** The held factory constructs `SovereignAgent(did, controller, oracle, factory_)` and calls `sa.factory()`. Until deletion, `SovereignAgent` therefore keeps:
- its 4-argument constructor;
- the `factory` getter name (it now holds the `AgentRegistry` address);
- `updateAIS` / `ais` / `ORACLE_ROLE`.

Only `_resolveGate`'s internals move. The renames and the `updateAIS` removal are part of the deletion PR.

**Effect on held-graph agents.** An agent bound to the held `AgentPrimitivesFactory` gets an inert gate after the repoint: the factory does not implement `isRegisteredAgent`, the wrapped call fails, and the gate is inert. That graph is kept only so the kernel review can see it. Nothing new deploys it except `DeployKernelReference`, and the kernel's own enforcement is the ERC-7579 hook on `IntegrityAccount`, not `SovereignAgent`. **No v3 actor is ever bound to the factory.**

## Order of PRs

| PR | Scope | Depends on |
|---|---|---|
| 3.1 | Pack on-chain section compiler (`integrity_sdk`), additive | — |
| 3.2 | Contract repoint, new `Deploy.s.sol`, wiring test, confined e2e | 3.1 (golden vector) |
| 3.3 | Shield `register_with_oracle.py` moves to off-chain registration (Phase 1 Task 10, never landed); integrity-console demo `main.py` too | — (other repos) |
| 3.4 | SDK/CLI primitives registration path removed; bcc_middleware moved to `AgentRegistry` | 3.2, 3.3 |
| deletion PR | Delete the held graph, rename `factory` to `registry`, remove `updateAIS` | the owner's kernel review |

The SDK's `registration.py` primitives path is Python only, and the kernel doesn't use it. It still waits for 3.3, because Shield and integrity-console import it. Cortex and Shield read the base checkouts through editable path deps, so deleting it first would break them.

## PR 3.1 — pack on-chain section compiler

- `integrity_sdk/core/pack_onchain.py` (beside `core/merkle.py` and `core/packs.py`); the section is the pack file `onchain.json`, so `pack_hash` covers it:
  - the `onchain` pack section `{domain, edges: [{from_node, relation, to_node, target, selector, risk_weight_bps}]}`;
  - `compile_onchain(section) -> OnchainPolicy(leaves, root)`, where leaves follow `PolicyRegistry.leafOf` (§4.4c) and the tree is the sorted-pair OZ `MerkleProof` tree;
  - `proof_for(policy, edge) -> list[bytes32]`.
- Naming for plain contract calls (left to the builder): `from_node = "agent"`, `relation = "calls"`, `to_node = "<target hex>:<selector hex>"`. Each is hashed the way the §4.4c golden vector hashes node names.
- The root is bound to the pack's signed digest: `onchain_policy_of(pack)` carries `pack_hash` alongside, so a reader can check that the published root is the pack's root.
- Tests:
  - the §4.4c golden vector (spec/ and `GoldenVectors.t.sol`) reproduces byte for byte;
  - leaf order doesn't change the root;
  - each proof verifies against the root;
  - a tampered edge fails;
  - duplicate edges are rejected.

## PR 3.2 — contract repoint

- **`SovereignAgent._resolveGate`:** reads `AgentRegistry(factory)` directly. It uses `isRegisteredAgent(this)`, `resolveAgent(this).domainId` and `trustConfig()`, with every call wrapped so the gate is inert on failure. `IFactoryLike` and the XAR import are dropped from `SovereignAgent`.
- **`AISRegistry`:** `agentRegistry` becomes an `AgentRegistry`. When a registry is wired, `postCheckpoint` reverts for an agent that is not `isRegisteredAgent` ("AIS checkpoints only for agents with an actor"). The reward domain comes from `resolveAgent(agent).domainId`.
- **`AgentAuthorityResolver` / `IAgentAuthorityResolver`:**
  - known means `AgentRegistry.isRegisteredAgent`;
  - AIS comes from `AISRegistry`;
  - `getStateAnchor` and the enterprise branch are removed.
  - **Scale check:** `AISRegistry` scores are 0..10000, and `ReputationRegistry.effectiveScore` is on its own scale. The floors in `EHRGate` and `ConstraintExecutionPolicy`, and their tests, are converted explicitly, never silently.
- **`XibalbaNameService` and `AgentLineageRegistry`:** change the type to `AgentRegistry`. Their logic is unchanged.
- **`Deploy.s.sol`:** rewritten for the v3 graph:
  - `DomainRegistry`, `AgentRegistry` (granted `REGISTRAR_ROLE`), `TrustConfig`, `PolicyRegistry`, `StakeVault`, `AISRegistry`, `ActionAnchor`, `ITK`, `RewardRegistry` and its modules, XNS, Lineage, and the health set;
  - the attester comes from `ATTESTER_ADDRESS`, distinct from the scorer.

  The deployments file gains `AgentRegistry` and `protocolAddresses.attester`.

  **Amended during 3.2:** `Deploy.s.sol` still deploys the held graph alongside v3, **unwired**: the held registry gets no `trustConfig`, so agents built by the held factory resolve an inert gate (pinned by `ProtocolPinnedGate.test_3_heldFactoryAgentResolvesInertGate`). The SDK conftest (`tests/conftest.py` runs this script on Anvil) and the Oracle `e2e.rs` still register agents through the held factory, so removing it here would break CI before their replacements land. PR 3.4 removes it from `Deploy.s.sol`. The standalone `DeployXns`, `DeployAgentLineageRegistry` and `DeployEHRGate` scripts read `.singletons.AgentRegistry`.
- **Scale conversion (done in 3.2):** `AgentAuthorityResolver.getAis` returns `AISRegistry` basis points unchanged. `EHRGate.minAisThreshold` is now basis points: Deploy's 800 became 8000 and the test thresholds were multiplied by 10.
- **`ConstraintExecutionPolicy` (known limitation):** its AIS floor reads `SovereignAgent.ais()`, the oracle-pushed cache, which stays 0 for v3 agents (`oracle == 0`). Genesis uses `minAis = 0`, so nothing changes today. It is documented in the contract's NatSpec and repointed to `AISRegistry` in the deletion PR.
- **Tests:**
  - rewrite the gate tests (`ExecuteGating`, `Invariants`, `ProtocolPinnedGate`, `PolicyHooks`, `MediationM1`, `SovereignAgent`) to bind actors through `AgentRegistry`;
  - add `test/trust/ConfinedAgentE2E.t.sol`: take PR 3.1's vector pack, `setGraphRoot`, deploy a `SovereignAgent`, register it as actor; a call inside the map succeeds and a call outside it reverts `EdgeNotProven`;
  - rewrite `test_trust_wiring.py` against the new Deploy on a fresh Anvil.
- **ABIs:** add `AgentRegistry` to the shipped list. The held ABIs stay until 3.4 or the deletion PR.

## PR 3.4 — SDK/CLI/BCC

- **SDK:** delete the `registration.py` primitives path (`register_agent`, `FUNDER_PRIVATE_KEY` flow, genesis-root anchoring) with its tests and docs. Registration is off-chain only. `--onchain` comes in Phase 4, since it needs the attestation route.
- **CLI:** delete `test_cli_chain_full_registration` and the chain registration code path.
- **bcc_middleware:**
  - `chain.py` and `config.py` move to the `AgentRegistry` ABI and contract name;
  - the `verifying_contract` binding names `AgentRegistry`;
  - **fail closed:** when a chain is configured and the deployments file has no `AgentRegistry` entry, that is a startup or validation error, not a silent skip (the lookup is renamed while live deployments still say `XibalbaAgentRegistry`).
  - The PR body notes that BCC signers (hooks, Shield) need the new address.

## Acceptance (Phase 3 under the owner's deferral)

- `forge test` is green, and the confined in-map/out-of-map e2e passes from a compiled pack.
- `test_trust_wiring.py` passes on a fresh Anvil.
- No **active** (non-held) code path references the old graph. This grep, run outside `docs/`, the held files listed above, and the Oracle runtime (Phase 4), is empty:
  `XibalbaAgentRegistry|AgentPrimitivesFactory|PrimitiveSet|registerPrimitives|agent_primitives|/v1/agent/register([^/]|$)`
  - The trailing `([^/]|$)` excludes Phase 1's `/v1/agent/register/offchain`.
- The spec's repo-wide grep is met after Phase 4, the docs sweep, and the post-review deletion PR. It is reached across phases, not redefined.

## Out of scope / owner steps

- The **Base Sepolia deploy** is run by the owner after the exposed Base Sepolia credentials are rotated (`Deploy.s.sol --broadcast`).
- **Kernel review**, then the deletion PR.
