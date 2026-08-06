"""Test: Send only the canonical JSON as raw bytes in the HTTP body,
to check if the oracle's deserialization of the wire format changes floats."""
import json
import sys
from pathlib import Path
from integrity_sdk.did import Keypair
from integrity_sdk import bcc

pem_path = Path("/home/xibalba/.integrity-cli/identity/xibalba.pem")
doc_path = Path("/home/xibalba/.integrity-cli/identity/xibalba.document.json")

with open(pem_path, "rb") as f:
    keypair = Keypair.from_pem(f.read())
with open(doc_path, "r") as f:
    agent_id = json.load(f)["id"]

transcript_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/home/xibalba/.gemini/antigravity-cli/brain/fd43b907-10e3-4eb2-a297-1e6f42e2a505/.system_generated/logs/transcript.jsonl")

# Build a simple test span with a float that might cause issues
with open(transcript_path, "r") as f:
    first_line = json.loads(f.readline())

# Extract a float timestamp from the transcript
start_time = first_line.get("start_time", 1785380924.0824814)
print(f"Test float: {start_time}")
print(f"Python json.dumps: {json.dumps(start_time)}")

signable = {
    "schema_version": 1,
    "agent_id": agent_id,
    "nonce": 100001,
    "otel_spans": [{"kind": "trace_run", "name": "test", "start_time": start_time, "latency_ms": 0.1}],
    "derived_signals": {"entropy": 0.0, "grounding": 0.0, "sacrifice": 0.0, "compliance": 0.0},
    "zk_proof": None,
}

c_bytes = bcc.canonical_json_bytes(signable)
print(f"\nCanonical ({len(c_bytes)} bytes):")
print(c_bytes.decode('utf-8'))

signature = "0x" + keypair.sign(c_bytes).hex()
payload = {**signable, "signature": signature}

# Method 1: Let requests serialize (default)
import requests
resp1 = requests.post("http://localhost:8080/v1/telemetry/ingest", json=payload, timeout=10)
print(f"\nMethod 1 (requests json=): {resp1.status_code} {resp1.text[:200]}")

# Method 2: Manually serialize with ensure_ascii and send as data
signable2 = {**signable, "nonce": 100002}
c_bytes2 = bcc.canonical_json_bytes(signable2)
signature2 = "0x" + keypair.sign(c_bytes2).hex()
payload2 = {**signable2, "signature": signature2}
wire = json.dumps(payload2, ensure_ascii=True).encode("utf-8")
resp2 = requests.post("http://localhost:8080/v1/telemetry/ingest", data=wire, headers={"Content-Type": "application/json"}, timeout=10)
print(f"Method 2 (manual json):   {resp2.status_code} {resp2.text[:200]}")

# Method 3: Use sort_keys + separators matching canonical
signable3 = {**signable, "nonce": 100003}
c_bytes3 = bcc.canonical_json_bytes(signable3)
signature3 = "0x" + keypair.sign(c_bytes3).hex()
payload3 = {**signable3, "signature": signature3}
wire3 = json.dumps(payload3, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
resp3 = requests.post("http://localhost:8080/v1/telemetry/ingest", data=wire3, headers={"Content-Type": "application/json"}, timeout=10)
print(f"Method 3 (canonical json): {resp3.status_code} {resp3.text[:200]}")
