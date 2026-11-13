"""Local AIS from a gate's own receipts (`integrity_sdk.core.ais_local`)."""

from __future__ import annotations

import json
import os

import pytest

from integrity_sdk.core.ais_local import (
    CLEAN,
    LOCAL_RECEIPT_PROFILE,
    REASON_ZONE_RESTRICTED,
    UNKNOWN_ZONE,
    VIOLATION,
    LocalReceiptScorer,
    LocalScorerSettings,
    ReceiptLogTail,
    ReceiptLogZoneSource,
    classify_receipt,
    score_window,
)
from integrity_sdk.core.ais_reward import ZONE_POLICY_ABSOLUTE, ZonePolicy, ZoneThresholds

AGENT = "did:key:agent-a"


def receipt(decision: str, reason_code: str = "OK", agent: str = AGENT, timestamp: str = "2026-11-12T00:00:00Z"):
    return {"agent_did": agent, "decision": decision, "reason_code": reason_code, "timestamp": timestamp,
            "controls": []}


def settings(**overrides) -> LocalScorerSettings:
    base = dict(window_size=50, min_observations=10, default_tier=3)
    base.update(overrides)
    return LocalScorerSettings(**base)


# --------------------------------------------------------------------------- classification ---

@pytest.mark.parametrize("decision,reason,expected", [
    ("permit", "OK", CLEAN),
    ("deny", "PACK_RULE", VIOLATION),
    ("log_only", "PACK_RULE", VIOLATION),
    ("deny", "INTEGRITY_NO_MATCH", VIOLATION),  # an action outside the signed graph is the violation
    ("deny", REASON_ZONE_RESTRICTED, None),      # the mask's own denial must not feed the score
    ("deny", "INTEGRITY_EVALUATOR_ERROR", None),
    ("deny", "INTEGRITY_NO_PACK", None),
    ("deny", "INTEGRITY_MALFORMED_DECISION", None),
    ("something_else", "OK", None),
])
def test_classify_receipt(decision, reason, expected):
    assert classify_receipt(receipt(decision, reason)) == expected


# --------------------------------------------------------------------------- scoring ---

def test_cold_start_is_unknown_never_red():
    s = settings()
    result, carried = score_window([VIOLATION] * 9, did_tier=3, settings=s)
    assert result.zone == UNKNOWN_ZONE and result.ais is None and carried is None
    assert result.observations == 9 and result.violations == 9


def test_score_is_compliance_capped_by_tier():
    s = settings()
    clean, _ = score_window([CLEAN] * 50, did_tier=3, settings=s)
    assert clean.ais == pytest.approx(1000.0) and clean.zone == "green"
    assert clean.profile == LOCAL_RECEIPT_PROFILE
    capped, _ = score_window([CLEAN] * 50, did_tier=1, settings=s)
    assert capped.ais == pytest.approx(600.0) and capped.zone == "green"  # per-tier policy: tier 1 green at 540


@pytest.mark.parametrize("violations,zone", [(0, "green"), (5, "green"), (6, "yellow"), (12, "yellow"), (13, "red")])
def test_zone_bands_at_tier_3(violations, zone):
    # S_C = 1000 * (1 - v/50): 5 -> 900 (green), 6 -> 880, 12 -> 760 (yellow), 13 -> 740 (red, < 750)
    result, _ = score_window([VIOLATION] * violations + [CLEAN] * (50 - violations), did_tier=3, settings=settings())
    assert result.zone == zone


def test_zone_mask_denials_do_not_lock_an_agent_in_red():
    scorer = LocalReceiptScorer(settings())
    scorer.observe_all([receipt("deny", "PACK_RULE")] * 20)
    scorer.observe_all([receipt("permit")] * 10)
    assert scorer.score(AGENT).zone == "red"
    # A red agent keeps trying to execute: the mask denies every attempt. None of it may count.
    counted = scorer.observe_all([receipt("deny", REASON_ZONE_RESTRICTED)] * 500)
    assert counted == 0
    assert scorer.score(AGENT).violations == 20


def test_red_agent_recovers_through_permitted_actions_with_hysteresis():
    scorer = LocalReceiptScorer(settings())
    scorer.observe_all([receipt("deny", "PACK_RULE")] * 20 + [receipt("permit")] * 10)
    assert scorer.score(AGENT).zone == "red"
    # Clean reads push the violations out of the window one by one.
    history = []
    for _ in range(50):
        scorer.observe(receipt("permit"))
        result = scorer.score(AGENT)
        history.append((result.zone, result.violations))
    zones = [z for z, _ in history]
    assert zones[-1] == "green"
    assert "yellow" in zones  # it passes through yellow; it does not jump red -> green
    assert zones.index("green") > zones.index("yellow")
    # Hysteresis: from yellow, green needs `recovery` (920 at tier 3) = at most 4 violations in 50.
    # Without hysteresis it would turn green at 900 = 5 violations.
    _, violations_at_first_green = history[zones.index("green")]
    assert violations_at_first_green == 4
    assert ("yellow", 5) in history


def test_window_size_bounds_memory_of_old_violations():
    scorer = LocalReceiptScorer(settings(window_size=20, min_observations=5))
    scorer.observe_all([receipt("deny", "R")] * 20 + [receipt("permit")] * 20)
    result = scorer.score(AGENT)
    assert result.observations == 20 and result.violations == 0


def test_max_age_drops_stale_and_undated_decisions():
    now = 1_762_905_600.0  # 2025-11-12T00:00:00Z
    scorer = LocalReceiptScorer(settings(max_age_seconds=3600, min_observations=1), clock=lambda: now)
    scorer.observe(receipt("deny", "R", timestamp="2025-11-11T00:00:00Z"))   # a day old
    scorer.observe({**receipt("deny", "R"), "timestamp": None})               # undated
    scorer.observe(receipt("permit", timestamp="2025-11-11T23:30:00Z"))      # 30 minutes old
    result = scorer.score(AGENT)
    assert (result.observations, result.violations) == (1, 0)


def test_agents_are_scored_independently_and_tiers_come_from_settings():
    scorer = LocalReceiptScorer(settings(default_tier=0, agent_tiers={"b": 3}, min_observations=1))
    scorer.observe_all([receipt("permit", agent="a"), receipt("permit", agent="b"), receipt("deny", "R", agent="b")])
    a, b = scorer.score("a"), scorer.score("b")
    assert (a.did_tier, a.ais) == (0, pytest.approx(300.0))
    assert (b.did_tier, b.violations) == (3, 1)
    assert scorer.score("never-seen").zone == UNKNOWN_ZONE


def test_zone_policy_is_honoured():
    absolute = ZonePolicy(mode=ZONE_POLICY_ABSOLUTE, absolute=ZoneThresholds(750.0, 900.0, 920.0))
    result, _ = score_window([CLEAN] * 50, did_tier=1, settings=settings(zone_policy=absolute))
    assert result.zone == "red"  # tier 1 is capped at 600, below an absolute 750: why per_tier is the default


@pytest.mark.parametrize("bad", [
    dict(window_size=0), dict(window_size=True), dict(min_observations=0), dict(min_observations=51),
    dict(max_age_seconds=0), dict(default_tier=4), dict(agent_tiers={"x": -1}), dict(default_tier=True),
])
def test_settings_are_validated(bad):
    with pytest.raises(ValueError):
        settings(**bad)


# --------------------------------------------------------------------------- tailing ---

def _append(path, rows, *, newline=True):
    with open(path, "ab") as handle:
        text = "\n".join(json.dumps(r) for r in rows)
        handle.write((text + ("\n" if newline else "")).encode())


def test_tail_reads_only_complete_new_lines(tmp_path):
    path = tmp_path / "receipts.jsonl"
    tail = ReceiptLogTail(path)
    assert tail.read_new() == ([], False)
    _append(path, [receipt("permit")] * 2)
    _append(path, [receipt("deny", "R")], newline=False)  # write in progress
    rows, reset = tail.read_new()
    assert [r["decision"] for r in rows] == ["permit", "permit"] and not reset
    with open(path, "ab") as handle:
        handle.write(b"\n")
    rows, _ = tail.read_new()
    assert [r["decision"] for r in rows] == ["deny"]
    assert tail.read_new() == ([], False)


def test_tail_skips_garbage_and_restarts_on_truncation_or_replacement(tmp_path):
    path = tmp_path / "receipts.jsonl"
    _append(path, [receipt("permit")])
    with open(path, "ab") as handle:
        handle.write(b"not json\n[1,2]\n")
    tail = ReceiptLogTail(path)
    rows, _ = tail.read_new()
    assert len(rows) == 1
    replacement = tmp_path / "new.jsonl"
    _append(replacement, [receipt("deny", "R")])
    os.replace(replacement, path)
    rows, reset = tail.read_new()
    assert reset and [r["decision"] for r in rows] == ["deny"]


def test_zone_source_follows_the_log(tmp_path):
    path = tmp_path / "receipts.jsonl"
    source = ReceiptLogZoneSource(path, settings(min_observations=5))
    assert source(AGENT).zone == UNKNOWN_ZONE
    _append(path, [receipt("permit")] * 50)
    assert source(AGENT).zone == "green"
    _append(path, [receipt("deny", "R")] * 13)
    assert source(AGENT).zone == "red"
    # Rewriting the log (shorter) rebuilds the state rather than double counting.
    path.write_text("")
    _append(path, [receipt("permit")] * 5)
    result = source(AGENT)
    assert (result.observations, result.violations, result.zone) == (5, 0, "green")
