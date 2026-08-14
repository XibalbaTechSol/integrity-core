import hashlib
from typing import Any
from integrity_sdk.bcc import canonical_json_bytes

def compute_node_hash(node: Any) -> str:
    """Compute the sha256: prefix hash of the canonical JSON encoding of a payload.
    Used for Merkle root and event hash chains.
    """
    digest = hashlib.sha256(canonical_json_bytes(node)).hexdigest()
    return f"sha256:{digest}"
