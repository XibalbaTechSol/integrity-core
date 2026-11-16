import abc
import binascii
import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from eth_utils import keccak


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
        """
        Computes a deterministic cryptographic root of the current memory state.
        For an append-only log, this could be a hash chain. For a vector DB, 
        a Merkle root of all chunk IDs.
        """
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
        Validates the local state_root against the actor's latest root on `ActionAnchor`.

        The actor is `AgentRegistry.resolveDID(agent_did).actor`. An agent with no bound actor
        has nothing on-chain to compare against (`chain.NO_ACTOR`): returns False and the vault
        stays local and verifiable off-chain. Raises ValueError if the roots differ.
        """
        from integrity_sdk import chain

        local_root = self.backend.compute_state_root()

        w3 = chain.get_w3(chain_rpc_url)
        if not w3.is_connected():
            raise ConnectionError(f"Cannot connect to RPC at {chain_rpc_url}")
        deployments = chain.load_deployments(deployments_file)
        singletons = deployments.get("singletons") or {}
        if not singletons.get("AgentRegistry") or not singletons.get("ActionAnchor"):
            raise ValueError(f"{deployments_file} lacks singletons.AgentRegistry / singletons.ActionAnchor")

        actor = chain.resolve_actor(w3, singletons["AgentRegistry"], self.agent_did)
        if actor is None:
            return False

        onchain_root = chain.actor_latest_root(w3, singletons["ActionAnchor"], actor)
        onchain_norm = "0x" + bytes(onchain_root).hex()
        local_norm = local_root if local_root.startswith("0x") else f"0x{local_root}"
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
        # Pre-flight check
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
        """Returns the recent historical context for the agent."""
        return self.vault.backend.read_latest_context()
        
    def add_fact(self, role: str, content: str) -> None:
        """Records an event or fact to be committed at the end of the session."""
        self.facts.append({"role": role, "content": content})
        
    def commit(self) -> None:
        """
        Compiles the session, appends to backend, and anchors the new root.
        Usually called automatically by the context manager.
        """
        if not self.facts:
            return # Nothing to commit
            
        import time
        session_data = {
            "platform": self.platform,
            "timestamp": time.time(),
            "facts": self.facts
        }
        
        self.vault.backend.append_memory(session_data)
        new_root = self.vault.backend.compute_state_root()
        
        # In this implementation, anchoring occurs outside the context manager or using a callback
        # since it requires private key access, but it's part of the primitive lifecycle
        print(f"[TrustVault] Session committed. New state root: {new_root}")
        print(f"[TrustVault] Reminder: anchor the new root (chain.anchor_vault_root_for_did) to sync with ActionAnchor.")
