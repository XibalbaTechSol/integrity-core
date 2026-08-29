// Integrity Protocol — Intent/Key Binding Circuit
// =================================================
//
// WHAT THIS PROVES
// -----------------
// An AI agent published a "Behavioral Commitment Chain" (BCC) intent-lock
// (see docs/INTERFACE_CONTRACT.md §4.2) before acting. Before the agent's
// action is scored (§4.3, ZK_boost), we want cryptographic assurance that:
//
//   1. The party generating this proof actually holds the secret key
//      material behind the agent's on-chain/off-chain identity — NOT just
//      anyone who happened to see the public commitment.
//   2. That same secret key material, together with the *specific* intent
//      payload that was locked in for this action and the BCC nonce for
//      this action, hashes to the public "intent commitment" that the
//      oracle/contracts side is checking against.
//
// ...WITHOUT the proof ever revealing the secret key material or the full
// intent payload on-chain or to the verifier.
//
// This directly implements INTERFACE_CONTRACT.md §5, item 1: "I know a
// private Ed25519-derived secret and an intent payload whose hash equals
// the public `intended_state_hash`, without revealing the secret or full
// payload."
//
// HASH FUNCTION CHOICE — READ THIS IF YOU ARE integrity-sdk OR integrity-oracle
// -------------------------------------------------------------------------
// The BCC wire object's `intended_state_hash` (§4.2) is SHA-256 over the
// canonical JSON payload — that is fixed by the interface contract and is
// used *outside* this circuit for the Ed25519 signature over the BCC
// object. It does NOT change.
//
// Inside this circuit we do NOT recompute SHA-256. SHA-256 is a bitwise
// hash (rotations, XORs, ANDs over 32-bit words); implementing it in an
// arithmetic circuit costs thousands of gates per call. Instead we use the
// Pedersen hash (`std::hash::pedersen_hash`), which is:
//   - A *native* gate in Barretenberg's UltraPlonk backend (cheap — a
//     handful of constraints per call instead of thousands), and
//   - Already the convention used by this protocol's other Noir circuits
//     (integrity-oracle/circuits/telemetry and .../reputation both commit
//     to private data with `std::hash::pedersen_hash`), so this keeps a
//     single ZK-hash convention across the whole protocol instead of a
//     third scheme.
//
// This means there are now, by design, TWO distinct hashes in the
// pipeline for the same logical action, and every sibling package MUST
// keep them straight:
//   - `intended_state_hash` (SHA-256, in the signed BCC JSON object) —
//     unchanged, used for the Ed25519 signature and audit trail.
//   - `intent_commitment` (Pedersen hash, defined by THIS circuit) — a
//     *derived*, ZK-only value computed as:
//
//         intent_commitment = pedersen_hash([
//             DOMAIN_INTENT,        // Field(2) — domain separation, see below
//             secret_key,           // Field — KDF'd from the agent's Ed25519 seed
//             intent_payload_hash,  // Field — the SHA-256 intended_state_hash,
//                                   //         reduced mod the BN254 scalar field
//                                   //         and passed in as a private Field
//             nonce,                // Field — the same BCC per-agent nonce (§4.2),
//                                   //         public here, not secret
//             chain_id,             // Field — the EVM chain ID this proof is
//                                   //         valid for (public); see CHAIN /
//                                   //         CONTRACT BINDING below
//             verifying_contract,   // Field — the XibalbaAgentRegistry
//                                   //         singleton address for this
//                                   //         deployment (public); see
//                                   //         CHAIN / CONTRACT BINDING below
//         ])
//
//     integrity-sdk's `prover.py` MUST compute `intent_commitment` with
//     *exactly* this array shape and ordering (including the domain tag)
//     before writing Prover.toml, and integrity-oracle MUST recompute or
//     otherwise validate the same value when it checks a submitted proof
//     against the BCC record it has on file for that (agent, nonce) pair.
//     Any divergence (different field order, missing domain tag, hashing
//     raw SHA-256 bytes as 32 separate u8 field elements instead of one
//     reduced Field, etc.) produces a different Pedersen output and the
//     proof will fail to verify even though the underlying data is
//     "the same" in a human sense. There is exactly one place this
//     conversion is defined: right here.
//
//     Converting the 32-byte SHA-256 digest to a single `Field`: take the
//     big-endian byte string, interpret it as an integer, and reduce it
//     mod the BN254 scalar field prime (this is a lossy-but-collision-safe
//     truncation of a few high bits; both sdk and oracle must do this
//     identical `bytes_be_to_field_mod_r` step — see README.md for the
//     reference Python snippet).
//
// CHAIN / CONTRACT BINDING
// --------------------------
// `chain_id` and `verifying_contract` bind a proof to one specific chain
// and one specific protocol deployment (`verifying_contract` is the
// `XibalbaAgentRegistry` singleton address, matching the field integrity-sdk
// already sources via `chain.load_deployments(...)["singletons"]
// ["XibalbaAgentRegistry"]` for the non-ZK BCC binding — see bcc.py/
// markets.py), mirroring the same binding already applied to the non-ZK BCC
// commitment object (§4.2). An
// Ethereum address is at most 160 bits and the BN254 scalar field is
// ~254 bits, so `Field(uint256(address))` is an injective, lossless
// packing with no truncation — the same conversion integrity-sdk's
// `registration.py` already performs elsewhere for the non-ZK binding.
// `chain_id` is packed the same way: `Field(uint256(chain_id))`, no
// reduction needed for realistic chain IDs. Without this binding, a valid
// proof generated against one deployment (e.g. testnet) could be replayed
// verbatim against another deployment of the same contracts (e.g. a
// second testnet fork, or a future mainnet deployment reusing the same
// `agent_id_commitment`) since nothing in the original circuit tied the
// proof to where it would be submitted.
//
// KEY MATERIAL — SCOPE AND AN HONEST LIMITATION
// -----------------------------------------------
// A *full* Ed25519 signature-verification circuit (elliptic-curve scalar
// multiplication + point addition over Curve25519, done as non-native
// field arithmetic inside a BN254/Grumpkin proving system) is a large,
// separate undertaking — it needs a bignum/foreign-field library and is
// its own audited circuit in most production ZK stacks. We do not
// reimplement that here. Instead, `secret_key` is a Field element that
// integrity-sdk derives from the real Ed25519 seed via a KDF
// (`derive_circuit_secret()` in prover.py: BLAKE2s-256 of the raw 32-byte
// Ed25519 seed, reduced mod the BN254 scalar field) at DID-creation time.
// The corresponding `agent_id_commitment = pedersen_hash([DOMAIN_IDENTITY,
// secret_key])` is published once, alongside the DID Document (§4.1), as
// the agent's long-lived ZK identity commitment. This circuit then proves
// "the prover holds the exact preimage of that published commitment" —
// a real, checked, non-mock cryptographic binding — it just is not itself
// an Ed25519 signature check. This scope limitation is intentional and is
// called out here and in README.md rather than silently pretended away
// (matching the "no silent mocks, but be honest about hardware/scope
// limits" rule in INTERFACE_CONTRACT.md §0/§8).
//
// DOMAIN SEPARATION
// ------------------
// `DOMAIN_IDENTITY` (1) and `DOMAIN_INTENT` (2) are prepended to their
// respective Pedersen inputs. Without this, `agent_id_commitment` and
// `intent_commitment` are hashes of arrays that both start with the same
// `secret_key` element; an attacker who can influence how a commitment
// gets reinterpreted elsewhere in the wider protocol (e.g. two different
// services accepting "a Field the prover claims is some Pedersen
// commitment" without checking which *kind*) could otherwise try to pass
// one commitment off as the other. Tagging the domain up front is one
// extra constraint and removes that ambiguity entirely.
global DOMAIN_IDENTITY: Field = 1;
global DOMAIN_INTENT: Field = 2;

fn main(
    // ---- Private inputs (never leave the prover's machine) ----
    // Field-element derived from the agent's real Ed25519 secret seed via
    // a KDF performed off-circuit by integrity-sdk (see prover.py). This
    // is the "witness" the whole proof revolves around.
    secret_key: Field,
    // The BCC object's SHA-256 `intended_state_hash` (§4.2), reduced to a
    // single Field. Kept private so a verifier who does not already know
    // which intent this proof is about cannot learn it from the proof
    // alone — only that *some* payload hash, known to the prover, was
    // bound into `intent_commitment`.
    intent_payload_hash: Field,

    // ---- Public inputs (known to the verifier / posted on-chain) ----
    // The agent's long-lived ZK identity commitment, published once at
    // DID-creation time (see README.md "DID → ZK identity" handoff).
    agent_id_commitment: pub Field,
    // The BCC object's per-agent monotonic nonce (§4.2). Already public on
    // the wire (it's part of the signed JSON), so it is a public input
    // here too, not a secret blinding factor. Reusing it for the intent
    // commitment ties this proof to one specific action and prevents an
    // old proof being replayed as if it covered a newer action.
    nonce: pub Field,
    // The value this proof must reproduce from the private witnesses.
    intent_commitment: pub Field,
    // The EVM chain ID this proof is valid for. See CHAIN / CONTRACT
    // BINDING above.
    chain_id: pub Field,
    // The ReputationRegistry contract address this proof is submitted to,
    // packed as Field(uint256(address)). See CHAIN / CONTRACT BINDING
    // above.
    verifying_contract: pub Field,
) {
    // Defensive: a nonce of 0 is the typical "uninitialized struct field"
    // sentinel in most languages sdk/oracle might be written in. Reject it
    // outright so a caller that forgot to set the nonce fails loudly here
    // instead of silently producing a commitment that looks well-formed.
    assert(nonce != 0);

    // Constraint 1 — Identity binding.
    // Proves the prover controls the exact secret behind the agent's
    // published identity commitment. Prevents anyone who merely observes
    // `intent_commitment` (public) or intercepts a BCC object from
    // generating their own valid-looking proof "on behalf of" this agent:
    // without `secret_key` matching the pre-published `agent_id_commitment`,
    // this assertion fails and no proof can be constructed.
    let derived_identity = std::hash::pedersen_hash([DOMAIN_IDENTITY, secret_key]);
    assert(derived_identity == agent_id_commitment);

    // Constraint 2 — Intent binding.
    // Proves the prover knows an intent payload (represented here by its
    // SHA-256 digest, reduced to a Field) that, together with that same
    // secret and this action's public nonce, reproduces the public
    // `intent_commitment`. This is the ZK analogue of "this agent really
    // did lock in this exact intent before acting" — it prevents a
    // dishonest prover from fabricating a commitment for a payload they
    // never actually committed to, and (via `nonce`) stops a valid proof
    // for one action being replayed as "proof" for a different action.
    let derived_intent = std::hash::pedersen_hash([
        DOMAIN_INTENT,
        secret_key,
        intent_payload_hash,
        nonce,
        chain_id,
        verifying_contract,
    ]);
    assert(derived_intent == intent_commitment);
}

// ---------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------
// `test_valid_binding` exercises the happy path: a prover who honestly
// knows secret_key + intent_payload_hash, against commitments computed
// the same way the circuit computes them. This must satisfy every
// constraint.
//
// `test_invalid_binding_wrong_secret` simulates exactly the attack
// Constraint 1 exists to stop: someone who does NOT hold the real secret
// (they used a different one when constructing their claimed
// `intent_commitment`/`agent_id_commitment` pair) tries to pass their own
// secret off as the one behind a *different*, real agent's public
// identity commitment. It must fail to satisfy the constraints.
#[test]
fn test_valid_binding() {
    let secret_key = 0x1234;
    let intent_payload_hash = 0xabcdef;
    let nonce = 42;
    let chain_id = 84532; // Base Sepolia
    let verifying_contract = 0x5FbDB2315678afecb367f032d93F642f64180aa;

    let agent_id_commitment = std::hash::pedersen_hash([DOMAIN_IDENTITY, secret_key]);
    let intent_commitment = std::hash::pedersen_hash([
        DOMAIN_INTENT,
        secret_key,
        intent_payload_hash,
        nonce,
        chain_id,
        verifying_contract,
    ]);

    main(
        secret_key,
        intent_payload_hash,
        agent_id_commitment,
        nonce,
        intent_commitment,
        chain_id,
        verifying_contract,
    );
}

#[test(should_fail)]
fn test_invalid_binding_wrong_secret() {
    // The REAL agent's long-lived identity commitment and this action's
    // intent commitment, both computed with the real secret `0x1234`.
    let real_secret = 0x1234;
    let intent_payload_hash = 0xabcdef;
    let nonce = 42;
    let chain_id = 84532;
    let verifying_contract = 0x5FbDB2315678afecb367f032d93F642f64180aa;

    let agent_id_commitment = std::hash::pedersen_hash([DOMAIN_IDENTITY, real_secret]);
    let intent_commitment = std::hash::pedersen_hash([
        DOMAIN_INTENT,
        real_secret,
        intent_payload_hash,
        nonce,
        chain_id,
        verifying_contract,
    ]);

    // An impostor who does not hold `real_secret` tries to substitute
    // their own secret and still claim the real agent's public
    // commitments. Constraint 1 (identity binding) must reject this.
    let impostor_secret = 0x9999;
    main(
        impostor_secret,
        intent_payload_hash,
        agent_id_commitment,
        nonce,
        intent_commitment,
        chain_id,
        verifying_contract,
    );
}

#[test(should_fail)]
fn test_invalid_binding_wrong_payload() {
    // Same real agent/secret, but the prover tries to claim a DIFFERENT
    // intent payload than the one actually bound into `intent_commitment`
    // — i.e. "I locked in payload A, let me prove I locked in payload B
    // instead." Constraint 2 (intent binding) must reject this.
    let secret_key = 0x1234;
    let real_payload_hash = 0xabcdef;
    let substituted_payload_hash = 0x111111;
    let nonce = 42;
    let chain_id = 84532;
    let verifying_contract = 0x5FbDB2315678afecb367f032d93F642f64180aa;

    let agent_id_commitment = std::hash::pedersen_hash([DOMAIN_IDENTITY, secret_key]);
    let intent_commitment = std::hash::pedersen_hash([
        DOMAIN_INTENT,
        secret_key,
        real_payload_hash,
        nonce,
        chain_id,
        verifying_contract,
    ]);

    main(
        secret_key,
        substituted_payload_hash,
        agent_id_commitment,
        nonce,
        intent_commitment,
        chain_id,
        verifying_contract,
    );
}

#[test(should_fail)]
fn test_invalid_binding_zero_nonce() {
    // A nonce of 0 must be rejected outright regardless of whether the
    // hashes otherwise line up.
    let secret_key = 0x1234;
    let intent_payload_hash = 0xabcdef;
    let nonce = 0;
    let chain_id = 84532;
    let verifying_contract = 0x5FbDB2315678afecb367f032d93F642f64180aa;

    let agent_id_commitment = std::hash::pedersen_hash([DOMAIN_IDENTITY, secret_key]);
    let intent_commitment = std::hash::pedersen_hash([
        DOMAIN_INTENT,
        secret_key,
        intent_payload_hash,
        nonce,
        chain_id,
        verifying_contract,
    ]);

    main(
        secret_key,
        intent_payload_hash,
        agent_id_commitment,
        nonce,
        intent_commitment,
        chain_id,
        verifying_contract,
    );
}

#[test(should_fail)]
fn test_invalid_binding_wrong_chain_id() {
    // A proof legitimately constructed for chain_id 84532 (Base Sepolia)
    // must not verify when the caller claims a different chain_id at the
    // public-input boundary — this is exactly the cross-deployment replay
    // this binding exists to stop.
    let secret_key = 0x1234;
    let intent_payload_hash = 0xabcdef;
    let nonce = 42;
    let real_chain_id = 84532;
    let wrong_chain_id = 8453; // Base mainnet, not Base Sepolia
    let verifying_contract = 0x5FbDB2315678afecb367f032d93F642f64180aa;

    let agent_id_commitment = std::hash::pedersen_hash([DOMAIN_IDENTITY, secret_key]);
    let intent_commitment = std::hash::pedersen_hash([
        DOMAIN_INTENT,
        secret_key,
        intent_payload_hash,
        nonce,
        real_chain_id,
        verifying_contract,
    ]);

    main(
        secret_key,
        intent_payload_hash,
        agent_id_commitment,
        nonce,
        intent_commitment,
        wrong_chain_id,
        verifying_contract,
    );
}

#[test(should_fail)]
fn test_invalid_binding_wrong_verifying_contract() {
    // Same idea as the chain_id test, but for the contract address half of
    // the binding: a proof built for one XibalbaAgentRegistry deployment
    // must not verify against a claimed different deployment address.
    let secret_key = 0x1234;
    let intent_payload_hash = 0xabcdef;
    let nonce = 42;
    let chain_id = 84532;
    let real_verifying_contract = 0x5FbDB2315678afecb367f032d93F642f64180aa;
    let wrong_verifying_contract = 0x0000000000000000000000000000000000dEaD;

    let agent_id_commitment = std::hash::pedersen_hash([DOMAIN_IDENTITY, secret_key]);
    let intent_commitment = std::hash::pedersen_hash([
        DOMAIN_INTENT,
        secret_key,
        intent_payload_hash,
        nonce,
        chain_id,
        real_verifying_contract,
    ]);

    main(
        secret_key,
        intent_payload_hash,
        agent_id_commitment,
        nonce,
        intent_commitment,
        chain_id,
        wrong_verifying_contract,
    );
}

