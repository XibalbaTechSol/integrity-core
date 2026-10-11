"""The shared decision-contract vectors, run through `resolve()` (integrity-core B2 stage 4).

`tests/conformance/decision_vectors.json` is the single statement of how a policy result is interpreted. This file
runs it through the SDK's `resolve()`. `bcc_middleware/tests/test_decision_vectors.py` and xibalba-shield's
`tests/test_decision_vectors.py` run the same file through each gate's OWN code path, so "BCC and Shield interpret a
policy result the same way" is checked rather than asserted.

Expectations in the file are written by hand. They are deliberately not generated from `resolve()`: a vector set
derived from the implementation can only ever agree with it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from integrity_sdk.core import decision as d

VECTOR_FILE = Path(__file__).resolve().parents[1] / "conformance" / "decision_vectors.json"
DOCUMENT = json.loads(VECTOR_FILE.read_text())
VECTORS = DOCUMENT["vectors"]
EVENT = "test.event"


def result_of(vector):
    """Decode the file's result encoding: {"$undefined": true} is an evaluator result that was undefined."""
    raw = vector["result"]
    return d.NO_MATCH if isinstance(raw, dict) and raw.get("$undefined") is True else raw


def run(vector):
    defaults = None if vector.get("no_pack") else {EVENT: vector.get("invalid_default", vector["default"])}
    event_class = "undeclared.event" if vector.get("unknown_event_class") else EVENT
    error = RuntimeError("evaluator failed") if vector.get("evaluator_error") else None
    return d.resolve(event_class, result_of(vector), event_defaults=defaults, mode=vector["mode"], evaluator_error=error)


def test_the_file_declares_the_contract_it_tests():
    assert DOCUMENT["contract"] == d.DECISION_CONTRACT


def test_the_file_is_well_formed():
    names = [v["name"] for v in VECTORS]
    assert len(names) == len(set(names)), "vector names must be unique"
    for v in VECTORS:
        assert v["why"].strip(), f"{v['name']}: say why this vector exists"
        assert v["scope"] in ("result", "resolve"), v["name"]
        assert v["mode"] in ("enforce", "shadow", "observe"), v["name"]
        assert v["default"] in d.NO_MATCH_DEFAULTS, v["name"]
        expect = v["expect"]
        if "raises" in expect:
            assert set(expect) == {"raises"}, v["name"]
        else:
            assert set(expect) == {"decision", "reason_code", "controls", "blocks"}, v["name"]
            assert expect["decision"] in d.DECISIONS and isinstance(expect["blocks"], bool), v["name"]
    result_scope = [v for v in VECTORS if v["scope"] == "result"]
    # Gates run scope=result vectors with a fixed enforce mode and a real pack, so those vectors must not ask for more.
    assert all(v["mode"] == "enforce" and not v.get("no_pack") and not v.get("evaluator_error")
               and not v.get("unknown_event_class") for v in result_scope)


@pytest.mark.parametrize("vector", VECTORS, ids=lambda v: v["name"])
def test_resolve_matches_the_vector(vector):
    expect = vector["expect"]
    if "raises" in expect:
        with pytest.raises(ValueError):
            run(vector)
        return
    got = run(vector)
    assert (got.decision, got.reason_code, list(got.controls), got.blocks) == (
        expect["decision"], expect["reason_code"], expect["controls"], expect["blocks"]
    )


def test_every_gate_level_outcome_and_every_default_is_exercised():
    """A vector set that never reaches a branch cannot catch a change to it."""
    seen_codes = {v["expect"]["reason_code"] for v in VECTORS if "reason_code" in v["expect"]}
    assert {d.REASON_NO_MATCH, d.REASON_EVALUATOR_ERROR, d.REASON_MALFORMED_DECISION, d.REASON_UNKNOWN_EVENT_CLASS,
            d.REASON_NO_PACK} <= seen_codes
    for default in d.NO_MATCH_DEFAULTS:
        assert any(v["result"] == {"$undefined": True} and v["default"] == default and v["scope"] == "result"
                   for v in VECTORS), f"no result-scope vector for the {default} default"
    assert any(v["mode"] == "shadow" and not v["expect"].get("blocks", True) for v in VECTORS if "raises" not in v["expect"])
