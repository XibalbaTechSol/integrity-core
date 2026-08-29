"""Diagnostic: Reproduce exactly what sync_telemetry.py does, but dump the
canonical bytes to a file AND send the raw canonical bytes to a small
Rust program for comparison."""
import json
import sys
from pathlib import Path
from integrity_sdk.did import Keypair
from integrity_sdk.client import IntegrityClient
from integrity_sdk.telemetry.tracing import trace_run
from integrity_sdk import bcc

pem_path = Path("/home/xibalba/.integrity-cli/identity/xibalba.pem")
doc_path = Path("/home/xibalba/.integrity-cli/identity/xibalba.document.json")

with open(pem_path, "rb") as f:
    keypair = Keypair.from_pem(f.read())
with open(doc_path, "r") as f:
    agent_id = json.load(f)["id"]

client = IntegrityClient(
    agent_id=agent_id,
    keypair=keypair,
    enable_otel_export=True,
    auto_flush=False,
)

transcript_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/home/xibalba/.gemini/antigravity-cli/brain/fd43b907-10e3-4eb2-a297-1e6f42e2a505/.system_generated/logs/transcript.jsonl")

# Use only the first 5 lines to keep the payload small but representative
with open(transcript_path, "r") as f:
    lines = [l for l in f.readlines() if l.strip()][:5]

print(f"Using {len(lines)} transcript lines")

with trace_run("Antigravity Session", run_type="chain", client=client) as run:
    for line in lines:
        entry = json.loads(line)
        client.log_telemetry(metadata={"transcript_step": entry})
        step_type = entry.get('type', 'UNKNOWN')
        step_idx = entry.get('step_index', 0)
        with trace_run(f"Step {step_idx} - {step_type}", run_type="tool", client=client) as step_run_ctx:
            step_run_ctx.set_outputs({"content": entry.get("content", ""), "tool_calls": entry.get("tool_calls", [])})

# Now manually do what flush_telemetry does, but dump the canonical bytes
from integrity_sdk.telemetry import derive
batch = client._batcher.get_batch_and_clear()
trace_runs = client._trace_runs
client._trace_runs = []

derived = derive.derive_ais_signals(batch)

otel_spans = (
    [{"kind": "telemetry", **entry} for entry in batch]
    + [{"kind": "trace_run", **run} for run in trace_runs]
)

signable = {
    "schema_version": 1,
    "agent_id": agent_id,
    "nonce": 99999,
    "otel_spans": otel_spans,
    "derived_signals": derived,
    "zk_proof": None,
}

c_bytes = bcc.canonical_json_bytes(signable)
Path("/tmp/client_canonical.json").write_bytes(c_bytes)
print(f"Wrote {len(c_bytes)} bytes to /tmp/client_canonical.json")

# Sign it
signature = "0x" + keypair.sign(c_bytes).hex()

# Send via requests (which re-serializes)
import requests
payload = {**signable, "signature": signature}

# Also dump what requests will actually send
wire_bytes = json.dumps(payload).encode("utf-8")
Path("/tmp/client_wire.json").write_bytes(wire_bytes)
print(f"Wrote {len(wire_bytes)} wire bytes to /tmp/client_wire.json")

# Send
resp = requests.post("http://localhost:8080/v1/telemetry/ingest", json=payload, timeout=10)
print(f"Status: {resp.status_code}")
print(f"Response: {resp.text[:300]}")

# Also re-parse what requests sends and re-canonicalize
parsed_back = json.loads(wire_bytes)
del parsed_back["signature"]
re_canonical = json.dumps(parsed_back, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
Path("/tmp/client_recanonical.json").write_bytes(re_canonical)
print(f"\nOriginal canonical == re-canonical: {c_bytes == re_canonical}")
if c_bytes != re_canonical:
    for i in range(min(len(c_bytes), len(re_canonical))):
        if c_bytes[i] != re_canonical[i]:
            print(f"DIFF at byte {i}:")
            print(f"  orig:  ...{c_bytes[max(0,i-30):i+30]!r}...")
            print(f"  recan: ...{re_canonical[max(0,i-30):i+30]!r}...")
            break
    else:
        print(f"Length diff: orig={len(c_bytes)} recan={len(re_canonical)}")
