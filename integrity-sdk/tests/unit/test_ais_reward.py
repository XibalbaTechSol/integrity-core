"""Unit tests for canonical AIS (`ais/v1-geometric-1`), ClosedLoopAISController,
and the LEGACY additive reward profile (`ais-reward/v1-additive-1`). The canonical
multiplicative profile is covered by test_ais_reward_multiplicative.py.
"""

from __future__ import annotations

import math
import pytest

from integrity_sdk.core import (
    AIS_FORMULA_VERSION,
    AISComponents,
    AISControlZone,
    AISInputs,
    AISRewardFunction,
    REWARD_PROFILE_ADDITIVE_V1,
    ClosedLoopAISController,
    compute_compliance_score,
    compute_contribution_score,
    compute_entropy_score,
    compute_grounding_score,
    compute_zk_boost,
    evaluate_ais_v1_geometric,
)


def test_transfer_functions_codomain_and_boundary_behavior():
    # Entropy S_E(v) = 1000 * exp(-1.5 * v^2)
    assert compute_entropy_score(0.0) == pytest.approx(1000.0)
    assert compute_entropy_score(1.0) == pytest.approx(1000.0 * math.exp(-1.5))
    assert compute_entropy_score(-0.1) == 0.0
    assert compute_entropy_score(float("nan")) == 0.0
    assert compute_entropy_score(float("inf")) == 0.0

    # Grounding S_G(h) = 1000 * clamp(h, 0, 1)
    assert compute_grounding_score(0.0) == 0.0
    assert compute_grounding_score(0.85) == pytest.approx(850.0)
    assert compute_grounding_score(1.5) == 1000.0
    assert compute_grounding_score(-0.5) == 0.0
    assert compute_grounding_score(float("nan")) == 0.0
    assert compute_grounding_score(float("-inf")) == 0.0
    assert compute_grounding_score(float("inf")) == 1000.0

    # Contribution S_S(g) = 1000 * min(log10(g + 1) / 3, 1)
    assert compute_contribution_score(0.0) == 0.0
    assert compute_contribution_score(9.0) == pytest.approx(1000.0 / 3.0)
    assert compute_contribution_score(999.0) == pytest.approx(1000.0)
    assert compute_contribution_score(10000.0) == 1000.0
    assert compute_contribution_score(-1.0) == 0.0
    assert compute_contribution_score(float("nan")) == 0.0
    assert compute_contribution_score(float("inf")) == 1000.0

    # Compliance S_C(p) = 1000 * (1 - clamp(p, 0, 1))
    assert compute_compliance_score(0.0) == 1000.0
    assert compute_compliance_score(0.25) == pytest.approx(750.0)
    assert compute_compliance_score(1.0) == 0.0
    assert compute_compliance_score(2.0) == 0.0
    assert compute_compliance_score(float("nan")) == 0.0
    assert compute_compliance_score(float("inf")) == 0.0

    # ZK boost
    assert compute_zk_boost(0.0) == 1.0
    assert compute_zk_boost(1.0) == pytest.approx(1.15)
    assert compute_zk_boost(float("nan")) == 1.0


def test_ais_v1_geometric_perfect_and_tier_ceilings():
    perfect = evaluate_ais_v1_geometric(
        AISInputs(
            entropy_variance=0.0,
            grounding_ratio=1.0,
            graph_contribution=999.0,
            penalty_severity=0.0,
            zk_coverage_ratio=1.0,
            did_tier=3,
        )
    )
    assert perfect.formula_version == AIS_FORMULA_VERSION
    assert perfect.ais_base == pytest.approx(1000.0)
    assert perfect.ais_final == pytest.approx(1000.0)
    assert perfect.ais_int == 1000
    assert perfect.zero_annihilated is False

    # DID Tier ceilings: 0->300, 1->600, 2->850, 3->1000
    for tier, expected_cap in [(0, 300.0), (1, 600.0), (2, 850.0), (3, 1000.0)]:
        res = evaluate_ais_v1_geometric(
            AISInputs(
                entropy_variance=0.0,
                grounding_ratio=1.0,
                graph_contribution=999.0,
                penalty_severity=0.0,
                did_tier=tier,
            )
        )
        assert res.ais_final == pytest.approx(expected_cap)


def test_ais_zero_annihilation_property():
    # Even if 3 axes are 1000, a critical compliance failure (p=1.0 -> S_C=0) annihilates AIS to 0
    annihilated = evaluate_ais_v1_geometric(
        AISInputs(
            entropy_variance=0.0,
            grounding_ratio=1.0,
            graph_contribution=999.0,
            penalty_severity=1.0,
            zk_coverage_ratio=1.0,
            did_tier=3,
        )
    )
    assert annihilated.s_compliance == 0.0
    assert annihilated.zero_annihilated is True
    assert annihilated.ais_base == 0.0
    assert annihilated.ais_final == 0.0
    assert annihilated.ais_int == 0


def test_closed_loop_controller_zones_hysteresis_and_interlocks():
    controller = ClosedLoopAISController(
        green_threshold=900.0,
        yellow_threshold=750.0,
        recovery_threshold=920.0,
    )
    assert controller.current_zone == AISControlZone.GREEN

    # Step 1: Degrade into YELLOW (~890 AIS without ZK boost)
    state_yellow = controller.step(
        AISInputs(
            entropy_variance=0.2,
            grounding_ratio=0.90,
            graph_contribution=200.0,
            penalty_severity=0.10,
            zk_coverage_ratio=0.0,
        )
    )
    assert 750.0 <= state_yellow.ais_components.ais_final < 900.0
    assert state_yellow.zone == AISControlZone.YELLOW
    assert "execute" not in state_yellow.allowed_actions
    assert "draft" in state_yellow.allowed_actions

    # Step 2: Score rises to ~910 (above 900 GREEN threshold, but below 920 hysteresis recovery)
    state_hysteresis = controller.step(
        AISInputs(
            entropy_variance=0.0,
            grounding_ratio=0.95,
            graph_contribution=999.0,
            penalty_severity=0.0,
            zk_coverage_ratio=0.0,
            weights=(0.0, 1.0, 0.0, 0.0),  # S_G = 950 -> let's test 910 with grounding_ratio=0.91
        )
    )
    # Wait: grounding_ratio=0.95 gives 950 >= 920. Let's test 0.91 (910 < 920):
    controller_hyst = ClosedLoopAISController()
    controller_hyst.step(
        AISInputs(0.0, 0.80, 999.0, 0.0, weights=(0.0, 1.0, 0.0, 0.0))
    )
    assert controller_hyst.current_zone == AISControlZone.YELLOW

    hold_yellow = controller_hyst.step(
        AISInputs(0.0, 0.91, 999.0, 0.0, weights=(0.0, 1.0, 0.0, 0.0))
    )
    assert hold_yellow.ais_components.ais_final == pytest.approx(910.0)
    assert hold_yellow.zone == AISControlZone.YELLOW  # Held in YELLOW due to hysteresis < 920

    recover_green = controller_hyst.step(
        AISInputs(0.0, 0.93, 999.0, 0.0, weights=(0.0, 1.0, 0.0, 0.0))
    )
    assert recover_green.ais_components.ais_final == pytest.approx(930.0)
    assert recover_green.zone == AISControlZone.GREEN  # Recovered (>= 920)

    # Step 3: Hard interlock forces RED even when AIS is 1000
    interlock_red = controller_hyst.step(
        AISInputs(0.0, 1.0, 999.0, 0.0),
        hard_interlocks={"boundary_violation": True},
    )
    assert interlock_red.ais_components.ais_final == pytest.approx(1000.0)
    assert interlock_red.zone == AISControlZone.RED
    assert interlock_red.interlock_tripped is True
    assert interlock_red.active_interlocks == ("boundary_violation",)
    assert interlock_red.allowed_actions == {"escalate"}


def test_legacy_additive_reward_profile_and_onchain_settlement():
    reward_fn = AISRewardFunction(
        profile=REWARD_PROFILE_ADDITIVE_V1,
        lambda_ais=0.50,
        gamma=0.99,
        shaping_weight=0.25,
        deny_penalty=1.0,
        gate_task_on_compliance=True,
        ais_min=750.0,
        convex_beta=2.0,
    )

    # 1. Compliant high-AIS step reward: R_total = R_task + lambda * (AIS/1000) + shaping
    high_ais = evaluate_ais_v1_geometric(
        AISInputs(0.0, 1.0, 999.0, 0.0, zk_coverage_ratio=1.0, did_tier=3)
    )
    step_good = reward_fn.compute_step_reward(
        r_task=1.0,
        ais_t=high_ais,
        ais_prev=900.0,
        deny_count=0,
    )
    assert step_good.gated_by_compliance is False
    assert step_good.r_task == pytest.approx(1.0)
    assert step_good.ais_term == pytest.approx(0.50)
    assert step_good.potential_shaping > 0.0
    assert step_good.r_total > 1.50

    # 2. Anti-reward-hacking proof: if agent completes task (r_task=1.0) by violating policy
    # (penalty_severity=1.0 or deny_count=1), task reward is gated to 0 and R_total is strictly negative
    violating_ais = evaluate_ais_v1_geometric(
        AISInputs(0.0, 1.0, 999.0, 1.0, zk_coverage_ratio=1.0, did_tier=3)
    )
    step_bad = reward_fn.compute_step_reward(
        r_task=1.0,
        ais_t=violating_ais,
        ais_prev=1000.0,
        deny_count=1,
    )
    assert step_bad.gated_by_compliance is True
    assert step_bad.r_task == 0.0
    assert step_bad.ais_term == 0.0
    assert step_bad.r_total < -1.0
    assert step_good.r_total > step_bad.r_total

    # 3. On-chain epoch settlement validation:
    # - Below AIS_min (750): 0 payout
    epoch_low = reward_fn.settle_epoch(base_fee_pool=1000.0, ais_epoch=700.0, stake_amount=500.0)
    assert epoch_low.payout == 0.0
    assert epoch_low.slashed is False

    # - Mid-high AIS (875 -> halfway between 750 and 1000 -> multiplier = 0.5^2 = 0.25)
    epoch_mid = reward_fn.settle_epoch(base_fee_pool=1000.0, ais_epoch=875.0, stake_amount=500.0)
    assert epoch_mid.multiplier == pytest.approx(0.25)
    assert epoch_mid.payout == pytest.approx(250.0)

    # - Perfect AIS (1000 -> multiplier = 1.0 -> full pool)
    epoch_max = reward_fn.settle_epoch(base_fee_pool=1000.0, ais_epoch=1000.0, stake_amount=500.0)
    assert epoch_max.multiplier == pytest.approx(1.0)
    assert epoch_max.payout == pytest.approx(1000.0)

    # - Fraud proof verified -> AIS slashed to 0, payout 0, stake slashed
    epoch_slashed = reward_fn.settle_epoch(
        base_fee_pool=1000.0,
        ais_epoch=980.0,
        stake_amount=500.0,
        fraud_proof_verified=True,
        slash_fraction=0.50,
    )
    assert epoch_slashed.slashed is True
    assert epoch_slashed.payout == 0.0
    assert epoch_slashed.slash_amount == pytest.approx(250.0)
