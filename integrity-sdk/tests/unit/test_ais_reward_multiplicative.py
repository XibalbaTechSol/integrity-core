"""The canonical AIS reward is multiplicative: `R = max(0, R_task - cost) * AIS`.

Why not additive (`R_task + lambda * AIS`): AIS contributes at most `lambda`, so any
path whose task reward leads by more than that wins no matter how low its integrity.
Scaling the whole payoff by AIS removes that: a low-integrity path keeps only a
fraction of whatever it earned.

The vectors in spec/ais-api/v1/reward-vectors.json are shared with the Rust scorer
and with xibalba-cortex; their expected values were computed independently of all
three implementations.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from integrity_sdk.core import (
    DEFAULT_AXIS_WEIGHTS,
    DEFAULT_REWARD_PROFILE,
    REWARD_PROFILE_ADDITIVE_V1,
    REWARD_PROFILE_MULTIPLICATIVE,
    AISInputs,
    AISRewardFunction,
    evaluate_ais_v1_geometric,
    multiplicative_reward,
)

VECTORS = json.loads((Path(__file__).resolve().parents[3] / "spec/ais-api/v1/reward-vectors.json").read_text())
TOL = 1e-9


def test_profile_names_match_the_shared_vector_file():
    assert REWARD_PROFILE_MULTIPLICATIVE == VECTORS["reward_profile"]
    assert REWARD_PROFILE_ADDITIVE_V1 == VECTORS["legacy_reward_profile"]
    assert DEFAULT_REWARD_PROFILE == REWARD_PROFILE_MULTIPLICATIVE


def test_default_axis_weights_match_the_rust_scorer():
    w = VECTORS["ais_weights"]
    assert DEFAULT_AXIS_WEIGHTS == (w["entropy"], w["grounding"], w["sacrifice"], w["compliance"])


@pytest.mark.parametrize("vec", VECTORS["ais_vectors"])
def test_ais_matches_shared_golden_vectors(vec):
    got = evaluate_ais_v1_geometric(
        AISInputs(
            entropy_variance=vec["performance_variance"],
            grounding_ratio=vec["grounding_ratio"],
            graph_contribution=vec["contribution"],
            penalty_severity=vec["penalty_ratio"],
            zk_coverage_ratio=vec["zk_coverage_ratio"],
            did_tier=vec["did_tier"],
        )
    )
    assert got.ais_final == pytest.approx(vec["expected_ais"], abs=TOL)


@pytest.mark.parametrize("vec", VECTORS["reward_vectors"], ids=lambda v: v["name"])
def test_multiplicative_reward_matches_shared_golden_vectors(vec):
    got = multiplicative_reward(vec["r_task"], vec["ais"], cost_penalty=vec["cost_penalty"], gated=vec["gated"])
    assert got == pytest.approx(vec["expected_r_total"], abs=TOL)


def test_reward_is_never_negative_and_is_monotonic_in_ais():
    for r_task in (-3.0, 0.0, 0.4, 7.0):
        previous = -math.inf
        for ais in range(0, 1001, 50):
            r = multiplicative_reward(r_task, float(ais))
            assert r >= 0.0
            assert r >= previous
            previous = r


def test_zero_or_non_finite_ais_zeroes_any_reward():
    for ais in (0.0, -5.0, math.nan, -math.inf):
        assert multiplicative_reward(1e9, ais) == 0.0


def test_integrity_cannot_be_swamped_by_task_reward():
    """The case the two profiles disagree on. This is the reason for the change."""
    a, b = VECTORS["ordering_vector"]["a"], VECTORS["ordering_vector"]["b"]

    canonical = AISRewardFunction()
    ra = canonical.compute_step_reward(r_task=a["r_task"], ais_t=a["ais"]).r_total
    rb = canonical.compute_step_reward(r_task=b["r_task"], ais_t=b["ais"]).r_total
    assert ra == pytest.approx(a["v2"], abs=TOL)
    assert rb == pytest.approx(b["v2"], abs=TOL)
    assert rb > ra, "high-integrity path must beat the higher-task-reward, low-integrity path"

    legacy = AISRewardFunction(profile=REWARD_PROFILE_ADDITIVE_V1)
    la = legacy.compute_step_reward(r_task=a["r_task"], ais_t=a["ais"]).r_total
    lb = legacy.compute_step_reward(r_task=b["r_task"], ais_t=b["ais"]).r_total
    assert la == pytest.approx(a["v1"], abs=TOL)
    assert lb == pytest.approx(b["v1"], abs=TOL)
    assert la > lb, "the legacy additive profile is expected to get this case wrong"


def test_default_step_reward_reports_its_profile_and_has_no_additive_terms():
    step = AISRewardFunction().compute_step_reward(r_task=2.0, ais_t=800.0, ais_prev=200.0)
    assert step.reward_profile == REWARD_PROFILE_MULTIPLICATIVE
    assert step.ais_term == 0.0
    assert step.potential_shaping == 0.0
    assert step.violation_penalty == 0.0
    assert step.r_total == pytest.approx(1.6, abs=TOL)
    assert step.to_dict()["reward_profile"] == REWARD_PROFILE_MULTIPLICATIVE


def test_denied_or_non_compliant_step_earns_exactly_zero():
    fn = AISRewardFunction()
    denied = fn.compute_step_reward(r_task=5.0, ais_t=950.0, deny_count=1)
    assert denied.gated_by_compliance is True
    assert denied.r_total == 0.0

    violating = evaluate_ais_v1_geometric(AISInputs(0.0, 1.0, 999.0, 1.0))
    assert fn.compute_step_reward(r_task=5.0, ais_t=violating).r_total == 0.0


def test_unknown_profile_is_rejected():
    with pytest.raises(ValueError):
        AISRewardFunction(profile="ais-reward/made-up")
