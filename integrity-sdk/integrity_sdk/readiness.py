"""Read-only registration readiness evidence.

This module reports prerequisites independently. It never calls registration,
funding, minting, or contract-writing code and never treats a wallet alone as
proof of registration authority.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

from . import did, wallet


@dataclass(frozen=True)
class ReadinessCheck:
    name: str
    status: str
    agent_id: str
    checked_at: int
    evidence_source: str
    detail: str
    failure_reason: str | None = None
    remediation: str | None = None
    authoritative: bool = False


@dataclass(frozen=True)
class RegistrationReadiness:
    agent_id: str
    checks: tuple[ReadinessCheck, ...]

    @property
    def ready(self) -> bool:
        return bool(self.checks) and all(c.status == "pass" for c in self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {"agent_id": self.agent_id, "ready": self.ready, "checks": [asdict(c) for c in self.checks]}


def assess_local_readiness(
    agent_id: str,
    *,
    oracle_registered: bool | None = None,
    preflight: Any | None = None,
    cortex_home: str | Path | None = None,
    onchain_genesis_root: bytes | str | None = None,
) -> RegistrationReadiness:
    """Assess registration prerequisites without mutating identity or chain state.

    ``agent_id`` may be a local DID slug or the DID itself. Cortex is an optional
    canonical memory backend; when ``cortex_home`` is supplied (or
    ``XIBALBA_CORTEX_HOME`` is set), its SQLite source partition is inspected read-only.
    ``onchain_genesis_root`` is an optional result from a separate exact chain read and is
    the only evidence that can promote genesis from unknown for an existing registered
    agent. A non-zero root does not claim that a local Cortex record is itself genesis.
    """
    now = int(time.time())
    checks: list[ReadinessCheck] = []
    identity_path = did.agent_dir(agent_id)
    key_path, doc_path = identity_path / "private_key.pem", identity_path / "document.json"

    def add(name: str, status: str, source: str, detail: str, *, reason: str | None = None, remediation: str | None = None, authoritative: bool = False) -> None:
        checks.append(ReadinessCheck(name, status, agent_id, now, source, detail, reason, remediation, authoritative))

    resolved_agent_id = agent_id
    if key_path.exists() and doc_path.exists():
        try:
            resolved_agent_id, _, _ = did.load_or_create_did(agent_id)
            add("identity_and_key_continuity", "pass", str(identity_path), resolved_agent_id, authoritative=True)
        except Exception as exc:  # noqa: BLE001
            add("identity_and_key_continuity", "fail", str(identity_path), "persisted identity could not be loaded", reason=str(exc), remediation="restore the original key/document pair; do not regenerate it")
    else:
        add("identity_and_key_continuity", "unknown", str(identity_path), "DID key/document pair is incomplete", reason="identity material is absent or partial", remediation="provision or restore the canonical DID pair")

    # MemoryGraph/TrustVault are keyed by the canonical DID, not by the local
    # convenience slug used to locate the DID directory. Using the slug here
    # creates a false negative for callers such as ``assess_local_readiness("xibalba")``.
    vault_dir = Path(__import__("os").environ.get("INTEGRITY_VAULT_HOME", str(Path.home() / ".integrity" / "vault"))) / resolved_agent_id.replace(":", "_").replace("/", "_")
    nodes = vault_dir / "memory_nodes.jsonl"
    has_genesis = False
    if nodes.exists():
        try:
            has_genesis = any(json.loads(line).get("edge_type") == "genesis" for line in nodes.read_text().splitlines() if line.strip())
        except (OSError, json.JSONDecodeError):
            pass
    cortex_memory_count = 0
    cortex_source = None
    selected_cortex_home = cortex_home or os.environ.get("XIBALBA_CORTEX_HOME")
    if selected_cortex_home:
        cortex_db = Path(selected_cortex_home).expanduser() / "graph-memory.sqlite3"
        cortex_source = str(cortex_db)
        try:
            with sqlite3.connect(f"file:{cortex_db}?mode=ro", uri=True) as connection:
                has_sources = connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='sources'"
                ).fetchone()
                if has_sources:
                    cortex_memory_count = int(connection.execute(
                        "SELECT count(*) FROM sources WHERE agent_id = ?", (resolved_agent_id,)
                    ).fetchone()[0])
        except (OSError, sqlite3.Error):
            cortex_memory_count = 0

    memory_present = nodes.exists() or cortex_memory_count > 0
    memory_evidence = str(nodes) if nodes.exists() else (cortex_source or str(nodes))
    add("persistent_memory", "pass" if memory_present else "unknown", memory_evidence,
        "DID-scoped memory store exists" if memory_present else "DID-scoped memory store not found",
        reason=None if memory_present else "no persistent memory store observed",
        remediation=None if memory_present else "initialize the agent-scoped memory store")

    root_nonzero = False
    if isinstance(onchain_genesis_root, bytes):
        root_nonzero = onchain_genesis_root != b"\x00" * 32
    elif isinstance(onchain_genesis_root, str):
        root_nonzero = onchain_genesis_root.removeprefix("0x").strip("0") != ""
    if has_genesis:
        add("memory_genesis", "pass", str(nodes), "local genesis node observed", authoritative=False)
    elif onchain_genesis_root is not None:
        add("memory_genesis", "pass" if root_nonzero else "fail", "StateAnchor.latestRoot()",
            "non-zero StateAnchor root observed" if root_nonzero else "StateAnchor root is zero",
            reason=None if root_nonzero else "registration requires a non-zero genesis memory root",
            remediation=None if root_nonzero else "create and persist the agent-authorized genesis root",
            authoritative=True)
    elif cortex_memory_count > 0:
        add("memory_genesis", "unknown", cortex_source or "Cortex SQLite",
            "Cortex has DID-scoped records, but no local genesis node or chain root was supplied",
            reason="Cortex event history is not by itself proof of an anchored genesis root",
            remediation="read StateAnchor.latestRoot() on the intended network")
    else:
        add("memory_genesis", "fail", str(nodes), "genesis node absent",
            reason="registration requires a genesis memory root",
            remediation="create and persist a signed genesis memory before registration")

    keystore = wallet.wallet_dir(agent_id) / "keystore.json"
    if keystore.exists():
        try:
            address = wallet.load_evm_address(agent_id)
            add("wallet_available", "pass" if address else "fail", str(keystore), address or "keystore has no address", authoritative=True, reason=None if address else "wallet address is unavailable", remediation=None if address else "restore the existing keystore")
        except Exception as exc:  # noqa: BLE001
            add("wallet_available", "fail", str(keystore), "wallet keystore is unreadable", reason=str(exc), remediation="restore the existing keystore; do not generate a replacement")
    else:
        add("wallet_available", "unknown", str(keystore), "agent wallet keystore not found", reason="wallet state is absent", remediation="provision the wallet through the documented registration flow")

    if preflight is not None:
        for check in getattr(preflight, "checks", []):
            add(check.name, "pass" if check.passed else "fail", "registration.preflight", check.detail, reason=None if check.passed else check.detail, remediation=None if check.passed else "resolve this preflight failure before spending gas", authoritative=True)
    else:
        add("on_chain_preflight", "unknown", "not-run", "no chain preflight supplied", reason="controller, roles, primitives, ownership, and finality were not checked", remediation="run preflight_register_agent against the intended network")

    if oracle_registered is not None:
        add("oracle_registration", "pass" if oracle_registered else "fail", "Oracle response", "Oracle registration confirmed" if oracle_registered else "Oracle reports agent unregistered", reason=None if oracle_registered else "agent is not registered with this Oracle", remediation=None if oracle_registered else "complete registration prerequisites and Oracle registration", authoritative=True)
    else:
        add("oracle_registration", "unknown", "not-queried", "Oracle state not queried", reason="registration status is uncertain", remediation="query the configured Oracle read endpoint")
    return RegistrationReadiness(agent_id, tuple(checks))
