"""
Agent identity resolution: DID -> a display name plus on-chain status, for anything that
needs to show a human a list of agents (Cortex's Agents view, Shield's device list, the
dashboard). Shared here rather than duplicated in xibalba-cortex and xibalba-shield (both
already depend on this package as a local path dependency) so the three products can't drift
on what "on-chain" means or which name field wins.

Resolution order, matching the standard agreed 2026-09-13:
  1. On-chain status: present in the oracle's `GET /v1/agents` -> on_chain=True. Not there,
     but present in `GET /v1/shield/unregistered-agents` -> on_chain=False, seen=True ("known,
     unregistered"). Neither -> on_chain=False, seen=False ("fully local/unknown").
  2. Display name: oracle `handle` (XNS, the protocol's own naming authority) -> oracle `name`
     (DID document `alsoKnownAs`) -> a local `~/.integrity/agents.json` label (cosmetic-only
     fallback, never a signal of on-chain status) -> a shortened DID.

Fails open: any oracle-reachability problem resolves every requested DID to "unknown, off-chain,
no name" rather than raising -- a naming lookup must never be able to break the page that wanted
to show a device or agent list.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)

_LOCAL_LABELS_PATH = Path.home() / ".integrity" / "agents.json"


def _short_did(did: str) -> str:
    if len(did) <= 24:
        return did
    return f"{did[:14]}…{did[-8:]}"


def _local_labels() -> dict[str, str]:
    """Best-effort read of the ad hoc local label file. Missing/malformed is normal, not an
    error -- most machines won't have this file at all."""
    try:
        raw = json.loads(_LOCAL_LABELS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    labels: dict[str, str] = {}
    if isinstance(raw, dict):
        for label, entry in raw.items():
            did = entry.get("did") if isinstance(entry, dict) else None
            if isinstance(did, str) and did:
                labels[did] = label
    return labels


def resolve_agent_identities(dids: list[str], oracle_url: str, *, timeout: float = 5.0) -> dict[str, dict[str, Any]]:
    """Returns a dict keyed by each requested DID with:
    `did`, `on_chain` (bool), `seen` (bool -- only meaningful when `on_chain` is False),
    `handle` (str | None), `name` (str | None), `local_label` (str | None),
    `wallet_address` (str | None -- the agent's on-chain EVM controller; each agent has its
    own wallet in the dashboard, per `AgentSummary.controller` -- `None` when off-chain, since
    there's nothing to read a controller from),
    `display_name` (str -- the resolved name per the priority order, always non-empty).
    """
    wanted = set(dids)
    result: dict[str, dict[str, Any]] = {}
    registered: dict[str, dict[str, Any]] = {}
    unregistered_seen: set[str] = set()

    try:
        resp = requests.get(f"{oracle_url.rstrip('/')}/v1/agents", timeout=timeout)
        resp.raise_for_status()
        for entry in resp.json():
            agent_id = entry.get("id")
            if isinstance(agent_id, str):
                registered[agent_id] = entry
    except requests.RequestException as exc:
        logger.warning("agent identity resolution: could not reach oracle at %s: %s", oracle_url, exc)

    if wanted - registered.keys():
        try:
            resp = requests.get(f"{oracle_url.rstrip('/')}/v1/shield/unregistered-agents", timeout=timeout)
            resp.raise_for_status()
            unregistered_seen = {row.get("agent_id") for row in resp.json() if isinstance(row.get("agent_id"), str)}
        except requests.RequestException as exc:
            logger.warning("agent identity resolution: could not reach oracle's unregistered-agents endpoint: %s", exc)

    local_labels = _local_labels()

    for did in dids:
        on_chain_entry = registered.get(did)
        local_label = local_labels.get(did)
        handle = on_chain_entry.get("handle") if on_chain_entry else None
        name = on_chain_entry.get("name") if on_chain_entry else None
        wallet_address = on_chain_entry.get("controller") if on_chain_entry else None
        display_name = handle or name or local_label or _short_did(did)
        result[did] = {
            "did": did,
            "on_chain": on_chain_entry is not None,
            "seen": did in unregistered_seen,
            "handle": handle,
            "name": name,
            "local_label": local_label,
            "wallet_address": wallet_address,
            "display_name": display_name,
        }
    return result
