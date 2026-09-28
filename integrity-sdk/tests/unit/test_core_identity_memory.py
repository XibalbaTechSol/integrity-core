"""SDK core: signed HTTP bodies (oracle wire compatibility) and the memory-provider interface."""

from __future__ import annotations

from typing import Dict, List

import pytest

from integrity_sdk import bcc
from integrity_sdk.core import memory, merkle, signed_body
from integrity_sdk.did import Keypair

BODY = {"schema_version": 2, "agent_id": "did:integrity:" + "ab" * 32, "nonce": 7, "otel_spans": [{"n": 1.0}]}


def test_signed_body_is_byte_compatible_with_the_previous_client_signing():
    keypair = Keypair.generate()
    signed = signed_body.sign_body(keypair, BODY)
    # What client.py produced inline before, and what the oracle verifies.
    legacy = "0x" + keypair.sign(bcc.canonical_json_bytes(BODY)).hex()
    assert signed["signature"] == legacy
    assert signed_body.verify_body(keypair.public_bytes(), signed)


def test_signed_body_rejects_edits_foreign_keys_and_malformed_signatures():
    keypair = Keypair.generate()
    signed = signed_body.sign_body(keypair, BODY)
    assert not signed_body.verify_body(keypair.public_bytes(), {**signed, "nonce": 8})
    assert not signed_body.verify_body(Keypair.generate().public_bytes(), signed)
    for bad in ("", "0xzz", "0x" + "00" * 10, None):
        assert not signed_body.verify_body(keypair.public_bytes(), {**signed, "signature": bad})
    with pytest.raises(ValueError):
        signed_body.sign_body(keypair, signed)


class _ReferenceProvider:
    """Minimal in-memory provider: shows the interface is implementable, and its proofs verify."""

    interface_version = memory.MEMORY_INTERFACE_VERSION
    provider_id = "reference-in-memory"
    encrypted_at_rest = False

    def __init__(self) -> None:
        self._content: Dict[str, List[bytes]] = {}

    def _leaves(self, agent_did: str) -> List[bytes]:
        return [merkle.leaf_hash("memory", merkle.keccak256(c)) for c in self._content[agent_did]]

    def root(self, agent_did: str) -> memory.MemoryRoot:
        leaves = self._leaves(agent_did)
        return memory.MemoryRoot("0x" + merkle.merkle_root(leaves).hex(), len(leaves))

    def genesis(self, agent_did: str) -> memory.MemoryRoot:
        self._content[agent_did] = [b"genesis:" + agent_did.encode()]
        return self.root(agent_did)

    def append(self, agent_did: str, content: bytes, *, kind: str) -> memory.AppendResult:
        self._content[agent_did].append(content)
        index = len(self._content[agent_did]) - 1
        return memory.AppendResult(index, "0x" + merkle.keccak256(content).hex(), self.root(agent_did))

    def spot_check(self, agent_did: str, index: int, nonce: str) -> memory.SpotCheckResponse:
        content = self._content[agent_did][index]
        proof = merkle.merkle_proof(self._leaves(agent_did), index)
        return memory.SpotCheckResponse(
            index=index,
            nonce=nonce,
            nonce_content_digest=merkle.keccak256(nonce.encode() + content).hex(),
            content_commitment="0x" + merkle.keccak256(content).hex(),
            proof=["0x" + p.hex() for p in proof],
            root=self.root(agent_did),
        )

    def purge(self, agent_did: str, indices: List[int]) -> memory.PurgeResult:
        for index in indices:
            self._content[agent_did][index] = b""
        return memory.PurgeResult(list(indices), self.root(agent_did))


def test_a_provider_conforms_structurally_and_its_spot_check_proof_verifies():
    provider = _ReferenceProvider()
    assert isinstance(provider, memory.MemoryProvider)
    did = "did:integrity:" + "cd" * 32
    provider.genesis(did)
    appended = provider.append(did, b"note: patient-free synthetic content", kind="note")
    answer = provider.spot_check(did, appended.index, nonce="n-1")
    leaf = merkle.leaf_hash("memory", bytes.fromhex(answer.content_commitment[2:]))
    assert merkle.verify_leaf(
        bytes.fromhex(answer.root.root[2:]), leaf, [bytes.fromhex(p[2:]) for p in answer.proof]
    )
    # Inclusion of the commitment only: retrievability without the content is Phase C3's job.
    assert answer.nonce_content_digest != provider.spot_check(did, appended.index, nonce="n-2").nonce_content_digest
