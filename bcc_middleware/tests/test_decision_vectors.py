"""BCC interprets a policy result exactly as the shared decision vectors say (integrity-core B2 stage 4).

`integrity-sdk/tests/conformance/decision_vectors.json` is shared with the SDK (which runs it through `resolve()`) and
with xibalba-shield (which runs it through its own engine). This file runs every `scope: result` vector through BCC's
OWN code path -- `PackPolicy.decide_sync`, including its fixed enforce mode, its event class, and the way it forwards
the evaluator's raw result -- with only the OPA transport stubbed to return the vector's result. That is the seam a
gate could get wrong while `resolve()` itself is right: Shield did, see its runner.

The stubbed transport is the one thing replaced; what is being tested is BCC's glue, not OPA.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.clinical_allowlist import ClinicalAllowlist
from app.pack_policy import EVENT_CLASS, PackPolicy
from integrity_sdk.core.decision import NO_MATCH
from integrity_sdk.core.packs import LoadedPack

VECTOR_FILE = Path(__file__).resolve().parents[2] / "integrity-sdk" / "tests" / "conformance" / "decision_vectors.json"
VECTORS = [v for v in json.loads(VECTOR_FILE.read_text())["vectors"] if v["scope"] == "result"]


class StubOpa:
    """The OPA transport: returns the vector's raw result, or NO_MATCH when it was undefined."""

    def __init__(self, result):
        self.result = result
        self.installs = 0

    def query(self, pack, opa_input):
        return self.result

    def install(self, pack):  # a NO_MATCH makes BCC re-install a forgetful OPA and ask once more
        self.installs += 1


def policy_for(vector) -> PackPolicy:
    pack = LoadedPack(
        manifest={"name": "vectors", "version": "0", "entrypoint": "data.vectors.decision",
                  "event_classes": {EVENT_CLASS: {"no_match": vector["default"]}}},
        files={}, pack_hash="sha256:" + "11" * 32, signer_key="z6Mk-test",
    )
    raw = vector["result"]
    result = NO_MATCH if isinstance(raw, dict) and raw.get("$undefined") is True else raw
    return PackPolicy(pack, StubOpa(result), ClinicalAllowlist(None))


def test_the_vectors_cover_all_three_defaults_and_malformed_results():
    assert {v["default"] for v in VECTORS} == {"deny", "log_only", "permit"}
    assert sum(1 for v in VECTORS if v["expect"]["reason_code"] == "INTEGRITY_MALFORMED_DECISION") >= 30


@pytest.mark.parametrize("vector", VECTORS, ids=lambda v: v["name"])
def test_bcc_interprets_the_result_as_the_vector_says(vector):
    expect = vector["expect"]
    verdict = policy_for(vector).decide_sync({"agent_id": "did:integrity:x", "intent_type": "payment"})
    assert verdict.allow == (not expect["blocks"]), f"{vector['name']}: BCC {'allowed' if verdict.allow else 'denied'}"
    assert verdict.reason_code == expect["reason_code"]
    assert list(verdict.controls) == expect["controls"]
