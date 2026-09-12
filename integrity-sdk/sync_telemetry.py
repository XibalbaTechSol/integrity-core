import json
import time
from pathlib import Path
from integrity_sdk.did import load_or_create_did
from integrity_sdk.client import IntegrityClient

from integrity_sdk.telemetry.tracing import trace_run

def sync_transcript():
    # 1. Load the xibalba identity -- the general.integrity one Hermes and every live
    # process actually run as (did:integrity:68fed133...), not the healthcare-vertical
    # identity this script hardcoded before the tri-repo audit's F2 storage unification
    # (2026-09-12). That one is now at ~/.integrity/did/xibalba-healthcare-cli/ and was a
    # different, unrelated registration that only coincidentally shared the "xibalba"
    # label under the old CLI-only flat storage.
    agent_id, keypair, doc = load_or_create_did("xibalba")

    print(f"Loaded identity: {agent_id}")

    # 2. Init client
    client = IntegrityClient(
        agent_id=agent_id,
        keypair=keypair,
        enable_otel_export=True,
        auto_flush=False,
    )

    import sys
    if len(sys.argv) > 1:
        transcript_path = Path(sys.argv[1])
    else:
        transcript_path = Path("/home/xibalba/.gemini/antigravity-cli/brain/e59ab782-fbaa-4c3f-b42a-4fa81552eecd/.system_generated/logs/transcript.jsonl")
    
    print(f"Reading transcript: {transcript_path}")
    
    with open(transcript_path, "r") as f:
        lines = f.readlines()
        
    with trace_run("Antigravity Session", run_type="chain", client=client) as run:
        for line in lines:
            if not line.strip():
                continue
            entry = json.loads(line)
            # Log as telemetry
            client.log_telemetry(metadata={"transcript_step": entry})
            
            step_type = entry.get('type', 'UNKNOWN')
            step_idx = entry.get('step_index', 0)
            
            with trace_run(f"Step {step_idx} - {step_type}", run_type="tool", client=client) as step_run_ctx:
                step_run_ctx.set_outputs({"content": entry.get("content", ""), "tool_calls": entry.get("tool_calls", [])})
                
    # 4. Flush
    print("Flushing telemetry...")
    success = client.flush_telemetry()
    print("Telemetry flush success:", success)

if __name__ == "__main__":
    sync_transcript()
