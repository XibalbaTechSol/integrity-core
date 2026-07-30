import binascii
import json
import os
from pathlib import Path
from typing import Dict, Any

from eth_utils import keccak
from . import chain, identity, wallet

VAULT_DIR = Path.home() / ".integrity-cli" / "vault"


def get_vault_path(agent_name: str) -> Path:
    return VAULT_DIR / agent_name


def _compute_state_root(memory_file: Path) -> str:
    """Compute a simple Merkle-like root (just a hash chain for now) of the memory log."""
    if not memory_file.exists():
        return keccak(text="").hex()
    
    current_hash = keccak(text="")
    with open(memory_file, "r") as f:
        for line in f:
            if not line.strip():
                continue
            current_hash = keccak(current_hash + keccak(text=line))
    return current_hash.hex()


def sync_vault(
    agent_name: str,
    transcript_path: Path,
    rpc_url: str,
    deployments_file: str
) -> Dict[str, Any]:
    """Sync a session transcript into the trust vault."""
    vault_path = get_vault_path(agent_name)
    vault_path.mkdir(parents=True, exist_ok=True)
    
    memory_file = vault_path / "memory_log.jsonl"
    state_file = vault_path / "state_root.json"
    
    # Read the transcript and extract summary
    if not transcript_path.exists():
        raise FileNotFoundError(f"Transcript not found at {transcript_path}")
        
    # We simulate extraction of key facts (in reality, an LLM call or advanced parser)
    facts = []
    with open(transcript_path, "r") as f:
        for line in f:
            try:
                entry = json.loads(line)
                if entry.get("type") == "USER_INPUT":
                    facts.append({"role": "user", "content": entry.get("content", "")})
                elif entry.get("type") == "PLANNER_RESPONSE":
                    facts.append({"role": "agent", "content": entry.get("content", "")})
            except json.JSONDecodeError:
                pass
                
    summary = {
        "timestamp": os.stat(transcript_path).st_mtime,
        "facts": facts[-5:] # Store last 5 interactions for brevity
    }
    
    # Append to memory log
    with open(memory_file, "a") as f:
        f.write(json.dumps(summary) + "\n")
        
    # Compute new state root
    new_root = _compute_state_root(memory_file)
    state_file.write_text(json.dumps({"state_root": new_root}, indent=2) + "\n")
    
    # Anchor to StateAnchor on-chain
    try:
        w3 = chain.get_w3(rpc_url)
        deployments = chain.load_deployments(deployments_file)
        
        doc = identity.did_document(agent_name)
        did = doc["id"]
        from .client import IntegrityClient
        client = IntegrityClient()
        result_oracle = client.get(f"/v1/agent/{did}")
        primitives = result_oracle.get("primitives", {})
        
        sovereign_agent = primitives.get("sovereign_agent")
        state_anchor = primitives.get("state_anchor")
        
        if sovereign_agent and state_anchor:
            evm_account = wallet.generate_or_load_evm_wallet(agent_name)
            root_bytes = binascii.unhexlify(new_root.replace("0x", ""))
            
            chain.anchor_root(
                w3,
                evm_account,
                sovereign_agent,
                state_anchor,
                w3.eth.chain_id,
                root=root_bytes
            )
            anchored = True
        else:
            anchored = False
    except Exception as e:
        print(f"Warning: Failed to anchor root on-chain: {e}")
        anchored = False
    
    return {
        "memory_file": str(memory_file),
        "state_root": new_root,
        "records_added": 1,
        "anchored_on_chain": anchored
    }
