"""AIS control-zone gate (app/ais_zone.py, chain.resolve_control_zone, main.py step 5a).

The oracle computes a control zone (green / yellow / red) for every agent, and until this gate nothing
read it. These tests pin the first place the score restricts a tool call:

  * `BCC_AIS_ZONE_MODE=off` (the default) makes NO oracle request for the zone and returns exactly the
    response the pipeline returned before the gate existed;
  * an intent type classifies as read / draft / execute / escalate by EXACT match against a map, and
    anything not in the map is `execute`, never `read`;
  * green permits read+draft+execute, yellow read+draft, red read only; escalate is always permitted;
  * `enforce` denies through the ordinary deny path (so the global `BCC_SHADOW_MODE` still wins),
    `shadow` records a would-deny and lets the request continue through every later gate;
  * a zone that cannot be read is permitted or treated as red according to `BCC_AIS_ZONE_UNAVAILABLE`;
  * a zone denial is not charged to the circuit breaker or the token budget, and gets a receipt that
    verifies offline;
  * the zone cache has a fresh TTL and a bounded last-known-good, and an unrecognised zone string is
    "unavailable", not green.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from httpx import Response
from starlette.testclient import TestClient

import app.main as main_module
from app import ais_zone, chain
from app import verification_token as verification_token_module
from app.config import Settings
from app.gate_receipts import NO_PACK_HASH, BccReceipts
from app.main import run_intercept
from app.merkle import MerkleBatcher
from app.quarantine import QuarantineStatus
from integrity_sdk.core import verify_log
from integrity_sdk.did import Keypair
from tests.helpers import make_commitment_model, new_agent, sign_commitment

ORACLE = "http://oracle.test"
RATIONALE = "A sufficiently long declared intent rationale."
INTENT = {
    "read": "claude_tool:Read",
    "draft": "claude_tool:Edit",
    "execute": "claude_tool:Bash",
    "escalate": "claude_tool:AskUserQuestion",
}
PERMITTED = {
    "green": {"read", "draft", "execute", "escalate"},
    "yellow": {"read", "draft", "escalate"},
    "red": {"read", "escalate"},
}


# ------------------------------------------------------------------------------- classification


@pytest.mark.parametrize("intent_type, expected", [
    ("claude_tool:Read", "read"),
    ("claude_tool:Glob", "read"),
    ("claude_tool:Grep", "read"),
    ("claude_tool:Write", "draft"),
    ("claude_tool:Edit", "draft"),
    ("claude_tool:Bash", "execute"),
    ("claude_tool:AskUserQuestion", "escalate"),
])
def test_default_map_classifies_the_common_claude_code_tools(intent_type, expected):
    assert ais_zone.classify(intent_type, ais_zone.DEFAULT_ACTION_CLASSES) == expected


@pytest.mark.parametrize("intent_type", [
    "claude_tool:SomeToolNobodyMapped",
    "payment",
    "",
    "Read",                             # a bare tool name is not an intent type
    "claude_tool:Read:credential",      # the hook appended a risk class: no longer a plain read
    "hermes_tool:Read",                 # another runtime's tool of the same name is not this one
    " claude_tool:Read",                # exact match only: no normalisation that could widen a match
    "CLAUDE_TOOL:READ",
])
def test_an_intent_type_that_is_not_in_the_map_is_execute_never_read(intent_type):
    assert ais_zone.classify(intent_type, ais_zone.DEFAULT_ACTION_CLASSES) == "execute"


@pytest.mark.parametrize("zone", ["green", "yellow", "red"])
@pytest.mark.parametrize("action_class", ["read", "draft", "execute", "escalate"])
def test_zone_table(zone, action_class):
    assert ais_zone.permits(zone, action_class) is (action_class in PERMITTED[zone])


@pytest.mark.parametrize("zone", [None, "", "GREEN", "blue", "amber"])
def test_an_unrecognised_zone_permits_only_what_every_zone_permits(zone):
    """`permits` is never the place an unknown zone turns into green: the caller must apply the
    unavailable posture. Asked directly, it answers as the most restricted zone."""
    assert ais_zone.permits(zone, "read") is True
    assert ais_zone.permits(zone, "escalate") is True
    assert ais_zone.permits(zone, "draft") is False
    assert ais_zone.permits(zone, "execute") is False


# ------------------------------------------------------------------------------------- settings


def test_the_gate_is_off_by_default(monkeypatch):
    for name in ("BCC_AIS_ZONE_MODE", "BCC_AIS_ZONE_UNAVAILABLE", "BCC_AIS_ZONE_ACTION_CLASSES"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings()
    assert settings.ais_zone_mode == "off"
    assert settings.ais_zone_unavailable == "allow"
    assert settings.ais_zone_action_classes == ais_zone.DEFAULT_ACTION_CLASSES


def test_settings_read_the_environment(monkeypatch):
    monkeypatch.setenv("BCC_AIS_ZONE_MODE", "enforce")
    monkeypatch.setenv("BCC_AIS_ZONE_UNAVAILABLE", "restrict")
    monkeypatch.setenv("BCC_AIS_ZONE_ACTION_CLASSES", json.dumps({"claude_tool:Bash": "draft", "payment": "read"}))
    settings = Settings()
    assert (settings.ais_zone_mode, settings.ais_zone_unavailable) == ("enforce", "restrict")
    # Overrides are merged over the defaults: an operator changes one tool without restating the rest.
    assert settings.ais_zone_action_classes["claude_tool:Bash"] == "draft"
    assert settings.ais_zone_action_classes["payment"] == "read"
    assert settings.ais_zone_action_classes["claude_tool:Read"] == "read"


@pytest.mark.parametrize("kwargs", [
    {"ais_zone_mode": "on"},
    {"ais_zone_mode": "Enforce"},
    {"ais_zone_unavailable": "deny"},
    {"ais_zone_action_classes": {"claude_tool:Bash": "anything"}},
    {"ais_zone_action_classes": {"claude_tool:Bash": 1}},
])
def test_settings_reject_values_outside_the_vocabulary(kwargs):
    with pytest.raises(ValueError):
        Settings(**kwargs)


@pytest.mark.parametrize("raw", ["not json", "[]", '"read"', '{"claude_tool:Bash": "sudo"}'])
def test_an_unusable_action_class_override_refuses_to_start(monkeypatch, raw):
    """A typo here must not quietly leave the defaults (or worse, an empty map) deciding."""
    monkeypatch.setenv("BCC_AIS_ZONE_ACTION_CLASSES", raw)
    with pytest.raises(ValueError):
        Settings()


# ------------------------------------------------------------------------------ zone resolution

AGENT = "did:integrity:zone-cache-test"


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


@pytest.fixture()
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(chain, "_clock", c)
    monkeypatch.setattr(chain, "_ZONE_FRESH_TTL", 60.0)
    monkeypatch.setattr(chain, "_ZONE_MAX_STALE", 300.0)
    chain.clear_zone_cache()
    yield c
    chain.clear_zone_cache()


def _ais(zone) -> Response:
    return Response(200, json={"agent_id": AGENT, "ais": 910.0, "closed_loop_reward": {"control_zone": zone, "r_total": 1.0}})


def _route(mock, **kw):
    return mock.get(f"{ORACLE}/v1/agent/{AGENT}/ais").mock(**kw)


@pytest.mark.parametrize("zone", ["green", "yellow", "red"])
def test_zone_is_read_from_closed_loop_reward(clock, zone):
    with respx.mock(assert_all_called=False) as mock:
        _route(mock, return_value=_ais(zone))
        assert chain.resolve_control_zone(AGENT, oracle_url=ORACLE) == zone


def test_a_fresh_zone_is_served_without_calling_the_oracle(clock):
    with respx.mock(assert_all_called=False) as mock:
        r = _route(mock, return_value=_ais("green"))
        assert chain.resolve_control_zone(AGENT, oracle_url=ORACLE) == "green"
        clock.t += 59
        assert chain.resolve_control_zone(AGENT, oracle_url=ORACLE) == "green"
        assert r.call_count == 1


def test_a_demotion_is_picked_up_after_the_ttl(clock):
    with respx.mock(assert_all_called=False) as mock:
        r = _route(mock, side_effect=[_ais("green"), _ais("red")])
        assert chain.resolve_control_zone(AGENT, oracle_url=ORACLE) == "green"
        clock.t += 61
        assert chain.resolve_control_zone(AGENT, oracle_url=ORACLE) == "red"
        assert r.call_count == 2


@pytest.mark.parametrize("failure", [httpx.ConnectTimeout("asleep"), Response(503)])
def test_a_transient_failure_serves_the_last_known_good_zone(clock, failure):
    with respx.mock(assert_all_called=False) as mock:
        _route(mock, side_effect=[_ais("yellow"), failure])
        assert chain.resolve_control_zone(AGENT, oracle_url=ORACLE) == "yellow"
        clock.t += 61
        assert chain.resolve_control_zone(AGENT, oracle_url=ORACLE) == "yellow"


def test_last_known_good_expires_after_max_stale(clock):
    with respx.mock(assert_all_called=False) as mock:
        _route(mock, side_effect=[_ais("green"), httpx.ConnectTimeout("down")])
        assert chain.resolve_control_zone(AGENT, oracle_url=ORACLE) == "green"
        clock.t += 301
        assert chain.resolve_control_zone(AGENT, oracle_url=ORACLE) is None


def test_no_prior_value_and_oracle_down_is_unavailable(clock):
    with respx.mock(assert_all_called=False) as mock:
        _route(mock, side_effect=httpx.ConnectError("refused"))
        assert chain.resolve_control_zone(AGENT, oracle_url=ORACLE) is None


def test_an_authoritative_404_is_never_answered_from_stale(clock):
    with respx.mock(assert_all_called=False) as mock:
        _route(mock, side_effect=[_ais("green"), Response(404), httpx.ConnectTimeout("down")])
        assert chain.resolve_control_zone(AGENT, oracle_url=ORACLE) == "green"
        clock.t += 61
        assert chain.resolve_control_zone(AGENT, oracle_url=ORACLE) is None
        clock.t += 61  # oracle now unreachable: the evicted green must not come back
        assert chain.resolve_control_zone(AGENT, oracle_url=ORACLE) is None


@pytest.mark.parametrize("body", [
    {"closed_loop_reward": {"control_zone": "GREEN"}},      # exact vocabulary only
    {"closed_loop_reward": {"control_zone": "blue"}},
    {"closed_loop_reward": {"control_zone": ""}},
    {"closed_loop_reward": {"control_zone": None}},
    {"closed_loop_reward": {"control_zone": 1}},
    {"closed_loop_reward": {"control_zone": ["green"]}},
    {"closed_loop_reward": {}},
    {"closed_loop_reward": "green"},
    {"control_zone": "green"},                              # wrong place: not the documented field
    {},
    ["green"],
])
def test_an_invalid_zone_is_unavailable_and_not_green(clock, body):
    with respx.mock(assert_all_called=False) as mock:
        _route(mock, return_value=Response(200, json=body))
        assert chain.resolve_control_zone(AGENT, oracle_url=ORACLE) is None


def test_a_body_that_is_not_json_is_unavailable(clock):
    with respx.mock(assert_all_called=False) as mock:
        _route(mock, return_value=Response(200, text="<html>gateway</html>"))
        assert chain.resolve_control_zone(AGENT, oracle_url=ORACLE) is None


def test_an_invalid_zone_is_never_cached(clock):
    with respx.mock(assert_all_called=False) as mock:
        r = _route(mock, side_effect=[_ais("purple"), _ais("red")])
        assert chain.resolve_control_zone(AGENT, oracle_url=ORACLE) is None
        assert chain.resolve_control_zone(AGENT, oracle_url=ORACLE) == "red"  # asked again, not served a cached "purple"
        assert r.call_count == 2


# ------------------------------------------------------------------------------------ pipeline


class Pipeline:
    """One agent in front of a real OPA running bcc.rego. The zone answer is a counting stub so each
    test states the zone it is about; the tests further down use the real resolver over respx."""

    def __init__(self, monkeypatch, opa_url: str) -> None:
        self.monkeypatch = monkeypatch
        self.opa_url = opa_url
        self.agent_id, self.key = new_agent()
        self.nonce = 0
        self.zone: str | None = "green"
        self.zone_calls: list[str] = []
        self.reports: list[dict] = []
        monkeypatch.setattr(main_module, "resolve_control_zone", self._zone)
        monkeypatch.setattr(main_module, "resolve_verification_tier", lambda agent_id, oracle_url=None: 1)
        monkeypatch.setattr(main_module, "check_quarantine_status", lambda settings, agent_id: (QuarantineStatus.CLEAR, ""))
        monkeypatch.setattr(main_module, "_report_decision_background", lambda settings, **kw: self.reports.append(kw))
        monkeypatch.setattr(main_module, "batcher", MerkleBatcher(batch_size=999))
        monkeypatch.setattr(main_module, "receipts", None)
        main_module.circuit_breaker.reset()
        main_module.nonce_store.reset()
        main_module.token_budget_enforcer.reset()

    def _zone(self, agent_id: str, *, oracle_url: str) -> str | None:
        self.zone_calls.append(agent_id)
        return self.zone

    def settings(self, **extra) -> Settings:
        base = dict(opa_url=self.opa_url, oracle_url=ORACLE, merkle_batch_size=999, shadow_mode=False,
                    quarantine_fail_closed_intents=frozenset(), spool_enabled=False)
        return Settings(**{**base, **extra})

    def payload(self, intent_type: str, token_count: int | None = None) -> dict:
        self.nonce += 1
        payload = sign_commitment(self.key, agent_id=self.agent_id, intent_type=intent_type, nonce=self.nonce,
                                  intent_rationale=RATIONALE)
        payload["trace_id"] = "4bf92f3577b34da6a3ce929d0e0e4736"   # unsigned; bcc.rego requires them for agent tools
        payload["span_id"] = "00f067aa0ba902b7"
        if token_count is not None:
            payload["token_count"] = token_count
        return payload

    async def go(self, settings: Settings, intent_type: str, **kw):
        return await run_intercept(make_commitment_model(**self.payload(intent_type, **kw)), settings)

    def decisions(self) -> list[tuple[str, str | None]]:
        return [(r["decision"], r.get("reason_code")) for r in self.reports]


@pytest.fixture()
def pipeline(monkeypatch, real_opa_server):
    return Pipeline(monkeypatch, real_opa_server)


@pytest.mark.parametrize("zone", ["green", "yellow", "red"])
@pytest.mark.parametrize("action_class", ["read", "draft", "execute", "escalate"])
async def test_enforce_permits_exactly_what_the_zone_permits(pipeline, zone, action_class):
    pipeline.zone = zone
    resp = await pipeline.go(pipeline.settings(ais_zone_mode="enforce"), INTENT[action_class])
    if action_class in PERMITTED[zone]:
        assert resp.authorized is True and resp.enforced is True
        assert resp.verification_token is not None
        assert resp.reason is None and resp.shadow_would_deny is False
        assert pipeline.decisions() == [("allow", None)]
    else:
        assert resp.authorized is False
        assert resp.reason.startswith("AIS_ZONE_RESTRICTED: ")
        assert zone in resp.reason and action_class in resp.reason and INTENT[action_class] in resp.reason
        assert resp.verification_token is None and resp.batch_index is None
        assert pipeline.decisions() == [("deny", "AIS_ZONE_RESTRICTED")]


async def test_an_unmapped_tool_is_execute_so_yellow_denies_it(pipeline):
    pipeline.zone = "yellow"
    resp = await pipeline.go(pipeline.settings(ais_zone_mode="enforce"), "claude_tool:SomeToolNobodyMapped")
    assert resp.authorized is False
    assert resp.reason.startswith("AIS_ZONE_RESTRICTED: ") and "execute" in resp.reason


async def test_the_action_class_map_is_configurable(pipeline):
    pipeline.zone = "red"
    settings = pipeline.settings(ais_zone_mode="enforce", ais_zone_action_classes={"claude_tool:Bash": "read"})
    assert (await pipeline.go(settings, "claude_tool:Bash")).authorized is True
    assert (await pipeline.go(settings, "claude_tool:Edit")).authorized is False  # the defaults still apply


async def test_a_class_every_zone_permits_never_asks_the_oracle(pipeline):
    """Reads and escalations are permitted in every zone and under either unavailable posture, so the
    answer cannot change the decision: the gate must not put an oracle hop on those tool calls."""
    pipeline.zone = "red"
    settings = pipeline.settings(ais_zone_mode="enforce", ais_zone_unavailable="restrict")
    assert (await pipeline.go(settings, "claude_tool:Read")).authorized is True
    assert (await pipeline.go(settings, "claude_tool:AskUserQuestion")).authorized is True
    assert pipeline.zone_calls == []
    assert (await pipeline.go(settings, "claude_tool:Bash")).authorized is False
    assert pipeline.zone_calls == [pipeline.agent_id]


# --- shadow: records, never blocks ---------------------------------------------------------------


async def test_zone_shadow_records_a_would_deny_and_lets_the_request_through(pipeline):
    """BCC_SHADOW_MODE=false + BCC_AIS_ZONE_MODE=shadow: every other gate is enforcing, so the request
    must come out as a REAL allow (token, Merkle slot, enforced=True), with the zone's would-deny on
    the audit trail beside it."""
    pipeline.zone = "red"
    resp = await pipeline.go(pipeline.settings(ais_zone_mode="shadow"), "claude_tool:Bash")
    assert resp.authorized is True and resp.enforced is True
    assert resp.verification_token is not None and resp.batch_index == 0
    assert resp.shadow_would_deny is False and resp.reason is None
    assert pipeline.decisions() == [("shadow_deny", "AIS_ZONE_RESTRICTED"), ("allow", None)]
    would_deny = pipeline.reports[0]
    assert "red" in would_deny["detail"] and "execute" in would_deny["detail"]
    assert would_deny["intent_type"] == "claude_tool:Bash"
    assert would_deny["metadata"]["intended_state_hash"]


async def test_zone_shadow_does_not_skip_the_gates_after_it(pipeline, monkeypatch):
    """The reason zone-shadow does not go through `_deny`: under global enforcement `_deny` would have
    to return an allow early, skipping the token budget and the BAA check. A would-deny that is only
    observed must not switch off a gate that is enforcing."""
    monkeypatch.setattr(main_module.token_budget_enforcer, "check_and_record", lambda agent_id, tier, count: (False, "over the limit"))
    pipeline.zone = "red"
    resp = await pipeline.go(pipeline.settings(ais_zone_mode="shadow"), "claude_tool:Bash", token_count=5)
    assert resp.authorized is False
    assert resp.reason.startswith("TOKEN_BUDGET_EXCEEDED: ")
    assert pipeline.decisions() == [("shadow_deny", "AIS_ZONE_RESTRICTED"), ("deny", "TOKEN_BUDGET_EXCEEDED")]


async def test_zone_shadow_records_nothing_for_a_permitted_call(pipeline):
    pipeline.zone = "green"
    resp = await pipeline.go(pipeline.settings(ais_zone_mode="shadow"), "claude_tool:Bash")
    assert resp.authorized is True
    assert pipeline.decisions() == [("allow", None)]


async def test_global_shadow_still_wins_over_zone_enforce(pipeline):
    """BCC_SHADOW_MODE=true + BCC_AIS_ZONE_MODE=enforce: the zone gate asks to deny, and the global
    switch turns that into a would-deny like every other denial. Nothing blocks."""
    pipeline.zone = "red"
    resp = await pipeline.go(pipeline.settings(shadow_mode=True, ais_zone_mode="enforce"), "claude_tool:Bash")
    assert resp.authorized is True and resp.enforced is False
    assert resp.shadow_would_deny is True
    assert resp.reason.startswith("AIS_ZONE_RESTRICTED: ")
    assert pipeline.decisions() == [("shadow_deny", "AIS_ZONE_RESTRICTED")]


async def test_global_shadow_with_zone_shadow_never_blocks(pipeline):
    pipeline.zone = "red"
    resp = await pipeline.go(pipeline.settings(shadow_mode=True, ais_zone_mode="shadow"), "claude_tool:Bash")
    assert resp.authorized is True and resp.enforced is False
    assert resp.verification_token is not None
    assert pipeline.decisions() == [("shadow_deny", "AIS_ZONE_RESTRICTED"), ("allow", None)]


# --- zone unavailable ----------------------------------------------------------------------------


async def test_an_unavailable_zone_is_permitted_by_default(pipeline):
    pipeline.zone = None
    resp = await pipeline.go(pipeline.settings(ais_zone_mode="enforce"), "claude_tool:Bash")
    assert resp.authorized is True and resp.verification_token is not None
    assert pipeline.zone_calls == [pipeline.agent_id]   # it did ask; the answer was "unavailable"
    assert pipeline.decisions() == [("allow", None)]


@pytest.mark.parametrize("action_class, authorized", [("read", True), ("escalate", True), ("draft", False), ("execute", False)])
async def test_an_unavailable_zone_is_red_under_the_restrict_posture(pipeline, action_class, authorized):
    pipeline.zone = None
    settings = pipeline.settings(ais_zone_mode="enforce", ais_zone_unavailable="restrict")
    resp = await pipeline.go(settings, INTENT[action_class])
    assert resp.authorized is authorized
    if not authorized:
        assert resp.reason.startswith("AIS_ZONE_RESTRICTED: ")
        assert "unavailable" in resp.reason   # an operator must be able to tell "demoted" from "could not read"


async def test_restrict_posture_in_zone_shadow_only_records(pipeline):
    pipeline.zone = None
    settings = pipeline.settings(ais_zone_mode="shadow", ais_zone_unavailable="restrict")
    resp = await pipeline.go(settings, "claude_tool:Bash")
    assert resp.authorized is True and resp.verification_token is not None
    assert pipeline.decisions() == [("shadow_deny", "AIS_ZONE_RESTRICTED"), ("allow", None)]


# --- what a zone denial does NOT do --------------------------------------------------------------


async def test_a_zone_denial_does_not_charge_the_circuit_breaker(pipeline):
    """A demoted agent did not attempt a policy violation. If the denial counted, a red agent that
    tried three Bash calls would be locked out of the reads red is supposed to leave it."""
    pipeline.zone = "red"
    settings = pipeline.settings(ais_zone_mode="enforce", circuit_breaker_violation_threshold=1)
    monkey_breaker = main_module.AgentCircuitBreaker(violation_threshold=1, lockout_duration_seconds=60)
    pipeline.monkeypatch.setattr(main_module, "circuit_breaker", monkey_breaker)
    for _ in range(3):
        assert (await pipeline.go(settings, "claude_tool:Bash")).authorized is False
    assert monkey_breaker.is_locked_out(pipeline.agent_id) is False
    read = await pipeline.go(settings, "claude_tool:Read")
    assert read.authorized is True, read.reason


async def test_a_zone_denial_does_not_spend_token_budget(pipeline):
    pipeline.zone = "red"
    resp = await pipeline.go(pipeline.settings(ais_zone_mode="enforce"), "claude_tool:Bash", token_count=500)
    assert resp.authorized is False
    assert main_module.token_budget_enforcer.get_daily_spend(pipeline.agent_id) == 0


async def test_the_gate_runs_only_after_policy_allows(pipeline):
    """A commitment bcc.rego denies is a policy denial (and a violation), whatever the zone."""
    pipeline.zone = "red"
    resp = await pipeline.go(pipeline.settings(ais_zone_mode="enforce"), "claude_tool_bypass")
    assert resp.authorized is False
    assert resp.reason.startswith("OPA_REJECTION: ")
    assert pipeline.zone_calls == []


# --- receipts ------------------------------------------------------------------------------------


def _receipt_settings(pipeline, tmp_path, **extra) -> Settings:
    signer, hmac_file = tmp_path / "receipt.pem", tmp_path / "receipt.hmac"
    signer.write_bytes(Keypair.generate().private_pem())
    hmac_file.write_bytes(bytes(range(32)))
    for path in (signer, hmac_file):
        path.chmod(0o600)
    return pipeline.settings(
        receipt_dir=str(tmp_path / "receipts"), receipt_key_file=str(signer), receipt_hmac_key_file=str(hmac_file),
        receipt_epoch_max_receipts=0, receipt_epoch_max_age_seconds=0, **extra,
    )


def _verified_rows(tmp_path, receipts: BccReceipts) -> list[dict]:
    rows = [json.loads(line) for line in (tmp_path / "receipts" / "receipts.jsonl").read_text().splitlines()]
    verify_log(rows, trusted_signers=[receipts.signer_key], checkpoint=None)
    return rows


async def test_a_zone_denial_is_recorded_as_a_receipt_that_verifies_offline(pipeline, tmp_path):
    """The receipt verifier accepts any non-empty reason_code (it is an open vocabulary), so the new
    code needs no schema change. Proven here with the SDK's own `verify_log`, not asserted in prose."""
    settings = _receipt_settings(pipeline, tmp_path, ais_zone_mode="enforce")
    receipts = BccReceipts.from_settings(settings)
    pipeline.monkeypatch.setattr(main_module, "receipts", receipts)
    pipeline.zone = "red"
    try:
        resp = await pipeline.go(settings, "claude_tool:Bash")
        assert resp.authorized is False and resp.receipt_status == "recorded"
        rows = _verified_rows(tmp_path, receipts)
    finally:
        receipts.close()
    assert len(rows) == 1
    assert (rows[0]["decision"], rows[0]["reason_code"], rows[0]["mode"]) == ("deny", "AIS_ZONE_RESTRICTED", "enforce")
    assert rows[0]["pack_hash"] == NO_PACK_HASH and rows[0]["controls"] == []
    assert rows[0]["seq"] == resp.receipt["seq"]


async def test_under_global_shadow_the_zone_denial_receipt_says_shadow(pipeline, tmp_path):
    settings = _receipt_settings(pipeline, tmp_path, ais_zone_mode="enforce", shadow_mode=True)
    receipts = BccReceipts.from_settings(settings)
    pipeline.monkeypatch.setattr(main_module, "receipts", receipts)
    pipeline.zone = "yellow"
    try:
        resp = await pipeline.go(settings, "claude_tool:Bash")
        assert resp.authorized is True and resp.shadow_would_deny is True
        rows = _verified_rows(tmp_path, receipts)
    finally:
        receipts.close()
    assert [(r["decision"], r["reason_code"], r["mode"]) for r in rows] == [("deny", "AIS_ZONE_RESTRICTED", "shadow")]


async def test_zone_shadow_leaves_the_allow_receipt_as_the_only_receipt(pipeline, tmp_path):
    """Zone-shadow's would-deny goes to the audit trail, not the receipt log: the receipt records the
    decision that was actually made about the request, and that was a permit."""
    settings = _receipt_settings(pipeline, tmp_path, ais_zone_mode="shadow")
    receipts = BccReceipts.from_settings(settings)
    pipeline.monkeypatch.setattr(main_module, "receipts", receipts)
    pipeline.zone = "red"
    try:
        resp = await pipeline.go(settings, "claude_tool:Bash")
        assert resp.authorized is True
        rows = _verified_rows(tmp_path, receipts)
    finally:
        receipts.close()
    assert [(r["decision"], r["mode"]) for r in rows] == [("permit", "enforce")]
    assert ("shadow_deny", "AIS_ZONE_RESTRICTED") in pipeline.decisions()


# --- off: no oracle request, identical response --------------------------------------------------


class RealResolver(Pipeline):
    """As Pipeline, but with the REAL chain.resolve_control_zone, so respx sees what it sends."""

    def __init__(self, monkeypatch, opa_url: str) -> None:
        super().__init__(monkeypatch, opa_url)
        monkeypatch.setattr(main_module, "resolve_control_zone", chain.resolve_control_zone)
        chain.clear_zone_cache()


@pytest.fixture()
def real(monkeypatch, real_opa_server):
    yield RealResolver(monkeypatch, real_opa_server)
    chain.clear_zone_cache()


def _oracle(mock, agent_id: str, zone: str):
    mock.route(host="127.0.0.1").pass_through()   # the real OPA
    return mock.get(f"{ORACLE}/v1/agent/{agent_id}/ais").mock(
        return_value=Response(200, json={"closed_loop_reward": {"control_zone": zone}}))


async def test_off_makes_no_oracle_request_for_the_zone(real):
    """The oracle would answer `red` for a Bash call. With the gate off nothing may ask it."""
    with respx.mock(assert_all_called=False) as mock:
        ais_route = _oracle(mock, real.agent_id, "red")
        resp = await real.go(real.settings(), "claude_tool:Bash")                       # default
        explicit = await real.go(real.settings(ais_zone_mode="off"), "claude_tool:Bash")
        assert ais_route.call_count == 0
        assert [r.request.url.path for r in mock.calls if r.request.url.host == "oracle.test"] == []
    assert resp.authorized is True and explicit.authorized is True


async def test_the_same_request_does_ask_the_oracle_once_the_gate_is_on(real):
    """The control for the test above: the route it watches is the one the gate really uses."""
    with respx.mock(assert_all_called=False) as mock:
        ais_route = _oracle(mock, real.agent_id, "red")
        resp = await real.go(real.settings(ais_zone_mode="enforce"), "claude_tool:Bash")
        assert ais_route.call_count == 1
    assert resp.authorized is False and resp.reason.startswith("AIS_ZONE_RESTRICTED: ")


async def test_off_returns_exactly_the_response_the_pipeline_returned_before_the_gate(real):
    settings = real.settings()
    payload = real.payload("claude_tool:Bash")
    with respx.mock(assert_all_called=False) as mock:
        _oracle(mock, real.agent_id, "red")
        resp = await run_intercept(make_commitment_model(**payload), settings)
    expected_token = verification_token_module._compute(settings, real.agent_id, payload["nonce"], payload["intended_state_hash"])
    assert resp.model_dump() == {
        "authorized": True,
        "invocation_id": None,
        "reason": None,
        "enforced": True,
        "shadow_would_deny": False,
        "verification_token": expected_token,
        "batch_index": 0,
        "receipt": None,
        "receipt_status": None,
        "token_budget_remaining": None,
    }
    assert real.decisions() == [("allow", None)]
    assert set(real.reports[0]["metadata"]) == {"leaf", "batch_index", "verification_token", "intended_state_hash", "invocation_id"}


def test_off_over_http_has_the_same_body_as_before(real):
    """Through the route, so the serialized JSON (not just the model) carries no new key."""
    settings = real.settings()
    real.monkeypatch.setattr(main_module, "default_settings", settings)
    payload = real.payload("claude_tool:Bash")
    with respx.mock(assert_all_called=False) as mock:
        ais_route = _oracle(mock, real.agent_id, "red")
        mock.route(host="testserver").pass_through()
        body = TestClient(main_module.app).post("/v1/bcc/intercept", json=payload).json()
        assert ais_route.call_count == 0
    assert sorted(body) == sorted([
        "authorized", "invocation_id", "reason", "enforced", "shadow_would_deny", "verification_token",
        "batch_index", "receipt", "receipt_status", "token_budget_remaining",
    ])
    assert body["authorized"] is True and body["enforced"] is True and body["reason"] is None


def test_health_is_unchanged_by_the_gate(real):
    """`/health` gains no key: with the gate off the service's outputs are the ones it had."""
    real.monkeypatch.setattr(main_module, "default_settings", real.settings())
    off = TestClient(main_module.app).get("/health").json()
    real.monkeypatch.setattr(main_module, "default_settings", real.settings(ais_zone_mode="enforce"))
    on = TestClient(main_module.app).get("/health").json()
    assert sorted(off) == sorted(on)
    assert not any("zone" in key for key in off)
