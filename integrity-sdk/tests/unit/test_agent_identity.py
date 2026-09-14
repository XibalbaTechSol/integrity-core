"""Tests for integrity_sdk.agent_identity's resolution priority and fail-open behavior."""
from __future__ import annotations

import json

import pytest
import requests

from integrity_sdk import agent_identity

ORACLE_URL = "http://localhost:8080"
DID_WITH_HANDLE = "did:integrity:aaaa"
DID_WITH_NAME_ONLY = "did:integrity:bbbb"
DID_LOCAL_LABEL_ONLY = "did:integrity:cccc"
DID_UNKNOWN_BUT_SEEN = "did:integrity:dddd"
DID_FULLY_UNKNOWN = "did:integrity:eeee"


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


@pytest.fixture
def fake_oracle(monkeypatch):
    def _get(url, timeout=5.0):
        if url == f"{ORACLE_URL}/v1/agents":
            return _Resp([
                {"id": DID_WITH_HANDLE, "handle": "xibalba.integrity", "name": None, "controller": "0xabc123"},
                {"id": DID_WITH_NAME_ONLY, "handle": None, "name": "Legacy Name", "controller": "0xdef456"},
            ])
        if url == f"{ORACLE_URL}/v1/shield/unregistered-agents":
            return _Resp([{"agent_id": DID_UNKNOWN_BUT_SEEN, "source": "otel", "first_seen": "2026-01-01T00:00:00Z"}])
        raise AssertionError(f"unexpected URL {url}")

    monkeypatch.setattr("integrity_sdk.agent_identity.requests.get", _get)


@pytest.fixture
def local_labels_file(tmp_path, monkeypatch):
    path = tmp_path / "agents.json"
    path.write_text(json.dumps({"quant-label": {"did": DID_LOCAL_LABEL_ONLY}}))
    monkeypatch.setattr("integrity_sdk.agent_identity._LOCAL_LABELS_PATH", path)
    return path


def test_handle_wins_over_name_and_local_label(fake_oracle, local_labels_file):
    result = agent_identity.resolve_agent_identities([DID_WITH_HANDLE], ORACLE_URL)
    entry = result[DID_WITH_HANDLE]
    assert entry["on_chain"] is True
    assert entry["display_name"] == "xibalba.integrity"


def test_name_used_when_no_handle(fake_oracle, local_labels_file):
    result = agent_identity.resolve_agent_identities([DID_WITH_NAME_ONLY], ORACLE_URL)
    entry = result[DID_WITH_NAME_ONLY]
    assert entry["on_chain"] is True
    assert entry["display_name"] == "Legacy Name"


def test_wallet_address_present_on_chain_and_absent_off_chain(fake_oracle, local_labels_file):
    result = agent_identity.resolve_agent_identities([DID_WITH_HANDLE, DID_FULLY_UNKNOWN], ORACLE_URL)
    assert result[DID_WITH_HANDLE]["wallet_address"] == "0xabc123"
    assert result[DID_FULLY_UNKNOWN]["wallet_address"] is None


def test_local_label_used_only_when_off_chain_and_unnamed(fake_oracle, local_labels_file):
    result = agent_identity.resolve_agent_identities([DID_LOCAL_LABEL_ONLY], ORACLE_URL)
    entry = result[DID_LOCAL_LABEL_ONLY]
    assert entry["on_chain"] is False
    assert entry["display_name"] == "quant-label"


def test_unregistered_but_seen_is_distinct_from_fully_unknown(fake_oracle, local_labels_file):
    result = agent_identity.resolve_agent_identities([DID_UNKNOWN_BUT_SEEN, DID_FULLY_UNKNOWN], ORACLE_URL)
    assert result[DID_UNKNOWN_BUT_SEEN]["on_chain"] is False
    assert result[DID_UNKNOWN_BUT_SEEN]["seen"] is True
    assert result[DID_FULLY_UNKNOWN]["on_chain"] is False
    assert result[DID_FULLY_UNKNOWN]["seen"] is False


def test_falls_back_to_shortened_did_when_long_and_unnamed(fake_oracle, local_labels_file, monkeypatch):
    long_did = "did:integrity:" + "e" * 40

    def _get(url, timeout=5.0):
        if url == f"{ORACLE_URL}/v1/agents":
            return _Resp([])
        if url == f"{ORACLE_URL}/v1/shield/unregistered-agents":
            return _Resp([])
        raise AssertionError(f"unexpected URL {url}")

    monkeypatch.setattr("integrity_sdk.agent_identity.requests.get", _get)
    entry = agent_identity.resolve_agent_identities([long_did], ORACLE_URL)[long_did]
    assert entry["display_name"] != long_did
    assert entry["display_name"] == f"{long_did[:14]}…{long_did[-8:]}"


def test_short_did_returned_unchanged_when_unnamed(fake_oracle, local_labels_file):
    entry = agent_identity.resolve_agent_identities([DID_FULLY_UNKNOWN], ORACLE_URL)[DID_FULLY_UNKNOWN]
    assert entry["display_name"] == DID_FULLY_UNKNOWN


def test_fails_open_when_oracle_unreachable(monkeypatch, local_labels_file):
    def _raise(*a, **k):
        raise requests.ConnectionError("no oracle in this test")

    monkeypatch.setattr("integrity_sdk.agent_identity.requests.get", _raise)
    result = agent_identity.resolve_agent_identities([DID_WITH_HANDLE], ORACLE_URL)
    entry = result[DID_WITH_HANDLE]
    assert entry["on_chain"] is False
    assert entry["seen"] is False
    assert entry["display_name"]  # never empty, falls back to shortened DID
