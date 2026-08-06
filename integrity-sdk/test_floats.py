"""Test: Does a float round-trip through Python json -> HTTP -> serde_json -> canonical
produce the same bytes as Python's own canonical_json_bytes?

This test sends a payload with known floats and checks if the oracle accepts it."""
import json
import requests
from pathlib import Path
from cryptography.hazmat.primitives.serialization import load_pem_private_key, Encoding, PublicFormat

pem = Path("/home/xibalba/.integrity-cli/identity/xibalba.pem").read_bytes()
sk = load_pem_private_key(pem, password=None)

AGENT_ID = "did:integrity:f96ae072b2db5d067213e1a4bd1a068bb9a62cef784868057f6a48cc42994c5d"

# Test with floats that Ryu (serde_json) might serialize differently than Python
test_spans = [
    {
        "kind": "trace_run",
        "name": "Step 1 - PLANNER_RESPONSE",
        "run_type": "tool",
        "start_time": 1785380924.0824814,  # precise float
        "end_time": 1785380924.0830476,
        "latency_ms": 0.102,
        "error": None,
        "inputs": {},
        "outputs": {"content": "Hello world", "tool_calls": []},
        "run_id": "abc123",
        "parent_run_id": "def456",
    }
]

signable = {
    "schema_version": 1,
    "agent_id": AGENT_ID,
    "nonce": 10000,
    "otel_spans": test_spans,
    "derived_signals": {"entropy": 0.0, "grounding": 0.0, "sacrifice": 0.0, "compliance": 0.0},
    "zk_proof": None,
}

canonical = json.dumps(signable, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
c_bytes = canonical.encode("utf-8")
print(f"Client canonical ({len(c_bytes)} bytes):")
print(canonical)
print()

signature_raw = sk.sign(c_bytes)
signature_hex = "0x" + signature_raw.hex()

payload = {**signable, "signature": signature_hex}
resp = requests.post("http://localhost:8080/v1/telemetry/ingest", json=payload, timeout=10)
print(f"Status: {resp.status_code}")
print(f"Response: {resp.text[:500]}")

if resp.status_code != 200:
    # Now let's see what requests actually sends vs what we signed
    # requests.post(json=...) uses json.dumps(payload) internally
    wire_json = json.dumps(payload)
    # Parse it back and re-canonicalize to see if there's a difference
    parsed = json.loads(wire_json)
    del parsed["signature"]
    re_canonical = json.dumps(parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    print(f"\nOriginal canonical == re-canonical after round-trip: {canonical == re_canonical}")
    if canonical != re_canonical:
        for i, (a, b) in enumerate(zip(canonical, re_canonical)):
            if a != b:
                print(f"Diff at position {i}: orig={canonical[i-20:i+20]!r} re={re_canonical[i-20:i+20]!r}")
                break
