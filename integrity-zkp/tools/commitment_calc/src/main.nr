// Offline commitment calculator — NOT the proving circuit.
//
// integrity-sdk's `prover.py` needs to know `agent_id_commitment` and
// `intent_commitment` BEFORE it can write a `Prover.toml` for the real
// circuit (`../../circuit/src/main.nr`), because that circuit takes both as
// public inputs to be checked (asserted equal to a freshly derived value),
// not computed as outputs. There is no Python Pedersen-hash implementation
// in this repo (deliberately — reimplementing Barretenberg's Pedersen hash
// from scratch in a second language is exactly the kind of "two hashes,
// both look canonical" divergence risk `../../circuit/src/main.nr`'s own
// docstring warns about), so instead this tiny sibling circuit runs the
// *identical* hash computation through the real `nargo`/Barretenberg
// toolchain and returns the two commitments as its public output, which
// `nargo execute` prints to stdout (`Circuit output: (0x.., 0x..)`) for
// prover.py to parse.
//
// THE HASH LOGIC BELOW MUST STAY BYTE-IDENTICAL TO `../../circuit/src/
// main.nr`'S `derived_identity` / `derived_intent` COMPUTATIONS (domain
// tags, field order, everything) — any change to the real circuit's hash
// shape must be mirrored here in the same commit.
//
// WHAT ACTUALLY CATCHES DRIFT, PRECISELY (don't overstate this — a Noir
// `#[test]` cannot read another package's Prover.toml or call into another
// package's functions, so nothing here can detect a change made ONLY to
// `../../circuit/src/main.nr`'s hash shape):
//   - `test_matches_main_circuit_fixture` below pins THIS package's own
//     output against `../../circuit/Prover.toml`'s checked-in fixture
//     values. It catches drift in THIS file's own logic (e.g. someone
//     reorders this array without updating the pinned constants) — it does
//     NOT catch the real circuit changing out from under it.
//   - What DOES catch that: `make build`'s `nargo execute witness` step
//     (run against `circuit/`) fails if the checked-in `circuit/Prover.toml`
//     fixture no longer satisfies `circuit/src/main.nr`'s constraints — but
//     only if `circuit/Prover.toml` itself wasn't updated to match, which is
//     a manual step (see README.md "Fixture values"), not automatic. There
//     is currently no single automated check that a hash-shape change to
//     `circuit/src/main.nr` was mirrored here; that step is a same-commit
//     discipline, not a CI-enforced invariant.
global DOMAIN_IDENTITY: Field = 1;
global DOMAIN_INTENT: Field = 2;

fn main(
    secret_key: Field,
    intent_payload_hash: Field,
    nonce: pub Field,
    chain_id: pub Field,
    verifying_contract: pub Field,
) -> pub (Field, Field) {
    let agent_id_commitment = std::hash::pedersen_hash([DOMAIN_IDENTITY, secret_key]);
    let intent_commitment = std::hash::pedersen_hash([
        DOMAIN_INTENT,
        secret_key,
        intent_payload_hash,
        nonce,
        chain_id,
        verifying_contract,
    ]);
    (agent_id_commitment, intent_commitment)
}

#[test]
fn test_matches_main_circuit_fixture() {
    // Same secret_key/intent_payload_hash/nonce/chain_id/verifying_contract
    // as integrity-zkp/Prover.toml's checked-in fixture. If this ever stops
    // matching the values recorded there, either this file's hash logic or
    // ../../src/main.nr's has drifted from the other.
    let secret_key = 0xf00d;
    let intent_payload_hash = 0xc0ffee;
    let nonce = 7;
    let chain_id = 31337;
    let verifying_contract = 0x5FC8d32690cc91D4c39d9d3abcBD16989F875707;

    let (agent_id_commitment, intent_commitment) =
        main(secret_key, intent_payload_hash, nonce, chain_id, verifying_contract);

    assert(
        agent_id_commitment
            == 0x2817315e00e740df3fec7b27f79eacc3925ffc65d592bbbb273ca8d1b7c880ba,
    );
    assert(
        intent_commitment
            == 0x164a96b914cc827ea81f6b84b94e6753dfe88acf3255cfc91873550f3a58d88d,
    );
}
