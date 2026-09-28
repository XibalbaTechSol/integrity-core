"""Memory-provider interface (SDK contract C6): what any conforming memory store offers.

Registration requires persistent memory, and Cortex is one provider among
possibly several (Hermes' native memory, a customer's own store). This module
fixes the *shape* every provider exposes, so the registrar, the oracle and the
gates depend on the interface, not on Cortex:

- ``genesis``: create the store and return its first root, bound to the
  agent's DID. This is the root the agent anchors on its StateAnchor.
- ``append``: add one record. Content stays in the provider; the caller gets
  back a *content commitment* and the new root, which may be recorded in
  provenance and receipts.
- ``root``: the current provable root (anchorable).
- ``spot_check``: answer a verifier's challenge for a record index with a fresh
  nonce, returning ``H(nonce || content)`` and a Merkle proof for the record's
  commitment under a stated root. A signed digest chain alone cannot show that
  a provider can still produce the content; a fresh-nonce answer can.
- ``purge``: destroy content and its decryption material within the declared
  retention boundary, leaving only non-content provenance.

Honest scope: this is the interface only. How a verifier who must not receive
PHI checks ``H(nonce || content)`` (precomputed challenge tags, a verifier
inside the customer boundary, or a proof-of-retrievability scheme) is designed
and implemented in Phase C3 (docs/EXECUTION_PLAN.md). Until then a spot check
proves inclusion of the commitment, not retrievability, and nothing may claim
otherwise. The regulated profile additionally requires encrypted content at
rest.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Protocol, runtime_checkable

MEMORY_INTERFACE_VERSION = "integrity.memory-provider/1"


@dataclass(frozen=True)
class MemoryRoot:
    root: str  # 0x-prefixed 32-byte hex, in the protocol Merkle convention (core.merkle)
    size: int  # number of records the root covers


@dataclass(frozen=True)
class AppendResult:
    index: int
    content_commitment: str  # commitment to the content, never the content
    root: MemoryRoot


@dataclass(frozen=True)
class SpotCheckResponse:
    index: int
    nonce: str
    nonce_content_digest: str  # hex H(nonce || content)
    content_commitment: str
    proof: List[str]  # sibling path for the commitment's leaf under `root`
    root: MemoryRoot


@dataclass(frozen=True)
class PurgeResult:
    purged_indices: List[int]
    root_after: MemoryRoot  # historical roots stay valid as non-content evidence


@runtime_checkable
class MemoryProvider(Protocol):
    """Structural interface; any class with these methods conforms (PEP 544)."""

    interface_version: str
    provider_id: str
    encrypted_at_rest: bool

    def genesis(self, agent_did: str) -> MemoryRoot: ...

    def append(self, agent_did: str, content: bytes, *, kind: str) -> AppendResult: ...

    def root(self, agent_did: str) -> MemoryRoot: ...

    def spot_check(self, agent_did: str, index: int, nonce: str) -> SpotCheckResponse: ...

    def purge(self, agent_did: str, indices: List[int]) -> PurgeResult: ...
