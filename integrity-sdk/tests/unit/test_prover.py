"""
Real end-to-end coverage of `integrity_sdk.prover` against the actual
integrity-zkp Noir/Barretenberg toolchain — no mocking of nargo/bb. This is
the first test coverage `prover.py` has ever had; it previously had none
and was not wired to the real circuit at all (see prover.py's own
docstring). Requires `nargo`/`bb` on PATH (docs/INTERFACE_CONTRACT.md §1
pins the exact versions); skipped otherwise rather than failing the whole
suite in an environment without the ZK toolchain installed.
"""

from __future__ import annotations

import hashlib
import shutil

import pytest

from integrity_sdk.did import Keypair
from integrity_sdk.prover import NoirProver, _pack_address_to_field, _pack_hash_to_field

pytestmark = pytest.mark.skipif(
    shutil.which("nargo") is None or shutil.which("bb") is None,
    reason="nargo/bb not on PATH — real ZK toolchain required, no mock fallback",
)

CHAIN_ID = 31337
VERIFYING_CONTRACT = "0x5FC8d32690cc91D4c39d9d3abcBD16989F875707"


@pytest.fixture(scope="module")
def prover() -> NoirProver:
    return NoirProver()


def _intended_state_hash() -> str:
    return "0x" + hashlib.sha256(b"a real BCC intent payload").hexdigest()


def test_generate_and_verify_real_proof(prover: NoirProver) -> None:
    keypair = Keypair.generate()
    proof = prover.generate_proof(
        intended_state_hash_hex=_intended_state_hash(),
        nonce=1,
        chain_id=CHAIN_ID,
        verifying_contract=VERIFYING_CONTRACT,
        keypair=keypair,
    )
    assert proof.circuit == "integrity_zkp"
    assert proof.verifier_target == "evm"
    assert len(bytes.fromhex(proof.proof_hex)) == 8000
    # 5 real public inputs, 32 bytes each. The 8 UltraHonk pairing-point
    # words counted in the Solidity verifier's NUMBER_OF_PUBLIC_INPUTS=13
    # are carried inside the proof bytes, not this public_inputs file.
    assert len(bytes.fromhex(proof.public_inputs_hex)) == 5 * 32
    assert prover.verify_proof(proof) is True


def test_tampered_proof_fails_verification(prover: NoirProver) -> None:
    keypair = Keypair.generate()
    proof = prover.generate_proof(
        intended_state_hash_hex=_intended_state_hash(),
        nonce=2,
        chain_id=CHAIN_ID,
        verifying_contract=VERIFYING_CONTRACT,
        keypair=keypair,
    )
    tampered_bytes = bytearray(bytes.fromhex(proof.proof_hex))
    tampered_bytes[0] ^= 1
    from dataclasses import replace

    tampered = replace(proof, proof_hex=bytes(tampered_bytes).hex())
    assert prover.verify_proof(tampered) is False


def test_different_chain_id_produces_different_commitment(prover: NoirProver) -> None:
    keypair = Keypair.generate()
    state_hash = _intended_state_hash()
    proof_a = prover.generate_proof(
        intended_state_hash_hex=state_hash,
        nonce=3,
        chain_id=CHAIN_ID,
        verifying_contract=VERIFYING_CONTRACT,
        keypair=keypair,
    )
    proof_b = prover.generate_proof(
        intended_state_hash_hex=state_hash,
        nonce=3,
        chain_id=8453,  # different chain -> different intent_commitment
        verifying_contract=VERIFYING_CONTRACT,
        keypair=keypair,
    )
    assert proof_a.intent_commitment_field != proof_b.intent_commitment_field
    # Identity commitment is independent of chain_id/verifying_contract/nonce.
    assert proof_a.agent_id_commitment_field == proof_b.agent_id_commitment_field


def test_identity_commitment_is_stable_per_keypair_and_distinct_across_keypairs(prover: NoirProver) -> None:
    # generate_proof always derives agent_id_commitment from the caller's
    # own keypair (there is no way to hand it a target commitment to try to
    # match — that asymmetry is what makes impersonation via this API
    # impossible: `main.nr`'s own test_invalid_binding_wrong_secret already
    # covers the underlying constraint failure at the circuit level). The
    # property this integration actually needs to hold: the same keypair
    # always derives the same identity commitment, and different keypairs
    # derive different ones.
    keypair_a = Keypair.generate()
    keypair_b = Keypair.generate()
    state_hash = _intended_state_hash()

    proof_a1 = prover.generate_proof(
        intended_state_hash_hex=state_hash,
        nonce=5,
        chain_id=CHAIN_ID,
        verifying_contract=VERIFYING_CONTRACT,
        keypair=keypair_a,
    )
    proof_a2 = prover.generate_proof(
        intended_state_hash_hex=state_hash,
        nonce=6,
        chain_id=CHAIN_ID,
        verifying_contract=VERIFYING_CONTRACT,
        keypair=keypair_a,
    )
    proof_b = prover.generate_proof(
        intended_state_hash_hex=state_hash,
        nonce=7,
        chain_id=CHAIN_ID,
        verifying_contract=VERIFYING_CONTRACT,
        keypair=keypair_b,
    )
    assert proof_a1.agent_id_commitment_field == proof_a2.agent_id_commitment_field
    assert proof_a1.agent_id_commitment_field != proof_b.agent_id_commitment_field


def test_pack_hash_to_field_reduces_mod_fr() -> None:
    digest_hex = "0x" + "ff" * 32  # larger than the BN254 scalar field
    packed = _pack_hash_to_field(digest_hex)
    assert packed < 21888242871839275222246405745257275088548364400416034343698204186575808495617


def test_pack_address_to_field_is_lossless() -> None:
    addr = "0x5FC8d32690cc91D4c39d9d3abcBD16989F875707"
    assert _pack_address_to_field(addr) == int(addr, 16)
