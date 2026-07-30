"""Exact reproduction of sync_telemetry.py flow with 5 lines, dumping the
signable dict to a file before and after what serde_json would do."""
import json
import sys
import time
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

# Monkey-patch flush_telemetry to capture the signable dict
import integrity_sdk.client as client_mod

original_flush = IntegrityClient.flush_telemetry

def patched_flush(self, **kwargs):
    from integrity_sdk.telemetry import derive
    batch = self._batcher.get_batch_and_clear()
    trace_runs_list = self._trace_runs
    self._trace_runs = []
    custom_metrics = self._metrics.drain()

    if not batch and not trace_runs_list and not custom_metrics:
        return True

    self._nonce += 1
    derived = derive.derive_ais_signals(batch)

    otel_spans = (
        [{"kind": "telemetry", **entry} for entry in batch]
        + [{"kind": "trace_run", **run} for run in trace_runs_list]
        + ([{"kind": "custom_metrics", "metrics": custom_metrics}] if custom_metrics else [])
    )

    signable = {
        "schema_version": 1,
        "agent_id": self.agent_id,
        "nonce": self._nonce,
        "otel_spans": otel_spans,
        "derived_signals": derived,
        "zk_proof": None,
    }

    c_bytes = bcc.canonical_json_bytes(signable)

    # Dump the canonical bytes
    Path("/tmp/debug_canonical.json").write_bytes(c_bytes)
    print(f"Wrote canonical ({len(c_bytes)} bytes) to /tmp/debug_canonical.json")

    # Now check: if we json.dumps the signable (like requests does) and parse it back,
    # does re-canonicalizing produce the same bytes?
    wire = json.dumps(signable)
    parsed = json.loads(wire)
    re_c_bytes = bcc.canonical_json_bytes(parsed)
    print(f"Python round-trip match: {c_bytes == re_c_bytes}")

    # Check: what about json.dumps with default settings (what requests uses)?
    import requests
    # requests uses json.dumps(payload) which uses default float formatting
    
    signature = "0x" + self._keypair.sign(c_bytes).hex()
    payload = {**signable, "signature": signature}

    # Dump what we're about to send
    wire_payload = json.dumps(payload)
    Path("/tmp/debug_wire.json").write_text(wire_payload)
    print(f"Wrote wire payload ({len(wire_payload)} bytes) to /tmp/debug_wire.json")

    # Check if there are any floats in otel_spans that might cause issues
    def find_floats(obj, path=""):
        if isinstance(obj, float):
            return [(path, obj)]
        elif isinstance(obj, dict):
            r = []
            for k, v in obj.items():
                r.extend(find_floats(v, f"{path}.{k}"))
            return r
        elif isinstance(obj, list):
            r = []
            for i, v in enumerate(obj):
                r.extend(find_floats(v, f"{path}[{i}]"))
            return r
        return []

    floats = find_floats(signable)
    print(f"\nFloats in signable: {len(floats)}")
    for path, val in floats[:20]:
        py_str = json.dumps(val)
        print(f"  {path}: {val} -> json.dumps: {py_str}")

    resp = requests.post(f"{self.oracle_url}/v1/telemetry/ingest", json=payload, timeout=10)
    print(f"\nStatus: {resp.status_code}")
    print(f"Response: {resp.text[:300]}")
    return resp.status_code == 200

IntegrityClient.flush_telemetry = patched_flush

client = IntegrityClient(
    agent_id=agent_id,
    keypair=keypair,
    enable_otel_export=True,
    auto_flush=False,
)

transcript_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/home/xibalba/.gemini/antigravity-cli/brain/fd43b907-10e3-4eb2-a297-1e6f42e2a505/.system_generated/logs/transcript.jsonl")

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

success = client.flush_telemetry()
print(f"\nFinal result: {success}")
