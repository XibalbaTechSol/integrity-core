# Integrity Protocol v2.0.0 — Proposed Development Specification

**Status:** Proposed; non-normative until explicitly accepted
**Version:** 2.0.0-proposed
**Date:** 2026-09-12
**Author:** Jacob S. Vickers, Xibalba Solutions, LLC
**Supersedes:** Nothing. `docs/SPEC.md` remains the active normative specification.
**Source material:** `docs/WHITEPAPER.md` v3.2, current Core source, current Cortex and Shield specifications, and the 2026-09-12 architecture audit.

> This document is a development target, not evidence that the target has been implemented, tested, deployed, or accepted. A status tag applies to the nearest requirement or table row.

## 1. Authority and status

Implementations continue to claim conformance only against `docs/SPEC.md` until this proposal is reviewed, accepted, and recorded in `docs/DOCUMENT_STATUS.yaml`. The v3.2 whitepaper remains explanatory. This proposal may guide additive implementation before acceptance, but it must not be used to claim a new public protocol guarantee.

Status tags used here:

| Tag | Meaning |
|---|---|
| `[PROPOSED]` | Target behavior for this proposed major version; not active normative behavior. |
| `[BUILT]` | Observed in current source or a named repository. This is not automatically tested, deployed, or production-ready. |
| `[PARTIAL]` | A meaningful implementation exists, but an acceptance boundary or required sub-behavior is missing. |
| `[EXPERIMENTAL]` | Exists as a non-production or non-deployed slice. It MUST NOT be described as the live path. |
| `[PLANNED]` | Required target behavior with no verified implementation. |
| `[UNVERIFIED]` | A claim may be present in source, configuration, or documentation, but the required independent evidence is missing. |
| `[BLOCKED]` | Verification or implementation is currently prevented by a named dependency or decision. |
| `[LEGACY]` | Historical behavior retained for compatibility and migration; it is not the target model. |

Evidence classes are separate:

```text
implemented ≠ tested ≠ deployed ≠ observed live ≠ accepted normative behavior
```

A signature, hash, Merkle proof, or StateAnchor proves only the limited bytes or relationship covered by its construction. It does not independently prove truth, authorization, ownership, execution, completeness, or legal identity.

## 2. Purpose and design thesis

Integrity Protocol v2 proposes a clean separation between public agent interoperability, execution assurance, endpoint security, and memory security.

> **ERC-8004 identifies and helps discover an agent. Integrity constrains admissible execution and preserves evidence. Cortex protects multi-agent memory boundaries. Shield protects devices and endpoints.**

The system MUST preserve the following distinctions:

1. Public agent discovery is not execution authorization.
2. A logical agent subject is not a verification key, controller, deployment, runtime, session, device, tenant, or operator.
3. A memory identifier is not proof that the caller may access that memory.
4. A signed declaration is not proof that the declared action executed or produced its claimed outcome.
5. A local implementation or unit test is not proof of live chain deployment or cross-repository interoperability.
6. v3.2 architecture is explanatory source material until its proposed semantics are accepted through this versioned process.

## 3. System boundaries

```text
                         public interoperability
                    ERC-8004 agentId + agentURI
                                  │
                                  ▼
                         Integrity AgentSubject
              ┌───────────────┬───────────────┬───────────────┐
              ▼               ▼               ▼               ▼
        verification      deployments     runtimes       tenant grants
           keys             and artifacts   and sessions   and operators
              │               │               │               │
              └───────────────┴──────┬────────┴───────────────┘
                                     ▼
                              Integrity evidence
                         BCC · policy · Oracle · AIS
                           StateAnchor · execution
                                     │
                    ┌────────────────┴────────────────┐
                    ▼                                 ▼
              Shield device boundary              Cortex memory boundary
          posture · enrollment · endpoint        storage · retrieval · provenance
```

### 3.1 Integrity Core

Integrity Core owns protocol primitives, behavioral assurance, authorization semantics, evidence schemas, Oracle validation, Agent Integrity Score (AIS), StateAnchor integration, and interoperability profiles.

Core MUST NOT import or require Shield or Cortex to define its base protocol. Shield and Cortex consume Core contracts through explicit adapters.

### 3.2 Shield

Shield is the endpoint-security product. It owns device sensing, enrollment, posture, local enforcement, installation credentials, and device-bound recovery. Shield MAY publish or consume an agent discovery handle, but its device identity MUST remain separate from a portable logical runtime identity.

Shield MAY be deployed in three operator-selected forms: edge-only, cloud-only, or hybrid. In hybrid mode, each enrolled device has exactly one device-scoped logical Shield agent composed of a device-bound edge runtime and one or more paired cloud runtime instances. The edge runtime owns local sensing, enforcement, offline behavior, and device-originated evidence. Cloud runtimes provide control-plane coordination, fleet management, analytics, and Cortex integration; they do not become evidence that an action occurred on the device.

The one-agent-per-device rule applies to the logical Shield agent, not to the number of cloud processes. A multi-tenant cloud service MAY host many cloud runtime instances, but it MUST preserve tenant, device, agent, deployment, and runtime separation. Edge and cloud runtimes MUST use distinct purpose-bound keys and MUST authenticate their pairing. A cloud-originated command MUST be attributable to its cloud principal and accepted by the edge only after local policy, freshness, replay, and pairing checks succeed.

### 3.3 Cortex

Cortex is the memory and provenance system. It owns canonical memory storage, source lineage, graph and vector projections, retrieval traces, inference task boundaries, retention, forgetting, and memory access authorization.

Cortex is not the public identity registry and is not an Integrity verifier. It MUST NOT authorize a caller solely because a supplied agent identifier exists.

## 4. Canonical identity model

### 4.1 Identity objects

The target model defines these separate objects:

| Object | Meaning | Authority |
|---|---|---|
| `ERC8004AgentRef` | Qualified public registry, chain, and `agentId` reference | ERC-8004 registry, once an exact revision is pinned |
| `AgentSubject` | Stable logical subject represented by the public agent handle | Integrity subject registry/profile |
| `VerificationKey` | Purpose-bound key that signs evidence or authenticates a runtime | Integrity key lifecycle |
| `Controller` | EVM account or controller authorized for a defined operation | On-chain contract and authorization policy |
| `Deployment` | Versioned artifact, configuration, dependency, and policy binding | Integrity deployment record |
| `RuntimeInstance` | Concrete worker, process, workload, or cloud execution instance | Runtime/controller evidence |
| `Session` | Conversation or bounded execution context | Runtime and Cortex session records |
| `DeviceBinding` | Optional Shield installation/device relationship | Shield enrollment and Integrity evidence |
| `Tenant` | Administrative and data-isolation boundary | Cortex authorization plane |
| `Principal` | Human, service, or runtime credential making a request | Authenticated authorization layer |
| `Operator` | Administrative actor with explicitly granted management scope | Tenant membership and audit policy |

The following relationships are normative targets:

```text
ERC8004AgentRef
  └── AgentSubject
        ├── current and historical VerificationKeys
        ├── Controllers and controller history
        ├── Deployments
        ├── RuntimeInstances
        ├── Sessions and Invocations
        ├── Tenant memberships
        └── optional Shield DeviceBindings
```

A key rotation MUST NOT silently create a new portable logical subject. A deployment, runtime instance, or session MUST NOT silently create a new public agent identity.

### 4.2 Public and internal identity

`ERC8004AgentRef` is the proposed public discovery handle. `AgentSubject` is the Integrity-native stable subject below it. The mapping MUST be explicit, auditable, versioned, and lossless for historical references.

The current key-derived identifier remains:

```text
did:integrity:<sha256(raw Ed25519 public key)>
```

`did:integrity:` is a verification-key or identity-document reference under this proposal, not the sole durable portable-agent subject. Existing DIDs MUST remain readable and linkable during migration.

### 4.3 Key lifecycle

A conforming implementation target MUST define for every verification key:

- key identifier and purpose;
- public key and algorithm;
- activation time and optional expiry;
- predecessor and successor, when rotated;
- revocation time and reason;
- authorized tenant, agent subject, deployment, or runtime scope;
- evidence and canonicalization profile;
- recovery and replacement procedure.

Missing or inconsistent key state MUST fail closed. Ordinary startup MUST NOT generate a replacement key. Explicit key replacement requires a separately authorized lifecycle operation and an auditable successor relationship.

### 4.4 Shield device identity

Shield installation identity is intentionally device-bound. Same-device repair SHOULD restore the original installation identity. A new physical device requires explicit enrollment or an audited successor relationship.

Machine identity MUST NOT determine the portable agent subject, ERC-8004 `agentId`, Cortex tenant, or Integrity kernel address. A device binding is execution context and endpoint evidence, not a universal identity.

### 4.5 Shield hybrid deployment modes

The deployment mode is an explicit product choice:

| Mode | Required runtime | Permitted role |
|---|---|---|
| `edge_only` | One device-bound edge runtime | Local sensing, enforcement, offline queueing, and signed device evidence |
| `cloud_only` | One cloud runtime subject | Cloud-hosted agent protection and control-plane policy; no claim of physical-device coverage unless a separately verified device binding exists |
| `hybrid` | One device-bound edge runtime plus paired cloud runtime instance(s) | Local enforcement and device evidence combined with cloud coordination, fleet, analytics, and Cortex services |

Users MAY choose any mode according to their needs. A user MAY operate edge-only Shield on a sensitive or disconnected device, cloud-only Shield for workloads that never require endpoint enforcement, or hybrid Shield when local containment and cloud coordination are both required. Changing mode MUST be recorded as a deployment/lifecycle event and MUST NOT silently replace the logical Shield agent or its device binding.

In all modes, a device-bound evidence claim requires evidence from the enrolled edge runtime. Cloud logs, cloud model output, or a cloud session alone MUST NOT be upgraded into device-originated evidence.

## 5. ERC-8004 interoperability profile

### 5.1 Revision pinning

`[PARTIAL]` The implementation pins an exact ERC-8004 draft revision with a retrievable source identifier and content hash — closed 2026-09-12 (tri-repo audit's §9 correction: this row was `[PLANNED]`, but a revision was already pinned in source; only the content hash was missing).

Pinned revision: `ethereum/ERCs@503591a6e80e6e1affdd6403341e25269141f046/ERCS/erc-8004.md`
— git blob `7653a80922c0bf0243669f30e7a2d4aabfe006aa`,
sha256 `249dc3d96ad7bbe4afd25cacd14be942eb87751abcf1608bab19a610f3c3f8a9` (24470 bytes).
Retrieved via `gh api repos/ethereum/ERCs/contents/ERCS/erc-8004.md?ref=503591a6e80e6e1affdd6403341e25269141f046`;
`git hash-object` on the fetched bytes reproduced the blob hash, so the sha256 above is
independently verifiable against the pinned commit, not merely asserted. Recorded in
`docs/INTERFACE_CONTRACT.md` §6.1a and `contracts/src/kernel/IntegrityERC8004Registry.sol`'s header.

Still `[PLANNED]`: this pins the revision only. `isERC8004Conformant()` returning a hardcoded
`true` (tri-repo audit §7.3) is a separate, unresolved conformance-claim defect — pinning the
revision does not establish that the contract actually conforms to it.

Until semantic conformance against the pinned revision is independently tested (§5.2):

- `IntegrityERC8004Registry` MUST be described as an Integrity-specific implementation with ERC-721-shaped behavior, not as proven ERC-8004 conformance;
- `IntegrityIdentityReadV1` MUST remain explicitly custom and non-ERC-8004/non-ERC-721;
- source-level `isERC8004Conformant()` claims MUST NOT be used as independent evidence.

### 5.2 Standard boundary

After revision pinning, exact compatibility MUST be tested independently for:

- registration flow and incrementally assigned identity semantics;
- `agentId` and registry identifier encoding;
- owner/controller semantics;
- transfers and approvals;
- `agentURI` mutation and events;
- registration-file retrieval and schema;
- `agentWallet` proof and mutation behavior;
- ERC-165 interface detection;
- unauthorized operations;
- negative-conformance cases.

A local test that passes custom soulbound or DID-hashed behavior does not satisfy these gates if the pinned draft requires different semantics.

### 5.3 Registration document

An Integrity registration file SHOULD use standard ERC-8004 fields and a namespaced extension:

```json
{
  "type": "https://eips.ethereum.org/EIPS/eip-8004#registration-v1",
  "name": "Xibalba Agent",
  "description": "Integrity-governed autonomous agent",
  "services": [
    {"name": "MCP", "endpoint": "https://agent.example/mcp"},
    {"name": "A2A", "endpoint": "https://agent.example/.well-known/agent-card.json"}
  ],
  "supportedTrust": ["reputation", "validation"],
  "integrity": {
    "profile": "xibalba.integrity.agent.v1",
    "subject": "integrity:subject/[REDACTED]",
    "evidenceProfile": "xibalba.integrity.bcc.v1",
    "currentKeySet": "ipfs://[REDACTED]",
    "oracle": "eip155:84532:0x[REDACTED]",
    "stateAnchor": "eip155:84532:0x[REDACTED]",
    "cortex": "https://agent.example/integrity"
  }
}
```

The namespaced object MUST NOT redefine ERC-8004 ownership, transfer, wallet, or registration semantics. It provides Integrity-specific references only.

### 5.4 Reputation and evidence

ERC-8004 feedback is an interoperability input or publication surface. It is not interchangeable with:

- Behavioral Commitment Chain (BCC) intent;
- policy authorization;
- execution evidence;
- outcome evidence;
- Oracle verification;
- StateAnchor finality;
- Cortex provenance;
- AIS.

Integrity MAY publish validated assessments through an interoperable registry, but arbitrary external feedback MUST NOT automatically authorize execution or raise an Integrity assurance tier.

## 6. Account, kernel, and execution model

### 6.1 Existing kernel status

`[BUILT][EXPERIMENTAL]` `contracts/src/kernel/IntegrityKernel.sol` implements native and token budgets, reputation and assurance gates, adapter-registry checks, stale snapshots, reentrancy protection, hook lifecycle behavior, and gas-bound logic.

`[BUILT][EXPERIMENTAL]` `contracts/src/kernel/IntegrityAccount.sol` implements a single-hook account, timelocked kernel swaps, guardian quorum controls, rescue behavior, EntryPoint validation, and swap reentrancy protections.

`[PARTIAL]` The kernel/account path is not the same as the production `SovereignAgent.execute()` path. Production currently uses `ConstraintExecutionPolicy`; kernel integration into the production account remains a separate development decision.

`[UNVERIFIED]` The historical Base Sepolia deployment manifest does not prove that the current kernel source is deployed. A deployment record MUST bind address, chain, bytecode or artifact hash, source commit, constructor parameters, and independent chain readback.

### 6.2 Target execution contract

`[PROPOSED]` Every value-bearing account state transition MUST pass through an identified Integrity enforcement boundary that:

1. binds the call to the stable `AgentSubject` and authorized account;
2. checks the current kernel/policy epoch and replay nonce;
3. evaluates the post-state constraint vector;
4. applies finite budgets and reputation/assurance gates where configured;
5. rejects on timeout or unavailable mandatory verification;
6. emits or stores separately attributable intent, authorization, dispatch, execution, and outcome evidence.

AIS MAY parameterize finite constraints. AIS MUST NOT independently convert a denial into an allow decision.

### 6.3 Kernel test and verification gates

Before calling the kernel production-ready, the following MUST pass against one identified source tree:

- concrete account and kernel tests;
- registry-disabled and registry-enabled paths;
- denial biconditionals and anti-vacuity mutations;
- gas-ceiling tests for each configured adapter path;
- kernel swap lifecycle and guardian recovery tests;
- formal properties for each enabled configuration;
- clean-build artifact and ABI verification;
- deployment and chain readback, if deployed.

Current audit finding: the focused account and registry-hook fixtures fail during setup with `Unauthorized(...)`, consistent with an account creation-nonce prediction mismatch after deploying the kernel first. This is an open test defect, not a verified kernel-logic failure.

## 7. Evidence and authorization

### 7.1 Evidence classes

The following records MUST remain distinct:

```text
signed declared intent
inferred or reported intent
authorization / policy decision
host-tool dispatch evidence
execution observation
outcome evidence
Cortex source and derived memory
Merkle inclusion
StateAnchor confirmation
```

Only a validly verified BCC record may receive the authoritative `declared_intent` class. Unsigned prompts, summaries, embeddings, or inferred rationale MUST NOT be promoted into that class.

### 7.2 Behavioral Commitment Chain

BCC records SHOULD contain exact action, target, scope, data exposure, expected postcondition, rollback, expiry, and approver fields when approval is required. Xibalba MUST NOT approve its own commitment.

A policy result of `allowed` proves only the policy result. It does not prove that the host dispatched the tool, that the tool executed, or that the outcome succeeded.

### 7.3 Replay and lifecycle controls

`[PLANNED]` Every authorization and evidence path MUST define domain separation, monotonic sequence or nonce, expiry, duplicate handling, revocation behavior, and conflict behavior. Gaps, replay attempts, omitted sequences, and ambiguous delivery MUST remain observable.

## 8. Cortex multi-agent memory specification

### 8.1 Scope

The target Cortex model expands beyond the current local single-user v1. Cortex MUST support multiple agent subjects while preventing accidental or unauthorized cross-agent memory access.

The security key is:

> **Identity tells Cortex whose memory an object represents. Authorization tells Cortex who may touch it.**

Cortex MUST remain a memory/provenance provider, not an identity authority or final execution verifier.

### 8.2 Required security dimensions

Every source, memory, entity, relation, attachment, embedding, telemetry event, inference task, retrieval trace, export, and Integrity link MUST be associated with the applicable dimensions:

```text
tenant_id
agent_subject_id
session_id or invocation_id, where applicable
deployment_id and runtime_instance_id, where applicable
device_binding_id, where applicable
created_by_principal
visibility
provenance references
```

These fields MUST remain semantically distinct:

| Field | Meaning |
|---|---|
| `tenant_id` | Organizational and data-isolation boundary |
| `agent_subject_id` | Logical agent whose activity or memory is represented |
| `principal_id` | Authenticated caller making the request |
| `deployment_id` | Versioned artifact/configuration/policy context |
| `runtime_instance_id` | Concrete worker or workload |
| `device_binding_id` | Optional Shield endpoint context |
| `session_id` | Conversation or bounded execution context |
| `memory_id` | Stable memory record identifier, not an authorization credential |

A caller-supplied `agent_id`, profile name, memory identifier, or session identifier MUST NOT establish authorization.

### 8.3 Authorization flow

Every read and write MUST follow this order:

```text
authenticated principal
  → server-side tenant membership
  → server-side agent-scope grants
  → visibility and operation policy
  → canonical query filter
  → retrieval or mutation
```

This applies to:

- memory create, read, search, recall, supersession, contradiction, and forgetting;
- graph traversal and relation mutation;
- embedding and re-embedding;
- attachment upload, download, and deletion/tombstoning;
- telemetry correlation;
- inference task listing, claiming, evidence retrieval, and completion;
- backups, exports, projection rebuilds, and Integrity linking.

Authorization filtering MUST occur before lexical, vector, graph, temporal, or reranking operations. It MUST also apply to caches, background workers, logs, provider bridges, exports, and backups.

### 8.4 Visibility classes

The default visibility MUST be `private_agent`.

```text
private_agent   → one agent subject
tenant_shared   → authorized subjects within one tenant
explicit_shared → named source/destination subjects with grant
operator_scoped → approved operator principals only
public          → deliberately redacted and published content
```

Cross-agent sharing MUST specify source subject, destination subject, tenant, permitted operation, scope, expiry, provenance, consent/policy basis, and revocation behavior. Administrative visibility MUST NOT imply agent ownership.

### 8.5 Storage modes

`[BUILT]` Local single-agent mode uses one profile-local SQLite store and is appropriate for one bounded memory authority.

`[PROPOSED]` Multi-agent service mode MUST use either:

- one isolated database/process boundary per tenant; or
- a database with enforceable tenant and agent Row-Level Security (RLS), audited authorization, encrypted tenant-scoped data, and tested backup/recovery behavior.

Application-level filters over a shared SQLite database MUST NOT be described as production multi-tenant security without adversarial validation of every operation and projection.

Cortex’s canonical store remains the authority. Vector, graph, remote inference, reranking, backup, and synchronization systems are rebuildable projections or explicitly bounded providers, never independent writers.

### 8.6 Inference and embedding isolation

Inference tasks MUST bind to tenant, agent subject, requester, subject identifier, evidence scope, input snapshot hash, output schema, promotion policy, and retry policy.

Claim and completion are separate authorization boundaries. A worker MUST claim a task with an owner and cryptographically random claim token. Completion MUST require the matching owner and token. Leases, retry limits, stale-claim reclamation, dead-letter behavior, and reconciliation MUST be explicit.

Embedding workers MUST apply the same tenant and agent filters as ordinary retrieval. Wrong dimensions, stale content hashes, non-finite values, zero-norm vectors, and cross-agent projection contamination MUST fail closed and remain retryable or observable.

### 8.7 Provenance and Integrity linkage

Cortex MUST preserve raw source observations, derived propositions, summaries, inferences, profiles, procedures, contradictions, and current projections as different epistemic classes. Retrieved memory is untrusted data and MUST NOT alter system authority, identity, permissions, or tool policy.

A Cortex Merkle root proves only the committed bytes under the declared construction. An Integrity StateAnchor proves only the anchored root record. Neither independently proves semantic truth, authorization, ownership, execution, or completeness.

## 9. Migration and compatibility

### 9.1 Non-destructive migration

Migration MUST be additive, versioned, replay-safe, and provenance-linked. Existing records MUST NOT be rewritten to appear as if they were created under the new identity model.

The migration MUST preserve and map:

- existing `did:integrity:` identifiers;
- existing token IDs and registry records;
- existing `SovereignAgent` and StateAnchor references;
- BCC and Oracle evidence;
- Cortex memories, sessions, attachments, and event chains;
- Shield installation and device records;
- historical deployment and runtime identifiers.

### 9.2 Mapping record

Each mapping SHOULD include:

```text
mapping_id
source_namespace
source_identifier
target_namespace
target_identifier
mapping_type
basis and evidence references
created_at
created_by_principal
status
predecessor/successor information
revocation or supersession state
```

A mapping MUST NOT be treated as proof that the source and target were always the same identity. It records a reviewed relationship between historical identifiers.

### 9.3 Compatibility behavior

Legacy readers MUST remain available for the defined deprecation period. Legacy identity records MUST be marked `[LEGACY]`; they MUST NOT silently become current canonical subjects.

If key state is missing, inconsistent, or unverifiable, migration MUST stop for that subject and produce an actionable recovery record. It MUST NOT silently regenerate a key or relabel historical evidence.

## 10. Deployment, recovery, and operational controls

Every deployment record MUST bind:

```text
chain and network
contract or service address
artifact and source hash
configuration and policy digests
identity subject and controller
deployment time and deployer evidence
verification source and observed state
```

A deployment file is a claim until independent chain or service readback verifies it.

The system MUST expose degraded states separately:

```text
executed and verified
executed, unverified
not attempted
blocked by policy
provider unavailable
recovery required
```

Local operation SHOULD remain available for bounded reversible work when optional providers fail. Consequential actions MUST remain fail-closed when mandatory authorization, identity, evidence, or policy services are unavailable.

The following controls remain required before production claims:

- cryptographic origin binding for every graph-memory event;
- monotonic sequence and replay checks;
- deterministic sensitive-data redaction before queueing;
- stale-claim recovery and dead-letter handling;
- independent queue reconciliation after restart;
- adversarial tests for prompt injection, duplicate delivery, revoked keys, provider leakage, and degraded operation;
- multi-agent retrieval, cache, export, backup, and provider-bridge isolation;
- live Shield → Integrity → Cortex correlation;
- Oracle receipt and StateAnchor finality/readback.

## 11. Development sequence and acceptance gates

### Gate 1 — Identity boundary

- define and persist `AgentSubject`;
- define ERC-8004 mapping and pin the exact draft revision;
- define verification-key history, rotation, revocation, and recovery;
- keep Shield device identity separate;
- add negative tests for machine-identity leakage into portable identity.

### Gate 2 — Kernel stabilization

- repair nonce/address-prediction fixtures;
- run concrete account, kernel, and registry-enabled suites;
- rerun formal properties with every enabled configuration;
- close gas-ceiling and adapter-path gaps;
- decide whether the kernel replaces or complements `SovereignAgent.execute()`.

### Gate 3 — Cortex authorization

- introduce tenant and agent-subject membership records;
- enforce principal-to-scope derivation server-side;
- close `memory_embed`, `memory_attach`, telemetry, graph, export, and backup ownership checks;
- add visibility grants and explicit cross-agent sharing;
- bind inference claim/completion to scope and lease tokens.

### Gate 4 — Cross-repository contracts

- update `docs/INTERFACE_CONTRACT.md` for accepted wire changes;
- define Shield export fields for agent subject, device binding, session, deployment, and provenance;
- define Cortex APIs and Model Context Protocol (MCP) tools with server-side scope enforcement;
- add cross-repository integration tests without treating adapters as live proof.

### Gate 5 — Migration

- create lossless legacy-to-current mappings;
- migrate one isolated development subject;
- verify historical evidence remains readable and unchanged;
- test key rotation, revoked keys, device replacement, replay, rollback, and interrupted migration;
- perform independent readback of all resulting service and chain state.

### Gate 6 — Acceptance and release

A v2 implementation MUST NOT be called accepted, conformant, production-ready, or deployed until the exact proposal revision is accepted, the touched-package suites pass, the cross-repository acceptance tests execute, deployment state is independently verified, and residual gaps are recorded in the canonical wiki and production-gap register.

## 12. Current implementation ledger

| Area | Current evidence | Proposed v2 disposition |
|---|---|---|
| v3.2 architecture | Explanatory whitepaper and archived copy | Preserve as rationale; reconcile into accepted clauses |
| IntegrityKernel | Source implemented; focused fixtures currently fail in setup | Stabilize, test, then decide production integration |
| IntegrityAccount | Source implemented; focused suite currently fails in setup | Stabilize with kernel path |
| Production account | `SovereignAgent.execute()` uses `ConstraintExecutionPolicy` | Keep until kernel migration is accepted and verified |
| ERC-8004 registry | ERC-721-shaped source and local custom tests | Require pinned-draft semantic conformance or label custom |
| `IntegrityIdentityReadV1` | Custom read facade | Preserve as explicitly non-ERC-8004 compatibility surface |
| Shield identity | Operationally device-bound through local identity/enrollment state | Preserve device binding; remove portable-agent coupling |
| Cortex profile isolation | Profile-local SQLite and focused identity/runtime tests | Retain for local mode; extend for multi-agent service mode |
| Cortex authorization | Bearer/profile scope foundation; known operation-level gaps | Add server-side tenant/agent authorization everywhere |
| Key recovery | Existing SDK can silently replace incomplete identity state | Replace with fail-closed recovery workflow |
| Live deployment | Historical manifests and unverified integration claims | Require independent chain/service readback |

## 13. Explicit non-claims

Until the gates above are closed, this proposal MUST NOT be used to claim that:

- ERC-8004 conformance has been established;
- a key-derived DID is a stable portable agent identity;
- Shield machine identity proves agent ownership;
- Cortex provides production multi-tenant isolation;
- Cortex memory ownership follows from a supplied `agent_id`;
- the IntegrityKernel mediates the production `SovereignAgent` path;
- historical deployment manifests represent current source;
- a signature, hash, Merkle root, StateAnchor, or local test proves truth, authorization, execution, or legal ownership;
- migration has completed merely because mapping records exist.

## 14. Change-control checklist

Before accepting this proposal as a normative version:

- ~~pin the ERC-8004 revision and preserve its source hash~~ — done 2026-09-12, §5.1;
- perform a clause-by-clause comparison against `docs/SPEC.md` and v3.2;
- update `docs/INTERFACE_CONTRACT.md` for accepted cross-package changes;
- obtain independent adversarial review of identity, kernel, Cortex authorization, and migration;
- run the full touched-package suites and report unavailable tools separately;
- update `PRODUCTION_GAPS.md` with measured closure evidence;
- update the canonical wiki page and append a `WIKI_LOG.md` entry;
- update `docs/DOCUMENT_STATUS.yaml` only after acceptance;
- preserve this proposal and earlier documents as historical records with their authority labels.
