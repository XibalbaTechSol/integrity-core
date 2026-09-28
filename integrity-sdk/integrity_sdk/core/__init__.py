"""Integrity SDK core: the dependency-light trust layer Shield and Cortex build on.

Needs only `cryptography`, `base58`, `jcs`, `pycryptodome` (keccak) and
`pyyaml` -- no network, chain or telemetry stack (guarded by
tests/unit/test_import_hygiene.py). Contracts implemented here
(docs/EXECUTION_PLAN.md §5):

- C1 canonical bytes ........ `jcs`
- C3 pack + decision ........ `packs`, `decision`
- C4 receipts ............... `receipts` (on `merkle`, the protocol's one Merkle convention)
- C6 memory provider ........ `memory` (interface; verification semantics land in C3)
- policy evaluation ......... `opa` (the one OPA client, fail-closed)
- identity over HTTP ........ `signed_body` (the oracle's signed-submission wire format)

C2 identity lives in `integrity_sdk.did` (DID, keys, public DID file) and hook
normalization in `integrity_sdk.harness_hooks.normalize_hook`; both are
core-safe as well.
"""

from .decision import (
    DECISION_CONTRACT,
    DENY,
    ENFORCE,
    LOG_ONLY,
    NO_MATCH,
    PERMIT,
    SHADOW,
    Decision,
    resolve,
)
from .jcs import canonical_bytes, sha256_hex
from .memory import MEMORY_INTERFACE_VERSION, MemoryProvider
from .merkle import hash_pair, keccak256, leaf_hash, merkle_proof, merkle_root, verify_leaf
from .opa import OpaClient, OpaError
from .packs import PACK_FORMAT, CompiledPack, LoadedPack, PackError, compile_pack, load_pack, sign_pack
from .receipts import (
    CHECKPOINT_VERSION,
    RECEIPT_VERSION,
    ReceiptError,
    ReceiptLog,
    hmac_identifier,
    receipt_hash,
    verify_checkpoint,
    verify_inclusion,
    verify_log,
    verify_receipt,
)
from .signed_body import sign_body, verify_body

__all__ = [
    "DECISION_CONTRACT", "DENY", "ENFORCE", "LOG_ONLY", "NO_MATCH", "PERMIT", "SHADOW", "Decision", "resolve",
    "canonical_bytes", "sha256_hex",
    "hash_pair", "keccak256", "leaf_hash", "merkle_proof", "merkle_root", "verify_leaf",
    "PACK_FORMAT", "CompiledPack", "LoadedPack", "PackError", "compile_pack", "load_pack", "sign_pack",
    "CHECKPOINT_VERSION", "RECEIPT_VERSION", "ReceiptError", "ReceiptLog", "hmac_identifier", "receipt_hash",
    "verify_checkpoint", "verify_inclusion", "verify_log", "verify_receipt",
    "MEMORY_INTERFACE_VERSION", "MemoryProvider", "OpaClient", "OpaError", "sign_body", "verify_body",
]
