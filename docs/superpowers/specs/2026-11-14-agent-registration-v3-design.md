# Agent registration v3: off-chain by default, on-chain as a record of existence

**Status:** design, approved in conversation with the owner 2026-11-14. Not implemented.
**Authority:** this is a design proposal. Where it conflicts with the accepted spec v0.3
(§4.1, §6, §7.1) or `docs/INTERFACE_CONTRACT.md` (§6.1–§6.3a), those stay authoritative until
the proposed amendment in Phase 5 is reviewed, implemented, tested, and accepted.
**Builds on:** `2026-11-08-integrity-token-v2-design.md` (the v2 trust layer, as amended
2026-11-11) and core #200–#208 (AIS as a closed-loop reward, per-tier zones, local AIS).

## Why

The owner's words: Shield and Cortex should "work with agents [that] register with the oracle
but off chain so users don't need to worry about gas costs", and "registering agents on chain
should be something reserved for agents that use smart contracts". Off-chain agents "should
still be assigned a DID/key pair". The on-chain part "is the record of [an] agent's
existence", and it must support both a bare existence record and an acting address. "We can
forget primitives." "We needed to simplify the agent registration architecture anyway."
And the purpose of going on chain: "being on chain makes an agent confined to the smart
contracts defined in policy packs". Confirmed: an on-chain agent that acts always acts
through the gate; there are no plain-wallet actors.

Today an agent cannot even send telemetry until it has done the full on-chain sequence
(§6.3): about eight transactions that deploy `SovereignAgent` and `StateAnchor`, grant a role,
anchor a genesis memory root, pin policies, approve a bond, then `registerPrimitives` clones
five more per-agent contracts, and the Oracle re-verifies all seven addresses. The v2 trust
layer already replaced what five of those clones were for with singletons keyed by agent
address, so most of that sequence now buys nothing.

## Goals

1. Every agent has a DID and an Ed25519 key pair, generated on the agent's side, and can
   register with the Oracle for free. That is enough for signed telemetry, AIS, control
   zones, and the verification ladder.
2. An agent that uses the protocol's contracts can additionally write **one record** to
   **one registry** in **one transaction**: proof that it exists, who controls the record,
   and optionally the address that acts for it.
3. An on-chain agent that acts is **confined**: every call it makes passes the policy gate,
   and the gate only allows the calls its domain's policy pack allows.
4. Nobody can claim someone else's DID on chain (no squatting), even though the public key is
   public.
5. The trust placed in the Oracle is limited to vouching at birth, and there is a ready door
   to remove even that (on-chain Ed25519 verification) without redesigning anything.

## Non-goals

- Per-agent contracts of any kind. No factory, no clones, no PrimitiveSet.
- Changing the AIS formula beyond what this branch already does (unobserved compliance).
- Key rotation inside a DID. The DID *is* a hash of the key, so a new key is a new DID
  (see "Left to the builder").
- Mainnet. Base Sepolia only; it is redeployed fresh, not migrated (the v2 precedent:
  testnet ITK has no value).

## Anti-goals (would make this a failure even if it works)

- Any user paying gas, or holding ETH, just to be scored or to send telemetry.
- The Oracle being able to change or take over an on-chain record that already exists.
- The Oracle ever holding an agent's private key.
- An address that never consented being bound as some agent's actor.
- An on-chain agent able to act outside its policy pack (an unconfined actor).

## Approaches considered

| | How the registry learns that the key holder approved the record | Trade-off |
|---|---|---|
| **A. Oracle attestation** | The agent signs with Ed25519; the Oracle checks it (it already knows the key from off-chain registration) and signs an EIP-712 attestation the contract verifies cheaply with `ecrecover`. The agent's guardian submits and pays. | One cheap transaction. Trust in the Oracle only at birth. |
| **B. Oracle writes for the agent** | As A, but the Oracle submits and pays. | Free even on chain, but the Oracle becomes the only writer and pays for spam; contradicts "contract-using agents pay". |
| **C. On-chain Ed25519** | The contract verifies the Ed25519 signature itself. | No trusted party. About 500K gas in reported pure-Solidity implementations, and no audited library was found. A bug would sit at the root of every on-chain identity. |
| *(dropped)* Merkle batch of all agents | The Oracle anchors one root over every agent. | Every agent "exists" almost free, but contracts cannot do a simple `msg.sender` lookup, and it puts agents on chain that do not use contracts. |

**Picked: A, with a door for C.** The registry accepts an identity proof of a declared kind.
Kind 1 is the Oracle attestation and ships now. Kind 2 is direct Ed25519 verification
through a governance-set verifier contract; it is disabled until an audited verifier exists.
Both kinds prove the same signed message, so turning C on changes nothing else.

---

## Part 1: Identity (every agent)

- Key: Ed25519, generated where the agent runs (SDK, Shield, Cortex), never by the Oracle.
- DID: `did:integrity:<sha256(raw 32-byte public key), 64 lowercase hex>`
  (`integrity_sdk.did.fingerprint_for_pubkey`, unchanged).
- The **fingerprint** (the 32 bytes behind the hex) is the agent's identifier everywhere on
  chain. It replaces `keccak256(bytes(did))` as the registry key; a contract can check
  `sha256(pubkey) == fingerprint` with the SHA-256 precompile, which it cannot do for a
  keccak of the DID string.

## Part 2: Off-chain registration (Oracle, the default)

`POST /v1/agent/register/offchain`, no chain access:

- Request: `did`, `ed25519_pubkey_hex`, `timestamp` (unix seconds), `signature`, optional
  `did_document`, optional `handle`.
- The agent signs RFC 8785 canonical JSON of
  `{"did", "domain": "integrity.agent.register.offchain.v1", "ed25519_pubkey_hex" (64
  lowercase hex, no 0x), "timestamp"}`. The domain tag stops a telemetry, BCC or DNS
  signature from being replayed as a registration and vice versa. A ±300 s freshness window
  bounds replay; replay is otherwise harmless (same key, same DID, idempotent).
- The Oracle checks: DID well-formed, `sha256(pubkey) == fingerprint`, fresh, signature valid.
  Implemented and unit-tested in `integrity-oracle/backend/src/offchain_registration.rs`
  (8 tests).
- Row semantics: absent → insert at **tier 1** (proven key; see Part 4, "Tier and evidence") with the key; same key → idempotent 200;
  row with no key → attach the proven key; different key → 409, never overwritten.
  `handle` is optional; when given it is claimed with the same rules as today.
- Rate limit: a **global** per-minute key (fresh key pairs are free, so a per-DID limit stops
  nothing). The tier ceiling bounds what a spammed agent can do; the limit bounds table growth.
- Shield and Cortex create the identity and register off-chain on first run, with no user
  step.

Off-chain agents are scored with the per-tier zone policy (#207), so they can reach GREEN
relative to their ceiling, and climb tiers through the existing DNS / GitHub / TEE / KYC routes,
none of which need chain state. Their compliance axis is "unobserved" until a gate supplies
evidence (this branch: migration 0025 and `AisWeights::without_compliance`; gate-receipt
evidence is the next PR).

## Part 3: The on-chain record (`AgentRegistry`)

One new contract, `contracts/src/framework/AgentRegistry.sol`, replacing
`XibalbaAgentRegistry` and `AgentPrimitivesFactory`.

### Record

```solidity
struct AgentRecord {
    bytes32 pubkey;        // raw Ed25519 public key; sha256(pubkey) == fingerprint
    address guardian;      // controls this record (an EOA or a contract wallet)
    address actor;         // optional: the agent's gated account (a SovereignAgent); 0 = existence only
    bytes32 domainId;      // the policy domain; required when actor != 0, optional otherwise
    string  uri;           // optional metadata (DID document / profile)
    uint64  registeredAt;  // block timestamp
    uint64  retiredAt;     // 0 = active
    uint8   proofKind;     // how existence was proven: 1 = oracle attestation, 2 = ed25519
}
mapping(bytes32 fingerprint => AgentRecord) records;
mapping(address actor => bytes32 fingerprint) agentOf;   // one actor <-> one agent
```

### The one message the agent signs

EIP-712, domain `{name: "IntegrityAgentRegistry", version: "1", chainId, verifyingContract}`:

```
RegisterAgent(bytes32 pubkey, address guardian, address actor, bytes32 domainId,
              bytes32 uriHash, uint256 deadline)
```

The agent signs the **32-byte EIP-712 digest** with its Ed25519 key. Both proof kinds prove
that same signature, which is what makes the door for C real:

- **Kind 1, Oracle attestation (ships now).** `POST /v1/agent/{id}/onchain/attestation` takes
  the typed fields and the agent's Ed25519 signature over the digest. The Oracle requires an
  existing off-chain row with that key, verifies the signature, and returns its own ECDSA
  signature over the **same digest** from an attester key. The contract accepts it when the
  recovered signer is in its governance-managed attester set.
- **Kind 2, Ed25519 (door, disabled).** The contract calls a governance-set
  `IEd25519Verifier.verify(pubkey, digest, signature)`. Until governance sets an audited
  verifier, kind 2 reverts `ProofKindDisabled`.

### Writes

- `register(pubkey, guardian, actor, domainId, uri, deadline, proofKind, proof, actorConsent)`
  - Anyone may submit (normally the guardian, who pays gas). No fee, no bond.
  - Reverts if: the deadline has passed; the fingerprint already has a record (first write
    wins; records are never overwritten); the proof does not verify; `domainId != 0` and
    `DomainRegistry.canJoin(domainId, guardian)` is false.
  - When `actor != 0` it also reverts unless **all** of: the actor is a gated account
    (`isGatedAccount`, Part 4), so a plain wallet can never be bound; the actor consented;
    the actor is not already bound; `domainId != 0` and that domain has a policy configured
    in `PolicyRegistry` (a module or a graph root). An actor with no policy would be an
    agent with no map: every `execute` would revert, or worse, a later default would let it
    roam.
  - On success with a domain, the registry calls `DomainRegistry.recordJoin` (it holds
    `REGISTRAR_ROLE`).
- **Actor consent**, required whenever an actor is bound: `msg.sender == actor` (the
  `SovereignAgent` calls `register`/`setActor` through its own `execute`), or an EIP-712
  `BindActor(bytes32 fingerprint, address actor, uint256 deadline)` signature validated by
  EIP-1271 against the `SovereignAgent` (which delegates to its controller).
- Guardian-only, after registration: `setActor(newActor, consent)` (same gated-account,
  consent and policy checks) / `clearActor()`, `setUri(uri)`, `setDomain(domainId)` (same
  `canJoin` check, and the new domain must have a policy when an actor is bound), two-step
  `proposeGuardian(next)` / `acceptGuardian()`, and `retire()` (irreversible; the record and
  its actor binding are kept, marked inactive).
- The attester (the Oracle) has **no** power over an existing record. Its only power is
  enabling the first write of a fingerprint that is not yet on chain.

### Reads (what the rest of the protocol uses)

- `isRegisteredAgent(address actor) -> bool`: an active record has this actor.
- `agentOf(address actor) -> bytes32` and `resolveAgent(address actor) -> AgentRecord`.
- `resolve(bytes32 fingerprint) -> AgentRecord` and `resolveDID(string did) -> AgentRecord`
  (hex-decodes the DID suffix).
- `isGatedAccount(address a) -> bool`: `a`'s code hash equals the canonical `SovereignAgent`
  code hash (stored at deploy). See Part 4. Every bound actor satisfies it by construction.
- `trustConfig() -> address`: moves here from `XibalbaAgentRegistry`, governance-set.

### Events

`AgentRegistered(fingerprint, guardian, actor, domainId, proofKind)`, `ActorBound`,
`ActorCleared`, `GuardianChanged`, `DomainChanged`, `UriChanged`, `AgentRetired`,
`AttesterAdded/Removed`, `Ed25519VerifierSet`.

## Part 4: Confinement — the actor is always a gated `SovereignAgent`

Being on chain means being confined to the contracts the agent's policy pack allows. A plain
wallet can call any contract directly, so it cannot be confined; therefore **the only kind of
actor is a `SovereignAgent`**, whose `execute` runs the v2 gate on every call: freeze check,
then policy (graph-edge proof or module), then stake lock, then the call.

- `SovereignAgent` keeps the v2 gate unchanged. Its constructor takes the registry address
  directly (immutable) instead of a factory, and it reads `trustConfig()` and its domain from
  `AgentRegistry` (`resolveAgent(address(this)).domainId`). The codehash pin moves to
  `AgentRegistry.isGatedAccount`, checked when an actor is bound.
- **Two kinds of on-chain record:** existence only (no actor: a public, tamper-proof record
  that the agent exists, it does not act on chain), and confined (an actor: it acts on chain,
  only inside its policy).
- Because every actor is gated, a consumer contract needs only `isRegisteredAgent(msg.sender)`
  to know the caller is a confined agent. Consumers no longer choose between "known" and
  "gated".
- Onboarding a confined agent: deploy its `SovereignAgent`, then `register(...)` with it as
  actor. Two transactions, versus about eight today.

### Policy pack → on-chain policy

The same signed policy pack drives the off-chain gate (Shield/BCC) and the on-chain gate.
v2 already fixed the seam (INTERFACE_CONTRACT §4.4c): `PolicyRegistry.graphRootOf[domainId]`
is a Merkle root over canonical edge leaves
`(fromNode, relation, toNode, target, targetSelector, riskWeightBps)`. What is missing is the
tooling, added in Phase 3:

- A pack may declare an **on-chain section**: the contracts (`target`), functions
  (`targetSelector`) and risk weights its agents may call.
- `integrity_sdk` compiles that section to the canonical leaves and root (asserted against
  the §4.4c golden vector) and emits the per-call Merkle proofs an agent passes to
  `execute`.
- Publishing the root for a domain stays a governance action (`PolicyRegistry` admin), and
  the published root is bound to the pack's signed digest so anyone can check that the
  on-chain map is the pack's map.

### Tier and evidence

The verification tier stays about **identity**, not location: a proven key is tier 1 for
every agent, off-chain or on-chain (ceiling 600; DNS/GitHub → 2, TEE → 3; tier 0 is left to
legacy rows with no key). Being on chain adds no identity evidence, since the Oracle vouches
for the key either way. Confinement instead shows up as **behavioral evidence**: the gate's
allow and deny outcomes are on-chain facts, so a confined agent's AIS compliance axis becomes
*observed* from independent evidence. Reading those outcomes into AIS belongs to the
gate-receipt-evidence PR that follows Phase 1, not to this design.

## Part 5: What changes in the rest of the protocol

| Consumer | Today | v3 |
|---|---|---|
| `AgentPrimitivesFactory`, `StateAnchor`, `ReputationRegistry`, `Slasher`, `VerifierRegistry`, `ComplianceGate`, `AgentProfile` clones | per-agent primitives | deleted |
| `XibalbaAgentRegistry` (incl. enterprise profile, `registerCore`, `provisionPrimitives`) | DID → PrimitiveSet | deleted; `AgentRegistry` replaces it (an enterprise agent is a record whose actor is its contract) |
| `AISRegistry` | `resolveAgent` on the old registry | `AgentRegistry.isRegisteredAgent`; AIS checkpoints only for agents with an actor |
| `AgentAuthorityResolver`, `ConstraintExecutionPolicy`, `EHRGate` | AIS from the agent's `ReputationRegistry` clone | AIS from `AISRegistry` (completes the deferred v2 amendment) |
| `XibalbaNameService` | claimant `isRegisteredAgent` | same check against `AgentRegistry` (by actor) |
| `AgentLineageRegistry` | by actor | same, against `AgentRegistry` |
| `IntegrityIdentityReadV1`, `IntegrityERC8004Registry` | read PrimitiveSet | read `AgentRecord`; primitive fields dropped from the view (breaking; testnet only) |
| `SovereignAgent.updateAIS` / `ais` | deferred removal | removed now (nothing reads it after the repoint) |
| `Deploy.s.sol`, deployments file, `test_trust_wiring.py` | old graph | rewritten for the new graph; fresh Base Sepolia deploy |
| Oracle `chain.rs` | `resolve_primitives_by_did`, `memory_state` | `resolve(fingerprint)` |
| Oracle `POST /v1/agent/register` (primitives) | chain re-verification | removed (410 Gone with a pointer); replaced by Part 2 and `POST /v1/agent/{id}/onchain/sync`, which reads the record and stores it in a new `agent_onchain_records` table (actor, guardian, domain, proof kind, block) |
| Oracle `agent_primitives` table and every read of it (AIS cross-checks, `oracle_compliance`, settlement) | per-agent addresses | dropped; `settlement_eligible` = active record with an actor; on-chain cross-checks that read clone state are removed |
| `bcc_middleware/app/chain.py` | old registry ABI | `AgentRegistry` |
| SDK `registration.py`, CLI `agent register` | deploys primitives | `register` = off-chain (default); `register --onchain` = existence record (attestation + one tx from the guardian wallet); `register --onchain --confined --domain ID` = also deploys the `SovereignAgent` and binds it as actor |
| Policy packs, `integrity_sdk` | off-chain only | optional on-chain section compiled to the §4.4c root and proofs (Part 4) |

The genesis memory root stops being a registration precondition. Agents that keep a memory
trail anchor it in the v2 `ActionAnchor` singleton, keyed by their actor.

## Part 6: Phasing (each phase is its own PR, merged on green CI)

1. **Off-chain registration + unobserved compliance** (Oracle, SDK client/CLI, Shield and
   Cortex first-run identity). Independent of contracts; unblocks telemetry for every agent.
2. **`AgentRegistry`** with Foundry tests and invariants.
3. **Consumer migration + deletions + deploy script**, fresh Base Sepolia deploy, and the
   policy-pack on-chain section compiler (Part 4).
4. **Oracle on-chain path** (attestation route, sync route, `chain.rs`, table changes) and SDK
   `--onchain`.
5. **Proposed spec amendment** to v0.3 §4.1 / §6 / §7.1 and INTERFACE_CONTRACT §6.1–§6.3a,
   plus wiki pages. Non-authoritative until accepted; the code in phases 1–4 is the
   implementation evidence it cites.

## Acceptance (what "done" means)

- Phase 1: a fresh key pair registers off-chain, sends signed telemetry that returns 2xx, and
  after a few events `GET /v1/agent/{id}/ais` returns a non-zero AIS and a zone that is not
  `red`. Claude's existing DID (`did:integrity:f07438ae…`) registers this way on the Render
  Oracle and its hooks stop logging "not registered".
- Phase 2: Foundry tests prove: squatting with a copied public key and no valid proof reverts;
  a second write of a fingerprint reverts; binding an actor without consent reverts; binding
  a plain wallet (EOA) or a non-canonical contract as actor reverts; binding an actor with no
  domain, or a domain with no policy, reverts; an actor
  cannot be bound to two agents; the attester cannot modify an existing record; kind 2 reverts
  while no verifier is set and succeeds with a mock verifier (the door works); guardian
  transfer is two-step; `retire` is irreversible.
- Phase 3: a confined agent's call to a contract inside its pack's map succeeds and a call
  outside it reverts, end to end from a compiled pack; `forge test` green; no source file references `XibalbaAgentRegistry`,
  `AgentPrimitivesFactory` or `PrimitiveSet`; the deploy wiring test passes on a fresh Anvil.
- Phase 4: an agent registered off-chain obtains an attestation, registers on Anvil in one
  transaction with an actor, and `GET /v1/agent/{id}` then shows the on-chain record and
  `settlement_eligible: true`.

## Decided by the owner

- Off-chain registration is the default; on-chain is only for contract-using agents.
- Every agent gets a DID/key pair, including off-chain ones.
- The on-chain record is a record of existence; an acting address is supported, optional.
- No primitives.
- Approach A with a door for C.
- Being on chain means being confined to the contracts in the agent's policy pack; every
  actor is a gated `SovereignAgent`, never a plain wallet.

## My calls (owner may override)

- No registration fee or bond (gas plus the off-chain prerequisite is the spam cost).
- Fingerprint, not keccak of the DID string, as the on-chain key.
- First write wins; records are never deleted, only retired.
- The Oracle attestation requires a prior off-chain registration with the same key.
- Two-step guardian transfer; actor consent by `msg.sender`, ECDSA, or EIP-1271.
- Domain membership kept (`canJoin` against the guardian); optional for an existence-only
  record, required for a confined one.
- Tier stays about identity: a proven key is tier 1 everywhere; confinement counts as
  compliance evidence, not as tier.
- `SovereignAgent.updateAIS` removed now rather than deferred.
- `POST /v1/agent/register` (primitives) returns 410 rather than silently doing something new.

## Left to the builder

- Exact Solidity layout, error names, gas tuning, and whether `uri` is stored or only hashed.
- The pack schema for the on-chain section and how `fromNode`/`relation`/`toNode` are named
  for plain contract calls (the §4.4c leaf is fixed; the naming is not).
- Key compromise: the guardian retires the record; the replacement key is a new DID, linked by
  `AgentLineageRegistry`. Any richer rotation is out of scope.
- Oracle attester key management: a dedicated key, distinct from the oracle signer that holds
  `SCORER_ROLE`, supplied through deployment secrets.
