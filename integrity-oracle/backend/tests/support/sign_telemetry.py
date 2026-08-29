#!/usr/bin/env python3
"""
Test support: builds and EIP-191-signs a real `POST /v1/telemetry/ingest` payload for
a throwaway secp256k1 key, using integrity-sdk's own `bcc.canonical_json_bytes` (the
exact canonicalization `crypto::verify_agent_signature` on the Rust side must agree
with) so the signature this produces is byte-for-byte what a real agent would send —
not a hand-rolled approximation of the wire format.

Deliberately does NOT go through integrity-sdk's `IntegrityClient.flush_telemetry`:
that method's own docstring documents an unresolved telemetry-envelope-signing gap
unrelated to this test's purpose (verifying the oracle's SSE push matches its own AIS
read), so this script signs the envelope directly instead of depending on that gap's
resolution.

Args (all via argv): private_key_hex, agent_id, nonce (int), entropy, grounding,
sacrifice, compliance (floats), otel_spans_json (optional, default "[]")

`derived_signals` here is the CLAIMED value — since the oracle now independently
recomputes entropy/grounding/sacrifice from `otel_spans` content rather than trusting
this claim (see `backend/src/derive.rs`), a caller can pass a claim that deliberately
disagrees with what `otel_spans` actually contains, to prove the oracle's recomputation
wins (see `oracle_e2e_recomputed_grounding_overrides_inflated_client_claim` in
`tests/e2e.rs`).

Prints the full signed JSON payload (ready to POST as-is) to stdout.
"""

import json
import sys

from eth_account import Account
from eth_account.messages import encode_defunct

from integrity_sdk import bcc


def main() -> None:
    private_key = sys.argv[1]
    agent_id = sys.argv[2]
    nonce = int(sys.argv[3])
    entropy, grounding, sacrifice, compliance = (float(x) for x in sys.argv[4:8])
    otel_spans = json.loads(sys.argv[8]) if len(sys.argv) > 8 else []
    # argv[9], when present, signs the VERSIONED envelope. Omitted => the pre-versioning
    # shape, which every existing caller relies on and which must keep verifying forever.
    schema_version = int(sys.argv[9]) if len(sys.argv) > 9 else None

    signable = {
        "agent_id": agent_id,
        "nonce": nonce,
        "otel_spans": otel_spans,
        "derived_signals": {
            "entropy": entropy,
            "grounding": grounding,
            "sacrifice": sacrifice,
            "compliance": compliance,
        },
        "zk_proof": None,
    }
    if schema_version is not None:
        signable["schema_version"] = schema_version
    message = bcc.canonical_json_bytes(signable)
    signed = Account.sign_message(encode_defunct(message), private_key=private_key)
    signature = "0x" + signed.signature.hex().removeprefix("0x")

    print(json.dumps({**signable, "signature": signature}))


if __name__ == "__main__":
    main()
