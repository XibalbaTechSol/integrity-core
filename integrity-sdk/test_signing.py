"""Minimal test: sign a tiny telemetry envelope and POST it to the oracle.
Isolates the signing mismatch by using the smallest possible payload."""
import json
import requests
from pathlib import Path
from cryptography.hazmat.primitives.serialization import load_pem_private_key, Encoding, PublicFormat

# ── Load identity ──────────────────────────────────────────────
pem = Path("/home/xibalba/.integrity-cli/identity/xibalba.pem").read_bytes()
sk = load_pem_private_key(pem, password=None)
pk_hex = sk.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()

AGENT_ID = "did:integrity:f96ae072b2db5d067213e1a4bd1a068bb9a62cef784868057f6a48cc42994c5d"
ORACLE_URL = "http://localhost:8080"

# ── Build a minimal signable ───────────────────────────────────
signable = {
    "schema_version": 1,
    "agent_id": AGENT_ID,
    "nonce": 9999,
    "otel_spans": [{"kind": "trace_run", "name": "test", "latency_ms": 1.0}],
    "derived_signals": {"entropy": 0.0, "grounding": 0.0, "sacrifice": 0.0, "compliance": 0.0},
    "zk_proof": None,
}

# ── Canonical bytes (Python side) ──────────────────────────────
canonical = json.dumps(signable, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
c_bytes = canonical.encode("utf-8")

print(f"=== CLIENT CANONICAL JSON ({len(c_bytes)} bytes) ===")
print(canonical)
print()

# ── Sign ───────────────────────────────────────────────────────
signature_raw = sk.sign(c_bytes)
signature_hex = "0x" + signature_raw.hex()
print(f"Signature length: {len(signature_raw)} bytes")
print(f"Public key (hex): {pk_hex}")
print()

# ── POST ───────────────────────────────────────────────────────
payload = {**signable, "signature": signature_hex}
print(f"=== SENDING TO {ORACLE_URL}/v1/telemetry/ingest ===")

try:
    resp = requests.post(f"{ORACLE_URL}/v1/telemetry/ingest", json=payload, timeout=10)
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.text[:500]}")
except Exception as e:
    print(f"Error: {e}")
