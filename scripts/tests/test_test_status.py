from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]


def _load(name: str, filename: str):
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def recorder(tmp_path, monkeypatch):
    module = _load("record_test_status_under_test", "record_test_status.py")
    monkeypatch.setattr(module, "STATUS", tmp_path / ".integrity-test-status")
    hashes = iter(["0xaaa"] * 20)
    monkeypatch.setattr(module, "_tree_hash", lambda: next(hashes))
    module.set_hashes = lambda values: monkeypatch.setattr(  # type: ignore[attr-defined]
        module, "_tree_hash", lambda: next(iter(values))
    )
    raw_main = module.main
    module.raw_main = raw_main
    module.main = lambda args: raw_main(["--run-id", "test-run", *args])
    return module


def test_mixed_tree_results_cannot_be_rebound_at_finalize(recorder, monkeypatch, capsys):
    assert recorder.main(["--begin", "a", "b"]) == 0
    monkeypatch.setattr(recorder, "_tree_hash", lambda: "0xaaa")
    assert recorder.main(["a", "pass"]) == 0
    monkeypatch.setattr(recorder, "_tree_hash", lambda: "0xbbb")
    assert recorder.main(["b", "pass"]) == 0
    assert recorder.main(["--finalize"]) == 2
    doc = json.loads(recorder.STATUS.read_text())
    assert doc["finalized"] is False
    assert "tree_hash" not in doc
    assert "a" in capsys.readouterr().err


def test_complete_same_tree_run_finalizes(recorder):
    assert recorder.main(["--begin", "a", "b"]) == 0
    assert recorder.main(["a", "pass"]) == 0
    assert recorder.main(["b", "pass"]) == 0
    assert recorder.main(["--finalize"]) == 0
    doc = json.loads(recorder.STATUS.read_text())
    assert doc["finalized"] is True
    assert doc["overall"] == "pass"
    assert doc["tree_hash"] == "0xaaa"
    assert {entry["tree_hash"] for entry in doc["suites"].values()} == {"0xaaa"}


def test_missing_and_unexpected_suites_fail_closed(recorder):
    assert recorder.main(["--begin", "a", "b"]) == 0
    assert recorder.main(["unexpected", "pass"]) == 2
    assert recorder.main(["a", "pass"]) == 0
    assert recorder.main(["--finalize"]) == 2


def test_failed_run_is_persisted_and_returns_nonzero(recorder):
    assert recorder.main(["--begin", "a"]) == 0
    assert recorder.main(["a", "fail", "assertion failed"]) == 0
    assert recorder.main(["--finalize"]) == 1
    doc = json.loads(recorder.STATUS.read_text())
    assert doc["finalized"] is True
    assert doc["overall"] == "fail"


def test_record_after_finalize_invalidates_attestation(recorder):
    assert recorder.main(["--begin", "a"]) == 0
    assert recorder.main(["a", "pass"]) == 0
    assert recorder.main(["--finalize"]) == 0
    assert recorder.main(["a", "pass", "rerun"]) == 0
    doc = json.loads(recorder.STATUS.read_text())
    assert doc["finalized"] is False
    assert "overall" not in doc and "tree_hash" not in doc


@pytest.mark.parametrize(
    "payload",
    ["not json", json.dumps({"suites": {}}), json.dumps({"schema_version": 2, "suites": {}})],
)
def test_malformed_and_legacy_status_are_not_silently_migrated(recorder, payload):
    recorder.STATUS.write_text(payload)
    assert recorder.main(["a", "pass"]) == 2
    assert recorder.main(["--finalize"]) == 2


def test_invalid_outcome_and_unknown_tree_fail_closed(recorder, monkeypatch):
    assert recorder.main(["--begin", "a"]) == 0
    assert recorder.main(["a", "maybe"]) == 2
    monkeypatch.setattr(recorder, "_tree_hash", lambda: "unknown")
    assert recorder.main(["a", "pass"]) == 2


def test_run_id_mismatch_cannot_mix_results(recorder):
    assert recorder.main(["--begin", "a"]) == 0
    assert recorder.raw_main(["--run-id", "other-run", "a", "pass"]) == 2


def _valid_status(tree: str = "0xaaa") -> dict:
    suites = ["contracts", "zkp", "oracle", "sdk", "cli", "bcc", "userapi", "dashboard"]
    return {
        "schema_version": 2,
        "run_id": "test-run",
        "suite_profile": "integrity-core-root-v1",
        "expected_suites": suites,
        "suites": {
            name: {"outcome": "pass", "detail": "", "at": 1, "tree_hash": tree}
            for name in suites
        },
        "started_at": 1,
        "finished_at": 2,
        "tree_hash": tree,
        "overall": "pass",
        "finalized": True,
    }


def test_leaf_consumer_accepts_only_consistent_finalized_v2(tmp_path, monkeypatch):
    vault = _load("vault_commit_leaf_under_test", "vault_commit_leaf.py")
    status = tmp_path / ".integrity-test-status"
    monkeypatch.setattr(vault, "TEST_STATUS_FILE", status)
    monkeypatch.setattr(vault, "_current_tree_hash", lambda: "0xaaa")

    status.write_text(json.dumps(_valid_status()))
    assert vault._test_result_hash().startswith("0x")

    invalid_docs = [
        {**_valid_status(), "finalized": False},
        {**_valid_status(), "schema_version": 1},
        {**_valid_status(), "overall": "fail"},
        {**_valid_status(), "expected_suites": ["a", "b"]},
        {**_valid_status(), "suites": {"a": {"outcome": "pass", "tree_hash": "0xbbb"}}},
    ]
    for doc in invalid_docs:
        status.write_text(json.dumps(doc))
        assert vault._test_result_hash() == "unverified"


def test_leaf_consumer_reports_explicit_tree_mismatch_as_stale(tmp_path, monkeypatch):
    vault = _load("vault_commit_leaf_stale_under_test", "vault_commit_leaf.py")
    status = tmp_path / ".integrity-test-status"
    status.write_text(json.dumps(_valid_status("0xold")))
    monkeypatch.setattr(vault, "TEST_STATUS_FILE", status)
    monkeypatch.setattr(vault, "_current_tree_hash", lambda: "0xnew")
    assert vault._test_result_hash() == "unverified:stale"


def test_leaf_consumer_rejects_self_declared_custom_subset(tmp_path, monkeypatch):
    vault = _load("vault_commit_leaf_subset_under_test", "vault_commit_leaf.py")
    status = tmp_path / ".integrity-test-status"
    doc = _valid_status()
    doc["suite_profile"] = "custom"
    doc["expected_suites"] = ["a"]
    doc["suites"] = {"a": {"outcome": "pass", "tree_hash": "0xaaa"}}
    status.write_text(json.dumps(doc))
    monkeypatch.setattr(vault, "TEST_STATUS_FILE", status)
    monkeypatch.setattr(vault, "_current_tree_hash", lambda: "0xaaa")
    assert vault._test_result_hash() == "unverified"


def test_leaf_consumer_rejects_unknown_and_malformed_suite_names(tmp_path, monkeypatch):
    vault = _load("vault_commit_leaf_unknown_under_test", "vault_commit_leaf.py")
    status = tmp_path / ".integrity-test-status"
    monkeypatch.setattr(vault, "TEST_STATUS_FILE", status)
    monkeypatch.setattr(vault, "_current_tree_hash", lambda: "unknown")
    status.write_text(json.dumps(_valid_status("unknown")))
    assert vault._test_result_hash() == "unverified"

    malformed = _valid_status()
    malformed["expected_suites"] = [["not-hashable"]]
    status.write_text(json.dumps(malformed))
    monkeypatch.setattr(vault, "_current_tree_hash", lambda: "0xaaa")
    assert vault._test_result_hash() == "unverified"
