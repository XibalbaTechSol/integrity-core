"""The AIS control zone is judged against what an agent's verification tier can reach.

AIS is capped by tier (300 / 600 / 850 / 1000). Under one absolute threshold set (750 / 900 /
920) a tier 0 or tier 1 agent is red whatever it does, so the zone carried no information for
them. `ZonePolicy` makes the rule a setting: `per_tier` (default), `relative`, or `absolute`.

The vectors in spec/ais-api/v1/zone-vectors.json are shared with the Rust scorer; their
expected zones were derived by hand from the thresholds, not from either implementation.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from integrity_sdk.core import (
    TIER_CEILINGS,
    ZONE_POLICY_ABSOLUTE,
    ZONE_POLICY_MODES,
    ZONE_POLICY_PER_TIER,
    ZONE_POLICY_RELATIVE,
    AISControlZone,
    AISInputs,
    ClosedLoopAISController,
    ZonePolicy,
    ZoneThresholds,
    evaluate_control_zone,
)

VECTORS = json.loads((Path(__file__).resolve().parents[3] / "spec/ais-api/v1/zone-vectors.json").read_text())


def _policy(name: str, mode: str) -> ZonePolicy:
    return ZonePolicy.from_mapping({**VECTORS["policies"][name], "mode": mode})


def test_the_default_policy_matches_the_shared_vector_file():
    default = ZonePolicy()
    assert default.mode == VECTORS["default_mode"] == ZONE_POLICY_PER_TIER
    assert default == _policy("default", ZONE_POLICY_PER_TIER)
    assert default.to_dict() == VECTORS["policies"]["default"]
    assert [TIER_CEILINGS[tier] for tier in range(4)] == VECTORS["tier_ceilings"]
    assert set(ZONE_POLICY_MODES) == {ZONE_POLICY_PER_TIER, ZONE_POLICY_RELATIVE, ZONE_POLICY_ABSOLUTE}


def test_the_vector_file_still_has_its_cases():
    assert len(VECTORS["zone_vectors"]) >= 40
    assert {case["mode"] for case in VECTORS["zone_vectors"]} == set(ZONE_POLICY_MODES)


@pytest.mark.parametrize("case", VECTORS["zone_vectors"], ids=lambda case: case["name"])
def test_control_zone_matches_shared_golden_vectors(case):
    prev = AISControlZone(case["prev_zone"]) if case["prev_zone"] else None
    got = evaluate_control_zone(
        case["score"], did_tier=case["tier"], prev_zone=prev, interlock_tripped=case["interlock"],
        policy=_policy(case["policy"], case["mode"]),
    )
    assert got.value == case["expected"]


def test_every_tier_can_reach_green_under_the_default_policy_and_not_under_absolute():
    """The reason the policy exists."""
    for tier, ceiling in TIER_CEILINGS.items():
        assert evaluate_control_zone(ceiling, did_tier=tier) is AISControlZone.GREEN
        assert evaluate_control_zone(
            ceiling, did_tier=tier, policy=ZonePolicy(mode=ZONE_POLICY_RELATIVE)) is AISControlZone.GREEN
    absolute = ZonePolicy(mode=ZONE_POLICY_ABSOLUTE)
    assert evaluate_control_zone(TIER_CEILINGS[0], did_tier=0, policy=absolute) is AISControlZone.RED
    assert evaluate_control_zone(TIER_CEILINGS[1], did_tier=1, policy=absolute) is AISControlZone.RED
    assert evaluate_control_zone(TIER_CEILINGS[2], did_tier=2, policy=absolute) is AISControlZone.YELLOW


@pytest.mark.parametrize("score", [math.nan, math.inf, -math.inf])
def test_a_score_that_is_not_finite_is_red(score):
    assert evaluate_control_zone(score, did_tier=3) is AISControlZone.RED


@pytest.mark.parametrize("document", [
    {"mode": "strict"},
    {"surprise": 1},
    {"absolute": [900, 750, 920]},                      # inverted
    {"absolute": [750, 900]},                           # wrong length
    {"absolute": [750, 900, 1001]},                     # above the scale
    {"relative": [0.75, 0.9, 1.01]},                    # a fraction above 1
    {"relative": {"yellow": 0.75, "green": 0.9}},       # a missing key
    {"per_tier": [[225, 270, 276]]},                    # not one row per tier
    {"per_tier": [[225, 301, 301], [450, 540, 552], [637.5, 765, 782], [750, 900, 920]]},  # above tier 0's ceiling
    {"per_tier": [[225, 270, math.nan], [450, 540, 552], [637.5, 765, 782], [750, 900, 920]]},
    {"per_tier": [[True, 270, 276], [450, 540, 552], [637.5, 765, 782], [750, 900, 920]]},
    {"per_tier": {"0": [225, 270, 276]}},
    {"per_tier": "225,270,276"},
])
def test_a_policy_that_cannot_work_is_refused(document):
    with pytest.raises(ValueError):
        ZonePolicy.from_mapping(document)


def test_a_bad_table_is_refused_even_when_another_mode_is_selected():
    """Otherwise switching the mode later would reveal a threshold nobody can reach."""
    with pytest.raises(ValueError, match="per_tier tier 0"):
        ZonePolicy.from_mapping({
            "mode": "relative",
            "per_tier": [[225, 400, 400], [450, 540, 552], [637.5, 765, 782], [750, 900, 920]],
        })


def test_per_tier_accepts_an_object_keyed_by_tier_and_named_thresholds():
    policy = ZonePolicy.from_mapping({"per_tier": {
        "0": {"yellow": 100, "green": 200, "recovery": 250}, "1": [300, 400, 500],
        "2": [637.5, 765, 782], "3": [750, 900, 920],
    }})
    assert policy.thresholds_for_tier(0) == ZoneThresholds(100, 200, 250)
    assert policy.thresholds_for_tier(1).green == 400


def _inputs(tier: int, penalty: float = 0.0) -> AISInputs:
    # Near-perfect axes, so the score is the tier ceiling unless `penalty` lowers it.
    return AISInputs(entropy_variance=0.0, grounding_ratio=1.0, graph_contribution=999.0,
                     penalty_severity=penalty, did_tier=tier)


def test_the_controller_uses_the_agents_tier_by_default():
    for tier in range(4):
        controller = ClosedLoopAISController()
        assert controller.zone_policy.mode == ZONE_POLICY_PER_TIER
        assert controller.step(_inputs(tier)).zone is AISControlZone.GREEN


def test_explicit_thresholds_still_mean_one_absolute_set_for_every_tier():
    controller = ClosedLoopAISController(green_threshold=900.0, yellow_threshold=750.0, recovery_threshold=920.0)
    assert controller.zone_policy.mode == ZONE_POLICY_ABSOLUTE
    assert controller.step(_inputs(1)).zone is AISControlZone.RED
    assert (controller.yellow_threshold, controller.green_threshold, controller.recovery_threshold) == (750, 900, 920)
    with pytest.raises(ValueError, match="either"):
        ClosedLoopAISController(green_threshold=900.0, zone_policy=ZonePolicy())
    with pytest.raises(ValueError):
        ClosedLoopAISController(green_threshold=700.0, yellow_threshold=750.0)


def test_the_controller_applies_hysteresis_on_the_tiers_own_scale():
    controller = ClosedLoopAISController()
    # A 99% penalty leaves about 398 uncapped, under tier 1's yellow threshold of 450.
    degraded = controller.step(_inputs(1, penalty=0.99))
    assert degraded.zone is AISControlZone.RED and 390 < degraded.ais_components.ais_final < 410
    # 600 is tier 1's ceiling and above its recovery threshold (552): back to green.
    assert controller.step(_inputs(1)).zone is AISControlZone.GREEN


def test_the_tier_ceiling_hides_degradation_that_stays_above_it():
    """A known property, pinned so it is not mistaken for a bug in the zone rule: AIS is clipped to
    the tier ceiling before the zone is read, so a low-tier agent stays green until its uncapped
    score falls under that tier's green threshold. Here a 90% penalty leaves about 631 uncapped,
    which is still clipped to tier 1's ceiling of 600."""
    state = ClosedLoopAISController().step(_inputs(1, penalty=0.9))
    assert state.ais_components.ais_final == 600.0 and state.zone is AISControlZone.GREEN
    # The same behaviour at tier 3 is visible: 631 is red there.
    assert ClosedLoopAISController().step(_inputs(3, penalty=0.9)).zone is AISControlZone.RED


def test_an_interlock_is_red_for_every_tier():
    for tier in range(4):
        state = ClosedLoopAISController().step(_inputs(tier), hard_interlocks={"phi_boundary": True})
        assert state.zone is AISControlZone.RED
