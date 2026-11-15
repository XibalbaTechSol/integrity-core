# Agent Registration v3 — Phase 2: `AgentRegistry`

**Parent plan:** `docs/superpowers/plans/2026-11-14-agent-registration-v3.md` (Phases 2–5 outline).
**Spec:** `docs/superpowers/specs/2026-11-14-agent-registration-v3-design.md`, Part 3 and Part 4, Phase 2 acceptance.
**Branch / worktree:** `feat/agent-registry`, `/mnt/storage/xibalba/Projects/worktrees/integrity-core/agent-registry`.

**Scope:** additive. One new contract, its verifier interface, an EIP-1271 hook on `SovereignAgent`, and tests. Nothing is deployed and no consumer is repointed; that is Phase 3.

## Files

- Create `contracts/src/framework/AgentRegistry.sol`. The spec's path; the parent plan's `identity/` directory does not exist.
- Create `contracts/src/framework/IEd25519Verifier.sol` (the proof kind 2 slot).
- Modify `contracts/src/core/SovereignAgent.sol`: add `isValidSignature` (EIP-1271). A signature is valid when it ECDSA-recovers to a controller (`DEFAULT_ADMIN_ROLE`). Contract-wallet controllers are not supported yet.
- Create `contracts/test/framework/AgentRegistryBase.sol` (fixture, plus a mock Ed25519 verifier).
- Create `contracts/test/framework/AgentRegistry.t.sol` (acceptance and surface tests).
- Create `contracts/test/framework/AgentRegistryInvariants.t.sol` (handler and invariants).

## Builder decisions (spec "left to the builder")

| Question | Decision | Why |
|---|---|---|
| Codehash pin | The constructor deploys a reference `SovereignAgent(..., factory_ = address(this))` and stores its `.codehash` as an immutable. | Same technique as `AgentPrimitivesFactory`. `factory` is SovereignAgent's only immutable, so every genuine actor for this registry shares the hash, and the pin cannot be left unwired. |
| `uri` | Stored as a string. Its hash is bound in `RegisterAgent`. | Readable on chain. Gas is paid once, by the guardian. |
| Proof kind 1 | A 65-byte ECDSA signature over the `RegisterAgent` digest. The recovered signer must hold `ATTESTER_ROLE`. | Spec Part 3. Because `guardian`, `actor`, `domainId`, `uriHash` and `deadline` are inside the digest, an attestation cannot be replayed for anyone else. |
| `BindActor` deadline | `register` reuses its own `deadline`. `setActor` takes an explicit `deadline`. | Avoids a second deadline parameter. |
| Actor reuse | `actorClaimedBy[actor]` is permanent. An actor can be rebound only to the fingerprint that first bound it, even after `clearActor`. | Spec says "one actor ↔ one agent". This keeps a SovereignAgent's on-chain history tied to one identity. |
| Domain join | `recordJoin(domainId, guardian, actor)` runs only when an actor is bound (by `register`, `setActor`, or `setDomain` with an actor). An existence-only record with a domain is checked with `canJoin(domainId, guardian)` but records no member. | The `member` of a domain is the acting address that consumers check (`msg.sender`). An existence-only record has none. |
| Policy check | Fails closed. An unset `trustConfig`, an unset `policyRegistry`, or a domain with neither a module nor a graph root reverts `DomainHasNoPolicy`. | Spec: "an actor with no policy would be an agent with no map". |
| Retire | Sets `retiredAt`, keeps the record and the actor binding, and cancels any pending guardian. After that, every guardian write reverts `Retired`, and `isRegisteredAgent` is false. | Spec: irreversible, record kept, marked inactive. |

## Acceptance → test map (spec Phase 2, verbatim clauses)

| Clause | Test |
|---|---|
| squatting with a copied public key and no valid proof reverts | `test_squatting_copied_pubkey_without_valid_proof_reverts` |
| a second write of a fingerprint reverts | `test_second_write_of_a_fingerprint_reverts`, plus `invariant_records_are_never_overwritten` |
| binding an actor without consent reverts | `test_binding_actor_without_consent_reverts` |
| binding a plain wallet (EOA) or a non-canonical contract as actor reverts | `test_binding_an_eoa_as_actor_reverts`, `test_binding_a_non_canonical_contract_as_actor_reverts` |
| binding an actor with no domain, or a domain with no policy, reverts | `test_binding_actor_with_no_domain_reverts`, `test_binding_actor_in_a_domain_with_no_policy_reverts`, `test_policy_check_fails_closed_without_trust_config`, `test_setDomain_with_actor_requires_policy_and_nonzero` |
| an actor cannot be bound to two agents | `test_actor_cannot_be_bound_to_two_agents`, plus `invariant_actor_binding_is_a_bijection` and `invariant_actor_serves_one_identity_for_life` |
| the attester cannot modify an existing record | `test_attester_cannot_modify_an_existing_record` |
| kind 2 reverts while no verifier is set and succeeds with a mock verifier | `test_kind2_reverts_while_no_verifier_is_set`, `test_kind2_succeeds_with_a_mock_verifier` |
| guardian transfer is two-step | `test_guardian_transfer_is_two_step` |
| `retire` is irreversible | `test_retire_is_irreversible`, plus `invariant_retire_is_irreversible` |

The fingerprint tests use the Phase 1 golden-vector key (seed 7), never a real agent's key. `test_existence_record_keyed_by_offchain_did_fingerprint` proves that the on-chain `sha256(pubkey)` equals the off-chain DID suffix.

**Mutation evidence** (each invariant was shown able to fail):
- Remove the `actorClaimedBy` check: `invariant_actor_serves_one_identity_for_life` fails.
- Remove `delete agentOf[actor]` from `_clearActor`: `invariant_actor_binding_is_a_bijection` fails.

## Known limits, closed in Phase 3

- `SovereignAgent._resolveGate` still reads the old `factory.registry()` (XibalbaAgentRegistry) ABI. An actor whose `factory_` is an `AgentRegistry` therefore has an **inert gate**: `registry()` reverts and the gate returns early. **Phase 2 actors are unconfined and must not be deployed.**
- Phase 3 renames `factory` to `registry`, repoints `_resolveGate` to `AgentRegistry.resolveAgent` and `trustConfig`, and deletes the old graph.
- No compatibility shim was added. A `registry()` getter on `AgentRegistry` would make `_resolveGate` decode a different struct, and a decode failure is not caught by `try`, so every `execute` would revert.

## Phase 3 notes (for its own plan)

- **Acceptance grep:** the literal `/v1/agent/register` also matches Phase 1's `/v1/agent/register/offchain`, so the pattern must exclude it.
- **Oracle strings:** `agent_primitives` and the old Oracle route are removed in Phase 4, so Phase 3's grep covers the non-Oracle tree.
- **integrity-console:** its demo `main.py` uses the old path and needs its own PR.
- **Base Sepolia deploy:** blocked until the exposed Base Sepolia credentials are rotated, and the owner broadcasts it.
