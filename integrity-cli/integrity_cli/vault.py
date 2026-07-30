import binascii
import json
import os
from pathlib import Path
from typing import Dict, Any

from eth_utils import keccak
from . import chain, identity, wallet

VAULT_DIR = Path.home() / ".integrity-cli" / "vault"


import abc
import binascii
import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Any, List, Iterator

from eth_utils import keccak
from web3 import Web3
from . import chain, identity, wallet
from .client import IntegrityClient


VAULT_DIR = Path.home() / ".integrity-cli" / "vault"


def get_vault_path(agent_name: str) -> Path:
    return VAULT_DIR / agent_name


class MemoryBackend(abc.ABC):
    """
    Interface for pluggable memory backends (JSONL, RAG/VectorDB, Graph, etc.).
    """
    
    @abc.abstractmethod
    def append_memory(self, session_context: Dict[str, Any]) -> None:
        """Appends new session data to the backend storage."""
        pass
        
    @abc.abstractmethod
    def compute_state_root(self) -> str:
        """Computes a deterministic cryptographic root of the current memory state."""
        pass
        
    @abc.abstractmethod
    def read_latest_context(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Retrieves the most recent context from the memory backend."""
        pass


class JSONLBackend(MemoryBackend):
    """Default append-only JSONL implementation of the Trust Vault."""
    
    def __init__(self, storage_path: Path):
        self.storage_path = storage_path
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        
    def append_memory(self, session_context: Dict[str, Any]) -> None:
        with open(self.storage_path, "a") as f:
            f.write(json.dumps(session_context) + "\n")
            
    def compute_state_root(self) -> str:
        if not self.storage_path.exists():
            return keccak(text="").hex()
            
        current_hash = keccak(text="")
        with open(self.storage_path, "r") as f:
            for line in f:
                if not line.strip():
                    continue
                current_hash = keccak(current_hash + keccak(text=line))
        return current_hash.hex()
        
    def read_latest_context(self, limit: int = 5) -> List[Dict[str, Any]]:
        if not self.storage_path.exists():
            return []
        lines = self.storage_path.read_text().splitlines()
        return [json.loads(line) for line in lines[-limit:]]


class RAGBackend(MemoryBackend):
    """Stub for a Vector Database / RAG backend adapter."""
    def __init__(self, connection_string: str):
        self.connection_string = connection_string
        
    def append_memory(self, session_context: Dict[str, Any]) -> None:
        raise NotImplementedError("RAGBackend is a stub")
        
    def compute_state_root(self) -> str:
        raise NotImplementedError("RAGBackend is a stub")
        
    def read_latest_context(self, limit: int = 5) -> List[Dict[str, Any]]:
        raise NotImplementedError("RAGBackend is a stub")


class GraphBackend(MemoryBackend):
    """Stub for a Graph Database backend adapter."""
    def __init__(self, connection_string: str):
        self.connection_string = connection_string
        
    def append_memory(self, session_context: Dict[str, Any]) -> None:
        raise NotImplementedError("GraphBackend is a stub")
        
    def compute_state_root(self) -> str:
        raise NotImplementedError("GraphBackend is a stub")
        
    def read_latest_context(self, limit: int = 5) -> List[Dict[str, Any]]:
        raise NotImplementedError("GraphBackend is a stub")


class TrustVault:
    def __init__(self, agent_did: str, backend: MemoryBackend):
        self.agent_did = agent_did
        self.backend = backend
        
    def verify_preflight(self, chain_rpc_url: str = "http://localhost:8545", deployments_file: str = "../deployments.local.json") -> bool:
        """
        Validates the local state_root against the on-chain StateAnchor.
        Throws a ValueError if tampered or out of sync.
        """
        local_root = self.backend.compute_state_root()
        
        # 1. Resolve StateAnchor from oracle
        client = IntegrityClient()
        result_oracle = client.get(f"/v1/agent/{self.agent_did}")
        primitives = result_oracle.get("primitives", {})
        state_anchor = primitives.get("state_anchor")
        
        if not state_anchor:
            raise ValueError(f"No StateAnchor found for agent {self.agent_did}")
            
        # 2. Query on-chain root
        w3 = Web3(Web3.HTTPProvider(chain_rpc_url))
        
        if not w3.is_connected():
            raise ConnectionError(f"Cannot connect to RPC at {chain_rpc_url}")
            
        with open(deployments_file, "r") as f:
            deployments = json.load(f)
            
        abi = [{
            "inputs": [],
            "name": "currentRoot",
            "outputs": [{"internalType": "bytes32", "name": "", "type": "bytes32"}],
            "stateMutability": "view",
            "type": "function"
        }]
        state_anchor_contract = w3.eth.contract(address=w3.to_checksum_address(state_anchor), abi=abi)
        
        onchain_root = state_anchor_contract.functions.currentRoot().call()
        onchain_root_hex = "0x" + onchain_root.hex() if isinstance(onchain_root, bytes) else onchain_root
        
        if local_root != onchain_root_hex and local_root != onchain_root_hex.replace("0x", ""):
            local_norm = local_root if local_root.startswith("0x") else f"0x{local_root}"
            onchain_norm = onchain_root_hex if onchain_root_hex.startswith("0x") else f"0x{onchain_root_hex}"
            
            if local_norm != onchain_norm:
                raise ValueError(
                    f"Memory integrity compromised or out-of-sync! "
                    f"Local root: {local_norm}, On-chain root: {onchain_norm}"
                )
                
        return True
        
    @contextmanager
    def session(self, platform: str) -> Iterator["ActiveSession"]:
        """
        Context manager for an active memory session.
        Validates before starting, commits and anchors upon exit.
        """
        self.verify_preflight()
        session = ActiveSession(self, platform)
        try:
            yield session
        finally:
            session.commit()


class ActiveSession:
    def __init__(self, vault: TrustVault, platform: str):
        self.vault = vault
        self.platform = platform
        self.facts: List[Dict[str, Any]] = []
        
    def load_context(self) -> List[Dict[str, Any]]:
        return self.vault.backend.read_latest_context()
        
    def add_fact(self, role: str, content: str) -> None:
        self.facts.append({"role": role, "content": content})
        
    def commit(self) -> None:
        if not self.facts:
            return 
            
        import time
        session_data = {
            "platform": self.platform,
            "timestamp": time.time(),
            "facts": self.facts
        }
        
        self.vault.backend.append_memory(session_data)
        new_root = self.vault.backend.compute_state_root()
        print(f"[TrustVault] Session committed. New state root: {new_root}")


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
    
    if not transcript_path.exists():
        raise FileNotFoundError(f"Transcript not found at {transcript_path}")
        
    doc = identity.did_document(agent_name)
    did = doc["id"]
    
    backend = JSONLBackend(memory_file)
    tv = TrustVault(did, backend)
    
    # We bypass preflight verify here because this is the CLI acting as a backend tool, 
    # and it might be creating the genesis root or resyncing.
    
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
                
    # Create an explicit active session
    session = ActiveSession(tv, "integrity-cli")
    # Only keep last 5 facts for brevity
    session.facts = facts[-5:]
    session.commit()
    
    new_root = backend.compute_state_root()
    state_file.write_text(json.dumps({"state_root": new_root}, indent=2) + "\\n")
    
    anchored = False
    try:
        w3 = chain.get_w3(rpc_url)
        deployments = chain.load_deployments(deployments_file)
        
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
    except Exception as e:
        print(f"Warning: Failed to anchor root on-chain: {e}")
        
    return {
        "memory_file": str(memory_file),
        "state_root": new_root,
        "records_added": len(facts[-5:]),
        "anchored_on_chain": anchored
    }
