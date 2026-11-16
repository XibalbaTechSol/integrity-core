# Registration v3 — deleting the v2 on-chain graph (plan only)

**Parent plan:** `docs/superpowers/plans/2026-11-14-agent-registration-v3.md` (Phase 3, "consumer migration + deletions").
**Spec:** `docs/superpowers/specs/2026-11-14-agent-registration-v3-design.md`, Part 5 (the consumer table and "the old architecture is removed, not deprecated") and the Phase 3 acceptance grep.
**Sibling plan:** `docs/superpowers/plans/2026-11-16-agent-registration-v3-phase4.md`. This plan amends its PR 4.6 table (see "Boundary with 4.6").
**Status:** plan only. Nothing is deleted by this document. The owner chose "plan it first" on 2026-11-16.

Line references are to integrity-core `origin/main` at `c46b63d7`, integrity-console `origin/main` and `origin/fix/ui-consistency` (identical for every hit below), xibalba-cortex `origin/main`, xibalba-shield `origin/main`, the hooks snapshot `~/.local/share/xibalba-hooks`, and the hook entry scripts in `~/.claude/xibalba/`, all read on 2026-11-16. PR 4.3 is in flight and may move `handlers.rs` lines; each slice re-reads its lines before editing.

## In plain terms

When an agent registered under the old (v2) design, a factory contract made **seven personal contracts** for it:
- a wallet-like account (`SovereignAgent`);
- a memory notary (`StateAnchor`);
- a score board (`ReputationRegistry`);
- a penalty box (`Slasher`);
- a proof checker (`VerifierRegistry`);
- a healthcare compliance switch (`ComplianceGate`);
- a profile page (`AgentProfile`).

A phone-book contract (`XibalbaAgentRegistry`) recorded the seven addresses.

The v3 design replaced all of that:
- **One record per agent**, in one shared registry (`AgentRegistry`).
- **Shared contracts**: one score book (`AISRegistry`), one stake vault (`StakeVault`) and one notary (`ActionAnchor`).

v3 agents never get the seven personal contracts. The old ones are still in the repository, though, and several programs still look things up through them:
- the BCC middleware;
- the SDK's anchoring helpers;
- the hooks that anchor Claude's session vault;
- some Oracle endpoints;
- the console's health and explorer pages.

**"Deleting the v2 graph" means:**
1. Move each of those programs to its v3 equivalent.
2. Then remove the old contracts, their deploy scripts, ABIs and tests.

Nothing live holds money or real agents on the old graph. Base Sepolia is a testnet, and the local Anvil chain was reset without agents. So this is a cleanup, not a migration of users.

**Three parts are not mechanical, and need your decision first.** They are the owner questions at the end.
1. **`SovereignAgent` itself has to change.** Renaming `factory` to `registry` and removing `updateAIS` means editing the one contract we have treated as frozen.
2. **Some old features have no v3 home.** These are the ZK identity commitment, the healthcare compliance switch, the leaderboard, and the on-chain assurance tier.
3. **Nothing writes the new score book yet.** Code reads `AISRegistry`, but no production service posts scores to it.

## What the spec already decides (Part 5)

| v2 thing | v3 answer in the spec |
|---|---|
| `AgentPrimitivesFactory`, `StateAnchor`, `ReputationRegistry`, `Slasher`, `VerifierRegistry`, `ComplianceGate`, `AgentProfile` | deleted |
| `XibalbaAgentRegistry` (incl. enterprise profile, `registerCore`, `provisionPrimitives`) | deleted; `AgentRegistry` replaces it |
| `AgentAuthorityResolver`, `ConstraintExecutionPolicy`, `EHRGate`: AIS from the `ReputationRegistry` clone | AIS from `AISRegistry` |
| `IntegrityIdentityReadV1`, `IntegrityERC8004Registry` | read `AgentRecord`; primitive fields dropped (breaking, testnet only) |
| `SovereignAgent.updateAIS` / `ais` | removed now |
| `Deploy.s.sol`, deployments file, `test_trust_wiring.py` | rewritten for the new graph; fresh Base Sepolia deploy |
| `bcc_middleware/app/chain.py` | `AgentRegistry` |
| memory trail | "anchor it in the v2 `ActionAnchor` singleton, keyed by their actor" |

**Already done:**
- `AgentAuthorityResolver.sol:10` and `EHRGate.sol:28` already read `AISRegistry`.
- `AISRegistry.agentRegistry` (`AISRegistry.sol:47`) already points at `AgentRegistry`.

**Still on the old graph:**
- `ConstraintExecutionPolicy.sol:13-16` still reads `SovereignAgent.ais()`. Its own comment schedules the move for "the deletion PR that removes `updateAIS`", which is slice D5 below.

## The `ReputationRegistry` readers and their v3 replacement

| Reader | File:line | What it reads | v3 replacement | Status |
|---|---|---|---|---|
| `AgentAuthorityResolver` | `contracts/src/framework/AgentAuthorityResolver.sol:10` | AIS | `AISRegistry.latest(actor).score` (bps) | **done** |
| `EHRGate` | `contracts/src/health/EHRGate.sol:28` | AIS floor | same | **done** |
| `ConstraintExecutionPolicy` | `contracts/src/core/ConstraintExecutionPolicy.sol:13-16`, via `SovereignAgent.ais()` (`SovereignAgent.sol:78`, `:307`) | AIS floor | `AISRegistry.latest(agent).score`, in basis points (genesis `minAis = 0`, so nothing changes today) | slice D5 |
| BCC score push | `bcc_middleware/app/reputation.py:2`, `:48`, `:131-188` (`push_score` → `updateScoreWithCoverage`); `scoring_loop.py:3`, `:65`, `:76`, `:126-160` | writes the score | `AISRegistry.postCheckpoint(agent, scoreBps, windowEnd, evidenceRoot, releasable)` with `SCORER_ROLE` (`AISRegistry.sol:17`, `:94`) | slice D2, **owner question 3** |
| BCC stake read | `reputation.py:188` `get_available_stake` (Slasher) | free stake | `StakeVault.availableOf(actor)` through `AgentRegistry.trustConfig()` → `TrustConfig.stakeVault()`, as 4.2 does (`integrity_cli/status_cmd.py`) | slice D2 |
| BCC dispute | `reputation.py:210` `raise_dispute` (Slasher) | locks stake | `StakeVault.raiseDispute` (`StakeVault.sol:243`, `DISPUTER_ROLE`) | slice D2 |
| BCC quarantine gate | `bcc_middleware/app/quarantine.py:76-104` (`Slasher.lockedStakeOf`) | "under dispute" | `StakeVault.disputeLockedOf(actor) > 0` (public mapping, `StakeVault.sol:71`). **Not** `stakeOf().locked`, which covers per-action locks only (`:109-110`) | slice D2 |
| BCC policy prose | `bcc_middleware/policies/bcc.rego:44`, `:60` | comment | reword | slice D2 |
| Oracle on-chain AIS cross-checks | `integrity-oracle/backend/src/handlers.rs:1273-1283` (`onchain_zk_boost_consistent`, `is_zk_boosted`), `:1291` + `:1089-1090`, `:1342-1343` (`onchain_assurance_tier` / `onchain_tier_ceiling`), `chain.rs:62` `IReputationRegistry`, `:445-471` | ZK boost, tier ceiling | **no spec replacement** | 4.6, **owner questions 2 and 4** |
| Oracle leaderboard | `handlers.rs:2200` `refresh_leaderboard_if_stale` (read at `:2224-2232`), `:2266` `get_leaderboard` (`/v1/leaderboard`, description at `:2263`) | `effectiveScore` (0..1000) | **no spec replacement** | 4.6, **owner question 5** |
| SDK ZK commitment | `integrity-sdk/integrity_sdk/chain.py:496-531` `set_zk_identity_commitment` | writes the ZK commitment | **no spec replacement** | slice D1, **owner question 2** |
| SDK primitives tuple | `integrity-sdk/integrity_sdk/chain.py:637`, `:682-688` | the address | removed with `resolve_did` (`:648`) | slice D5 |
| `IntegrityToken` prose | `contracts/src/oracle/IntegrityToken.sol:10`, `:16`, `:19`, `:27` | comment | reword to `StakeVault` | slice D5 |
| `IZkVerifier` / `RejectAllZkVerifier` | `IZkVerifier.sol:17`, `RejectAllZkVerifier.sol:8` | their only callers are `ReputationRegistry` and `VerifierRegistry` | orphaned; fate set by **owner question 2** | slice D5 |

**The gap the spec does not mention.** `AISRegistry` has exactly one writer, `postCheckpoint` with `SCORER_ROLE`.
- In this repository it is called only from tests: `integrity-sdk/tests/test_trust_wiring.py:180` and `tests/v3_onchain.py:90`.
- No Oracle, BCC or SDK production path posts checkpoints. Every repointed reader therefore reads 0 / unset in practice.
- The v2 equivalent did have a writer: the BCC scoring loop pushing to the clone.
- Deleting `ReputationRegistry` without giving `AISRegistry` a writer turns the on-chain AIS from "stale" into "never set". Owner question 3 picks the writer.

## Consumer inventory

`git grep -lE` for the v2 names over integrity-core, outside `docs/superpowers`:
- **Baseline at `c46b63d7`: 259 files.** That count is what the acceptance grep has to drive to the allowed residue.
- The names matched: `XibalbaAgentRegistry`, `AgentPrimitivesFactory`, `AgentProfile`, `StateAnchor`, `ReputationRegistry`, `Slasher`, `VerifierRegistry`, `ComplianceGate`, `IntegrityIdentityReadV1`, `IntegrityERC8004Registry`, `updateAIS`, `PrimitiveSet`, `provisionPrimitives` and `registerCore`.
- Of the 259, 42 are under `docs/archive` and 29 under `docs/wiki`.

### integrity-core: contracts

| Group | Files (refs) | Slice |
|---|---|---|
| Deleted sources | `src/framework/XibalbaAgentRegistry.sol`, `AgentPrimitivesFactory.sol`, `AgentProfile.sol`; `src/oracle/StateAnchor.sol`, `ReputationRegistry.sol`, `Slasher.sol`, `VerifierRegistry.sol`; `src/health/ComplianceGate.sol`; `src/kernel/IntegrityIdentityReadV1.sol`, `IntegrityERC8004Registry.sol` (owner question 7) | D5 |
| `SovereignAgent` | `src/core/SovereignAgent.sol:78-79` (prose), `:88-90` (`factory`), `:98`, `:121-124`, `:236`, `:253-257`, `:307` (`updateAIS`); `src/core/IAccount.sol:23` (`updateAIS` in the interface) | D4 (owner question 1) |
| Surviving contracts, prose only | `core/AllowlistAnchorPolicy.sol:9`, `core/IAnchorPolicy.sol:5`, `framework/AgentRegistry.sol:64`, `framework/XibalbaNameService.sol:72`, `trust/ActionAnchor.sol:9`, `:11`, `trust/StakeVault.sol:13-14`, `trust/TrustConfig.sol:14`, `oracle/IntegrityToken.sol:10-27` | D5: reword to the v3 names |
| `ConstraintExecutionPolicy` | `core/ConstraintExecutionPolicy.sol:13-16` | D4 (same slice as `updateAIS`) |
| Scripts | `script/Deploy.s.sol` (46 refs; `:168` `new XibalbaAgentRegistry`), `DeployEHRGate.s.sol` (14), `DeployProtocolEvidenceAnchor.s.sol` (9), `FixComplianceGateFactory.s.sol` (46), `MediationOk.s.sol` (3), `MigrateSlasherFactory.s.sol` (19), `MigrateVerifierFactory.s.sol` (13), `ReconcileFactoryRoles.s.sol` (10), `RotateOperatorKeyGrant.s.sol` (42) | D5: delete the v2 migration scripts; rewrite `Deploy.s.sol` and `DeployEHRGate.s.sol` |
| Tests | `test/AgentPrimitivesFactory.t.sol` (70), `AgentProfile.t.sol`, `health/ComplianceGate.t.sol`, `IntegrityERC8004Registry.t.sol`, `IntegrityIdentityReadV1.t.sol` (26), `ReputationRegistry.t.sol` (35), `Slasher.t.sol`, `StateAnchor.t.sol`, `VerifierRegistry.t.sol`, `XibalbaAgentRegistry.t.sol`: deleted with their contracts. `PolicyHooks.t.sol` (6), `trust/ProtocolPinnedGate.t.sol` (43), `VaultMerkle.t.sol` (4), `trust/ExecuteGating.t.sol` (2), `SovereignAgent.t.sol` (2), `trust/AgentRegistryGate.t.sol`, `health/EHRGate*.t.sol`: rewritten | D5 |
| Config | `foundry.toml:8`, `:20`, `:33` (the codehash and clone-gas comments), `contracts/.env.example`, `contracts/README.md`, `Makefile:40` | D5 |
| Deployments | `deployments.baseSepolia.json:3` (`cloneTemplates`), `:63-75` (`singletons`; no `AgentRegistry` / `AISRegistry` / `ActionAnchor` entry yet) | D5, after the owner's broadcast |

### integrity-core: Oracle (Rust)

PR 4.6 already owns:
- the route;
- `agent_primitives`;
- `resolve_primitives_by_did`;
- `memory_state`.

The rows below are the **other** v2 readers in the same files. 4.6 cannot compile them away without deciding their replacement.

| Reader | File:line | Proposed replacement | Owner |
|---|---|---|---|
| ZK boost cross-check | `handlers.rs:1273-1283`, `chain.rs:453-471` | drop the field (owner question 2) | 4.6 |
| On-chain assurance tier | `handlers.rs:1089-1090`, `:1291`, `:1342-1343`, `chain.rs:66-68` | drop the fields (owner question 4) | 4.6 |
| Anchor coverage | `handlers.rs:1308-1312`, `chain.rs:561-570` `latest_anchor_activity`, `anchor_coverage.rs:9-151` | `ActionAnchor.epoch(actor)`. It has no timestamp: `ActionAnchor.sol:14-17` exposes only `latestRoot`, `epoch` and the `RootAnchored` event. So use the event's block timestamp, or drop it (owner question 8) | 4.6 |
| Leaderboard | `handlers.rs:2200-2232`, `:2263-2266`, migration-backed cache `0005_leaderboard_cache.sql` | owner question 5 | 4.6 |
| Wallet | `handlers.rs:2343-2347` `get_wallet` (calls `resolve_primitives_row`) | actor from `agent_onchain_records` | 4.6 |
| Compliance vertical | `handlers.rs:2031`, `:2062-2104` (`compliance_vertical`, `is_healthcare_compliant`), `chain.rs:109`, `:478-489`, `derive.rs:226` | owner question 6 | 4.6 |
| v2 interfaces | `chain.rs:5-23`, `:35-47` `IXibalbaAgentRegistry`, `:62` `IReputationRegistry`, `:94-100` `IStateAnchor`, `:109` `IComplianceGate`, `:160-192` `PrimitiveSet`, `:228-254` deployments key, `:373-438` | `AgentRegistry.resolve` only | 4.6 |
| Prose | `merkle.rs:3`, `:52` (the tree format is shared with `ActionAnchor`), `error.rs:65`, `verification.rs:34`, `offchain_registration.rs:4-5`, `db.rs:769`, `:1183`, `:1306`, `handlers.rs:2659`, `:2674`, `:3274-3276`, `:3608` | reword: StateAnchor → ActionAnchor | 4.6 |
| Migrations | `0001_init.sql`, `0005`, `0007_anchor_events.sql`, `0025_compliance_observed.sql` | immutable; leave | — |
| Spec | `spec/ais-api/v1/openapi.yaml` (18 refs), `spec/vault-merkle/vectors.json:1` | with 4.6 (OpenAPI); vectors: reword the label only (the hashes don't change) | 4.6 / D5 |

### integrity-core: BCC middleware

| File | Lines | What it does | v3 |
|---|---|---|---|
| `app/chain.py` | `:50`, `:55`, `:240` | `resolve_agent_primitives` via the Oracle's `GET /v1/agent/{id}` `primitives` | `AgentRegistry.resolve` (spec Part 5) |
| `app/reputation.py` | `:2-3`, `:25`, `:48`, `:131-246` | score push, stake read, dispute (above) | `AISRegistry` / `StakeVault` |
| `app/scoring_loop.py` | `:3`, `:40`, `:65`, `:76`, `:126-202` | reads `primitives.reputation_registry`, `sovereign_agent`, `slasher` | same |
| `app/quarantine.py` | `:4-15`, `:78-104` | `Slasher.lockedStakeOf` | `StakeVault.disputeLockedOf` |
| `app/anchor.py` | `:2`, `:14`, `:60-132` | anchors batch sub-roots into the **protocol evidence `StateAnchor` singleton** (`DeployProtocolEvidenceAnchor.s.sol`) | `ActionAnchor` (owner question 8) |
| `app/merkle.py` | `:6`, `:22`, `:32`, `:99` | the tree format "matches `StateAnchor.sol`" | same tree as `ActionAnchor` (sorted pair); reword |
| `app/config.py` | `:132`, `:140`, `:259-273`, `:289-317`, `:417`, `:423` | contract names, signer keys | rename |
| `app/main.py` | `:13`, `:24`, `:483`, `:527`, `:633-681`, `:903` (`/v1/reputation/sync`), `:995` | wiring, deployment binding | rename; the binding moves in 3.4b |
| `app/schemas.py`, `audit.py`, `receipt_anchor.py` | `:108`, `:114`; `:94`; `:13` | prose and field names | reword |
| `.env.example`, `README.md`, `CLAUDE.md`, `policies/bcc.rego:44`, `:60` | — | docs | reword |
| Tests | `tests/conftest.py`, `helpers.py`, `test_anchor_per_agent.py`, `test_chain_baa_anchor.py`, `test_deployment_binding.py`, `test_evidence_linkage.py`, `test_merkle.py`, `test_quarantine.py`, `test_scoring_loop.py`; fixtures `tests/fixtures/foundry/src/MockReputationRegistry.sol`, `MockSlasher.sol`, `MockStateAnchor.sol` and their `out/` artifacts | — | rewrite against mock `AISRegistry` / `StakeVault` / `ActionAnchor` |

**A dependency the 4.6 plan does not list.** The BCC resolves the Slasher and ReputationRegistry addresses through the Oracle's `primitives` object (`quarantine.py:83-90`, `scoring_loop.py:126`).
- 4.6 removes `primitives` from `AgentResponse`. From then on, every quarantine check returns `CANNOT_VERIFY` and the scoring loop skips every agent.
- **So slice D2 has to merge before 4.6**, or in the same deploy window.
- The `CANNOT_VERIFY` posture is described two ways in `quarantine.py`: fail-open at `:16-20`, "treated identically to QUARANTINED" at `:79-80`. D2 pins it with a test before it changes anything.

### integrity-core: SDK, CLI, scripts

| File | Lines | v2 use | Slice |
|---|---|---|---|
| `integrity_sdk/chain.py` | `:170`, `:245`, `:334-368`, `:409-489`, `:496-531` (ZK), `:549` `state_anchor_latest_root`, `:574` `anchor_vault_root`, `:604` `anchor_genesis_root`, `:637-688` `PrimitivesRegistered` / `resolve_did` | v2 reads and writes | D1 (anchor functions) / D5 (the rest) |
| `integrity_sdk/vault.py` | `:6`, `:15`, `:38`, `:156` | `TrustVault` anchors on StateAnchor | D1 |
| `integrity_sdk/memory.py` | `:105-141`, `:207` | memory root on StateAnchor | D1 |
| `integrity_sdk/evidence_anchor.py` | `:1`, `:8`, `:48`, `:71-73` | evidence anchor | D1 |
| `integrity_sdk/health.py` | `:3`, `:6`, `:147-170` `set_self_declared_compliance` (ComplianceGate) | healthcare | D5 (owner question 6) |
| `integrity_sdk/readiness.py` | `:125-134` | readiness probe | D5 |
| `integrity_sdk/bcc.py` | `:181` | EIP-712 `verifying_contract` = `XibalbaAgentRegistry` | **3.4b** |
| `integrity_sdk/telemetry/derive.py` | `:226-346` | prose and field names | D5 |
| `integrity_sdk/core/merkle.py` | `:3`, `:67`, `:89`; `core/receipts.py:24`, `core/memory.py:9`, `memory_dag.py:334`, `agent_subject.py:14`, `client.py:411`, `:517`, `telemetry/intent.py:238`, `wallet.py:10` | prose | D5 |
| `integrity_sdk/abis/` | `AgentPrimitivesFactory.json`, `ComplianceGate.json`, `ReputationRegistry.json`, `StateAnchor.json`, `XibalbaAgentRegistry.json`; `SovereignAgent.json` (regenerated after D4) | ABIs | D5, via `scripts/sync_abis.py:50-135` |
| `integrity-sdk/pyproject.toml`, `README.md`, `scripts/seed_agent_subjects.py` | — | packaging, docs | D5 |
| SDK tests | `tests/conftest.py`, `test_chain.py` (6), `test_evidence_anchor.py`, `test_health.py`, `test_trust_wiring.py`, `unit/test_core_merkle_jcs.py`, `unit/test_core_receipts.py`, `unit/test_vault.py` | — | D1 / D5 |
| `integrity_cli/chain.py` | `:119-136` | v2 reads | D5 |
| `integrity_cli/vault.py` | `:122-154`, `:267-277` | vault anchor | D1 |
| `integrity_cli/main.py` | `:190`, `:252-266`, `:667` | vault / anchor commands | D1 |
| `integrity_cli/bcc.py` | `:107` | `verifying_contract` | **3.4b** |
| `integrity_cli/verify.py:115`, `wallet.py:11` | — | prose | D5 |
| `integrity_cli/abis/` | `ComplianceGate.json`, `ReputationRegistry.json`, `StateAnchor.json`, `SovereignAgent.json` | ABIs | D5 |
| `integrity-cli/tests/test_main.py`, `README.md` | — | — | D1 / D5 |
| `scripts/anchor_memory_dag.py` | `:9`, `:16`, `:84-102` | memory DAG anchor | D1 |
| `scripts/audit_harness_registry_readback.py` | `:44` | registry readback | D5 |

### integrity-core: docs

- 42 files under `docs/archive` are history. They stay.
- These 29 files describe the v2 graph as current, and slice D6 rewrites or points them at the spec:
  - `docs/wiki` (29);
  - `docs/design` (13), `docs/ecosystem` (4), `docs/guides` (2), `docs/runbooks`, `docs/architecture`;
  - `docs/WHITEPAPER.md`, `docs/SPEC.md`, `docs/INTERFACE_CONTRACT.md`, `docs/M1_M5_MEDIATION.md`, `docs/ENTERPRISE_ADOPTION.md`, `docs/demo-shield-integration.md`, `docs/HANDOFF_GATE_A_2026-09-28.md`;
  - `README.md`, `PRODUCTION_GAPS.md`, `ais-equations.html`, `integrity-oracle/README.md`.
- **Normative text is excluded.** `docs/SPEC.md` and `docs/INTERFACE_CONTRACT.md` §6.x belong to Phase 5, the spec amendment. Those files get a pointer only, never a rewrite here.

### integrity-console

Line numbers are the same on `origin/main` and `origin/fix/ui-consistency`. The live console is the second of those.

| File | Lines | Covered by 4.5? | Slice |
|---|---|---|---|
| `integrity-dashboard/src/components/ui/RegisterAgentModal.tsx` | `:27-44`, `:66`, `:106-376` (41 refs) | yes | 4.5 |
| `src/components/ui/ClaimAgentModal.tsx` | `:70` | yes | 4.5 |
| `src/services/oracle.ts` | `:6-23` (the `PrimitiveSet` type), `:418-435`, `:598` | partly (`:532` is the route) | 4.5 + C1 |
| `src/pages/HealthPage.tsx` | `:85-114`, `:192-194`, `:934-939` | no | C1 |
| `src/components/ui/DIDExplorer.tsx` | `:24`, `:75-79`, `:227` | no | C1 |
| `src/components/tabs/PrivacyPanel.tsx` | `:11`, `:38`, `:69`, `:83` (ZK commitment) | no | C1 (owner question 2) |
| `src/constants.ts` | `:5-6`, `:14-17`, `:28` | no | C1 |
| `src/chain/agent.ts` | `:23`, `:32-34` | no | C1 |
| `src/chain/bytecode.ts:5`, `scripts/sync-chain-bytecode.mjs:6` | SovereignAgent bytecode (changes with D4) | no | C1, after D4 |
| `src/deployments.baseSepolia.json` | 5 refs | no | C1, after the broadcast |
| `src/components/ui/TelemetryStream.tsx:278`, `src/landing/protocolStatus.ts:143`, `src/landing/ControlLoopDiagram.tsx:19` | prose and labels | no | C1 |
| `src/generated/wiki-data.json` | 33 refs | generated | regenerate from core after D6 (never hand-edit) |
| `demo/src/integrity_demo/seed_audit.py:174-187`, `:324`; `heartbeat.py:61`; `demo/tests/test_seed_audit_chain_scope.py` | demo | no | C1 |
| `integrity-userapi/app/oracle_routes.py` | `:69-70` | no | C1 |
| `PRODUCTION_GAPS.md`, `docs/archive/…` | docs | — | C1 / leave |

Following owner decision 1 (2026-11-16), C1 lands on `main` **and** on `fix/ui-consistency`.

### xibalba-shield (`origin/main`)

| File:line | Use | Action |
|---|---|---|
| `scripts/verify_oracle_registration.py:63` | `deployments["singletons"]["XibalbaAgentRegistry"]`: raises a `KeyError` once D5 rewrites the deployments file | S1: read `AgentRegistry`, before D5 |
| `shield/integrity_exporter/exporter.py:105` | comment | S1: reword |

### xibalba-cortex (`origin/main`, read-only here)

There are no code consumers. Every hit is prose or data:
- `docs/architecture/event-hash-chain.md:11`;
- `docs/integrity/xibalba-cortex-crypto-profile-v1.md:14`, `:56`;
- `docs/operations/resource-readiness.md:61`;
- the `docs/archive/2026-08/` files;
- `pending_tasks_content.json:7`.

Action: none required for correctness. A wording PR is optional and needs the owner's Cortex merge approval, because merging Cortex `main` deploys the managed pilot.

### Hooks (`~/.local/share/xibalba-hooks` and `~/.claude/xibalba/`)

**These are live runtime callers.** The 4.6 plan's "not a runtime caller" note was about `registration` only.
- **Entry scripts:**
  - `~/.claude/xibalba/anchor_vault.py:95` (`TrustVault`), `:113-144` (`chain.anchor_vault_root(..., primitives["sovereign_agent"], primitives["state_anchor"])`);
  - `~/.claude/xibalba/session_stop.py:83`, `:103`, `:121-150` (the same call).
  - Both read `~/.integrity/did/<agent>/primitives.json`. When it is missing they already log "cannot anchor" and skip, so they degrade gracefully, but they never anchor for a v3 agent.
- **Vendored SDK** (snapshot core `bb34958`, pre-3.4a):
  - `src/integrity-sdk/integrity_sdk/chain.py`, `vault.py`, `memory.py`, `memory_dag.py`, `health.py`, `bcc.py`, `registration.py`, `agent_subject.py`, `wallet.py`, `core/receipts.py`, plus its tests;
  - ABIs `src/integrity-sdk/integrity_sdk/abis/{AgentPrimitivesFactory,ComplianceGate,ReputationRegistry,StateAnchor,XibalbaAgentRegistry,SovereignAgent}.json`;
  - the same again under `src.prev-bb8cc5a/`.

Action:
- H1 rewrites the two entry scripts to anchor through D1's `ActionAnchor` helper.
- The snapshot is rebuilt in the same lockstep move as 3.4b. The `verifying_contract` move and the anchor move must ship in one snapshot, or the hooks sign against one registry and anchor against another.

## Boundary with 4.6

4.6 owns everything in the Oracle (Rust) table above. This plan adds rows to 4.6's `agent_primitives` reader table rather than opening a competing Oracle PR:
- leaderboard;
- `get_wallet`;
- the ZK and tier cross-checks;
- anchor coverage;
- the compliance vertical;
- the v2 `chain.rs` interfaces.

Reason: 4.6 deletes `resolve_primitives_row` (`handlers.rs:2139`), and `get_wallet` (`:2347`) and the leaderboard (`:2224`) call it, so 4.6 cannot compile without deciding them.

**4.6 cannot start until owner questions 2, 4, 5, 6 and 8 are answered.**

## Ordered slices

Each slice is its own PR, merged on green CI with `--match-head-commit`. The cross-repo slices (C1, S1) merge in their own repos.

| # | Slice | Repo | Depends on |
|---|---|---|---|
| D0 | this plan | core | — |
| D1 | SDK/CLI anchoring onto `ActionAnchor` (vault, memory, evidence anchor, memory DAG script); ZK commitment per owner question 2 | core | owner question 8 |
| H1 | hook entry scripts + snapshot rebuild | `~/.claude/xibalba`, hooks | D1 merged, **3.4b** (same snapshot) |
| D2 | BCC middleware onto `AgentRegistry` / `AISRegistry` / `StakeVault` / `ActionAnchor` | core | owner questions 3 and 8; **must merge before 4.6** |
| 4.6 | (Phase 4 plan) plus the rows added above | core | 4.3, 4.5, D2; owner questions 2, 4, 5, 6, 8 |
| S1 | Shield script reads `AgentRegistry` | xibalba-shield | before D5 |
| D4 | `SovereignAgent`: `factory` → `registry`, remove `updateAIS` / `ais`; `IAccount.updateAIS`; `ConstraintExecutionPolicy` → `AISRegistry.latest` | core | **owner question 1**; **before the Base Sepolia broadcast** |
| D5 | delete the contracts, v2 scripts, tests, ABIs; rewrite `Deploy.s.sol`, `DeployEHRGate.s.sol`, `test_trust_wiring.py`; prose rewording; kernel views per owner question 7 | core | D1, D2, D4, 4.6, S1, **3.4b** |
| C1 | console + userapi + demo off the v2 graph | integrity-console (`main` and `fix/ui-consistency`) | 4.5, D4 (bytecode), D5 (ABIs) |
| D6 | docs and wiki rewrite or pointer; regenerate console `wiki-data.json` | core, console | D5 |
| — | fresh Base Sepolia deploy | owner | D4, D5, the credential rotation |

### D1: SDK/CLI anchoring onto `ActionAnchor`

**Today:**
- `chain.anchor_vault_root` (`chain.py:574`) and `anchor_genesis_root` (`:604`) call `StateAnchor.anchorRoot` on the agent's clone, through `SovereignAgent.execute`.
- `TrustVault` (`vault.py`), `memory.py`, `evidence_anchor.py`, `scripts/anchor_memory_dag.py` and the CLI's `vault anchor` (`integrity_cli/vault.py:122-154`, `main.py:252-266`) all depend on it.

**Change:**
- Anchor via `SovereignAgent.execute(ActionAnchor, anchorRoot(root))`. `ActionAnchor` keys on `msg.sender`, so the root lands under the actor (spec Part 5, "keyed by their actor").
- Verify with `ActionAnchor.verifyLeaf(actor, leaf, proof)` (`ActionAnchor.sol:33`).
- An agent with no actor gets a typed `NO_ACTOR` result and no transaction (owner question 8b).

**Acceptance:**
- `git grep -nE 'StateAnchor|state_anchor' -- integrity-sdk/integrity_sdk integrity-cli/integrity_cli scripts/anchor_memory_dag.py` is empty.

**Tests that can fail:**
- On Anvil: anchor a root as a bound actor, then `ActionAnchor.latestRoot(actor) == root` and `verifyLeaf` is true for a member leaf and false for a non-member.
- Mutation: anchoring from the guardian EOA instead of through `execute` puts the root under the wrong key, and the `latestRoot(actor)` assertion fails.
- No-actor agent: no RPC write is attempted (an RPC stub that raises on `eth_sendRawTransaction`).

### H1: hooks

**Change:**
- `anchor_vault.py` and `session_stop.py` stop reading `primitives.json`.
- They resolve the actor from `AgentRegistry.resolveDID`, the same read `status_cmd.onchain_rows` uses, and call D1's helper.
- The snapshot is rebuilt from a core commit containing D1 **and** 3.4b.

**Acceptance:**
- `grep -rn primitives ~/.claude/xibalba/*.py` is empty.
- `SNAPSHOT` names a core SHA that contains both D1 and 3.4b.
- A session stop logs either an anchored tx or `NO_ACTOR`. It never logs "no primitives.json".

**Test that can fail:** a hook unit test with a fake registry returning `actor = 0x0` asserts the `NO_ACTOR` log line and zero transactions.

### D2: BCC middleware

**Change:**
1. `app/chain.py` resolves via `AgentRegistry` (`resolve(fingerprint)` / `resolveDID`). It no longer reads the Oracle `primitives`.
2. Quarantine reads `StakeVault.disputeLockedOf(actor)` via `AgentRegistry.trustConfig()` → `stakeVault()`.
3. The dispute path calls `StakeVault.raiseDispute` (`DISPUTER_ROLE`).
4. The score push becomes `AISRegistry.postCheckpoint`, if owner question 3 picks the BCC.
5. The evidence anchor targets `ActionAnchor` (owner question 8a).
6. The mock contracts in `tests/fixtures/foundry/src/` are replaced by mocks of the three v3 singletons.

**Acceptance:**
- `git grep -nE 'Slasher|ReputationRegistry|StateAnchor|reputation_registry|state_anchor|slasher' -- bcc_middleware ':!**/out/**'` is empty.
- `bcc_middleware` tests are green.

**Tests that can fail:**
- **Quarantine:** `disputeLockedOf(actor) = 1` gives QUARANTINED.
  - Mutation: reading `stakeOf(actor).locked` instead gives ALLOW for an agent with an open dispute and zero action locks, so the test fails.
- **CANNOT_VERIFY posture:** a test pins the caller's posture on an unreachable registry. The behaviour is not changed in this PR; the test records what it is.
- **Score:** a 0..1000 AIS of 850 is posted as `8500` bps.
  - Mutation: posting the raw 850 fails the assertion.
- **Ordering guard:** with the Oracle returning no `primitives` (4.6's response shape), quarantine still returns a definite status. On today's code this test fails with `CANNOT_VERIFY`, which proves it can fail.

### D4: `SovereignAgent` (owner question 1)

**Change**, one contract slice:
- `factory` → `registry` (`SovereignAgent.sol:88-90`, `:98`, `:121-124`, `:253-257`);
- delete `updateAIS` and `ais` (`:78-79`, `:307`) and `IAccount.updateAIS` (`IAccount.sol:23`);
- `ConstraintExecutionPolicy` reads `AISRegistry.latest(agent).score` in bps (`ConstraintExecutionPolicy.sol:13-16`);
- the v2 comments at `:236`, `:256` go.

**Why it is its own slice, and why it needs explicit approval:**
- `SovereignAgent` has been treated as frozen, because the canonical codehash is pinned. `AgentRegistry` learns it in its constructor (`AgentRegistry.sol:117`, checked at `:310`).
- **Any** byte change, comments included (they feed the metadata hash), changes the codehash. Every actor bound to an `AgentRegistry` deployed before D4 then fails `isCanonicalAgent`.
- Today that is Anvil only: Base Sepolia has no `AgentRegistry`.
- So D4 must merge **before** the owner's Base Sepolia broadcast. Doing it after means redeploying `AgentRegistry` and re-binding every actor.

**Acceptance:**
- `forge test` is green.
- `grep -nE 'updateAIS|function ais|factory' contracts/src/core/SovereignAgent.sol contracts/src/core/IAccount.sol` is empty.
- The console's `src/chain/bytecode.ts` is regenerated in C1.

**Tests that can fail:**
- `ConstraintExecutionPolicy` with `minAis = 5000`:
  - an agent whose `AISRegistry` checkpoint is 4999 is denied;
  - an agent at 5000 is allowed.
  - Mutation: reading a constant 10000 lets the 4999 agent through.
- A registry deployed **before** a one-byte `SovereignAgent` edit rejects an agent deployed **after** it (`bindActor` reverts `NotCanonicalAgent`). This documents why the slice is ordered before the broadcast.

### D5: contract and ABI deletion

**Change:**
- Delete the ten contracts listed under "Deleted sources" (the two kernel views per owner question 7), their tests and the v2 migration scripts.
- Rewrite `Deploy.s.sol`, stopping at the `new XibalbaAgentRegistry` at `:168`, plus `DeployEHRGate.s.sol` and `test_trust_wiring.py`.
- Remove `DeployProtocolEvidenceAnchor.s.sol` (D2 moved its user).
- Delete the SDK/CLI ABIs and re-run `scripts/sync_abis.py`.
- Delete `chain.py`'s `resolve_did` / `PrimitivesRegistered`.
- Reword the surviving-contract prose.
- Rewrite `deployments.baseSepolia.json` from the owner's broadcast output, or leave it with only an `AgentRegistry`-era layout if the broadcast has not happened. **No hand-written addresses.**

**Acceptance**, the spec's Phase 3 grep, now complete:
```
git grep -lE 'XibalbaAgentRegistry|AgentPrimitivesFactory|AgentProfile\b|StateAnchor|ReputationRegistry|\bSlasher\b|VerifierRegistry|ComplianceGate|IntegrityIdentityReadV1|IntegrityERC8004Registry|updateAIS|PrimitiveSet|provisionPrimitives|registerCore|registerPrimitives|agent_primitives' \
  -- ':!docs/superpowers' ':!docs/archive' ':!**/migrations/**'
```
- It must return only the files D6 still owns, and D6 must leave it **empty**.
- The baseline is 259 files at `c46b63d7`, and the PR body records the before and after counts.
- `forge build --force && forge test` must be green (forge reproducibility note: force after config changes).
- The deploy wiring test must pass on a fresh Anvil.

**Tests that can fail:**
- The rewritten `test_trust_wiring.py` asserts `AISRegistry.agentRegistry() == AgentRegistry` and `TrustConfig.stakeVault() == StakeVault` on a fresh Anvil deploy.
  - Mutation: dropping the `setAgentRegistry` call from `Deploy.s.sol` fails it.
- `sync_abis.py --check` (or a test over its output) fails if a deleted contract's ABI is still present.

### C1: console

**Change:**
- `HealthPage`, `DIDExplorer`, `PrivacyPanel`, `constants.ts`, `chain/agent.ts` and `oracle.ts` read the v3 record, i.e. the 4.3 `onchain` object.
- `bytecode.ts` is regenerated after D4.
- `src/deployments.baseSepolia.json` follows core.
- userapi `oracle_routes.py:69-70` and the demo scripts move too.
- The change lands on `main` and is cherry-picked to `fix/ui-consistency`.

**Acceptance:**
- the same grep over `integrity-dashboard/src`, `integrity-userapi` and `integrity-dashboard/demo/src` is empty on **both** branches;
- `npm run build` and lint are green;
- the live bundle has none of the names (check the deployed `index-*.js`).

**Test that can fail:** a Vitest render of `DIDExplorer` with an Oracle response carrying `onchain` and **no** `primitives` shows the actor. On today's code it renders the empty-primitives state.

### S1: Shield

**Change:** `scripts/verify_oracle_registration.py:63` reads `AgentRegistry` from the deployments file, and `exporter.py:105` is reworded.

**Test that can fail:** a unit test feeding a deployments file without `XibalbaAgentRegistry`. Today it raises `KeyError`.

### D6: docs

**Change:**
- Rewrite, or replace with a one-line pointer to the v3 spec, the files in "integrity-core: docs" above.
- `docs/SPEC.md` and `INTERFACE_CONTRACT.md` get a pointer to Phase 5 only.
- Regenerate the console `wiki-data.json` from core.

**Acceptance:** the D5 grep is empty.

## Dependencies on 4.6 and 3.4b

- **4.6 → D5.** D5 deletes `chain.rs`'s v2 interfaces' Solidity sources and ABIs, so the Oracle must have stopped reading them first.
- **D2 → 4.6.** Explained under the BCC middleware section: after 4.6 the BCC can no longer resolve the Slasher or score-board addresses.
- **3.4b → H1, D5.**
  - 3.4b moves the EIP-712 `verifying_contract` from `XibalbaAgentRegistry` to `AgentRegistry` (`integrity_sdk/bcc.py:181`, `integrity_cli/bcc.py:107`, BCC `main.py` deployment binding), in lockstep with the hooks snapshot.
  - D5 deletes `XibalbaAgentRegistry` and rewrites the deployments file the binding reads. Doing that before 3.4b leaves the BCC with no registry address to bind against: the conditional check silently stops denying mismatches.
  - H1 rebuilds the snapshot, and 3.4b needs the same rebuild. One rebuild, not two.
- **D4 → broadcast.** Explained under D4.

## Out of scope

- Any code, contract or deploy change. This document is a plan.
- PR 3.4b itself, and Phase 4 PRs 4.3–4.6, except the reader rows this plan adds to 4.6.
- The Base Sepolia broadcast and the credential rotation (owner).
- Phase 5: the normative spec amendment to v0.3 §4.1/§6/§7.1 and INTERFACE_CONTRACT §6.1–§6.3a.
- Contracts the spec keeps: `EHRGate`, `SmartBAA`, `SmartBAAFactory`, `CoveredEntityRegistry`, `HIPAAGuardrailRegistry`, `DomainRegistry`, `XibalbaNameService`, `AgentLineageRegistry`, `IntegrityToken`, and the trust singletons.
- Codex's second identity.
- xibalba-cortex wording (optional; needs Cortex merge approval).

## Owner questions

Each has options. The recommendation comes first.

1. **Edit `SovereignAgent`** (rename `factory` → `registry`, remove `updateAIS` / `ais`)? This is the one contract we treat as frozen. Editing it changes the codehash `AgentRegistry` pins.
   - a. **Yes, as slice D4, merged before the Base Sepolia broadcast** (recommended; today it costs nothing, since only Anvil has an `AgentRegistry`).
   - b. Keep the name `factory` forever and remove nothing. This needs a spec amendment, since Part 5 says "removed now"; `ConstraintExecutionPolicy` keeps reading `ais()`, which no one writes after D2.
   - c. Do it after the broadcast. This redeploys `AgentRegistry` and re-binds every actor.
2. **ZK identity commitment and attestation** (`ReputationRegistry.setZkIdentityCommitment` / `submitZkAttestation` / `isZkBoosted`, SDK `chain.py:496`, console `PrivacyPanel`, Oracle `onchain_zk_boost_consistent`). The verifier is `RejectAllZkVerifier`, so nothing has ever passed.
   - a. **Drop it now**, with `IZkVerifier`, `RejectAllZkVerifier` and the `UltraPlonkVerifier` entry, and re-add it later as an `AISRegistry` evidence input (recommended).
   - b. Move the commitment onto the `AgentRegistry` record (a contract and spec change).
   - c. Keep a slimmed `ReputationRegistry` for ZK only (contradicts Part 5).
3. **Who writes `AISRegistry`?** No production code posts checkpoints today, so every repointed reader reads "unset".
   - a. **The BCC scoring loop, repointed in D2** (it already has the signer key and the loop; it needs `SCORER_ROLE` granted at deploy) (recommended).
   - b. The Oracle posts checkpoints itself (a new Rust signer path, and a key on Render).
   - c. Nobody for now. On-chain AIS stays unset and the gates keep `minAis = 0`.
4. **On-chain assurance tier** (`onchain_assurance_tier` / `onchain_tier_ceiling` in `GET /v1/agent/{id}/ais`):
   - a. **Drop the fields.** The spec says tier is Oracle-vouched identity, so there is nothing on chain to read (recommended).
   - b. Keep them as always-`null` for one API version.
5. **Leaderboard** (`/v1/leaderboard`, ranked by the clone's `effectiveScore`):
   - a. **Rank by the Oracle's own off-chain AIS.** This covers off-chain agents, which are most of them (recommended).
   - b. Rank by `AISRegistry.latest(actor).score`, which covers actor-bound agents only.
   - c. Delete the endpoint.
6. **Healthcare compliance vertical after `ComplianceGate`** (`GET /v1/agent/{id}/compliance`, SDK `health.set_self_declared_compliance`, `DeployEHRGate.s.sol`). `EHRGate`, `SmartBAA` and `CoveredEntityRegistry` stay.
   - a. **Drop the self-declared vertical.** `/compliance` answers from `SmartBAA` / `EHRGate` state keyed by the actor (recommended; the self-declared switch was the agent vouching for itself).
   - b. Drop the healthcare vertical from `/compliance` entirely, for now.
   - c. Keep a `ComplianceGate` singleton keyed by actor (contradicts Part 5).
7. **Kernel read views** `IntegrityIdentityReadV1`, `IntegrityERC8004Registry`. They have no off-chain consumer, and the kernel was archived in #226.
   - a. **Delete them** (recommended).
   - b. Rewrite them over `AgentRecord`, as Part 5 says.
8. **Anchoring without per-agent `StateAnchor`s:**
   - (a) The BCC protocol-evidence anchor today is a `StateAnchor` singleton. `ActionAnchor` keys on `msg.sender`, so the BCC would anchor under **its own signer address**: one slot for the service, with per-agent sub-roots as leaves.
     - **Accept that** (recommended).
     - Or keep a renamed singleton `EvidenceAnchor`, the same code under a new name.
     - Or stop on-chain BCC anchoring.
   - (b) An agent with no actor (Claude today is off-chain) cannot anchor its vault in v3.
     - **Skip with `NO_ACTOR`**; the vault stays local and verifiable off-chain (recommended).
     - Or anchor from the guardian EOA under its own address, which breaks "keyed by actor".
   - (c) Anchor coverage on the Oracle (`anchor_coverage.rs`): `ActionAnchor` has no timestamp.
     - **Use the `RootAnchored` event's block time** (recommended).
     - Or drop anchor coverage.
