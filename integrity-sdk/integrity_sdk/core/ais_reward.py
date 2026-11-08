"""Canonical AIS Mathematical Engine (`ais/v1-geometric-1`), Closed-Loop Controller,
and Reward Function (`R_total = R_task + lambda * AIS`).

Strictly domain-agnostic (`integrity_sdk.core` contract): depends only on the
Python standard library (`math`, `dataclasses`, `enum`, `typing`).

Implements:
1. `evaluate_ais_v1_geometric` (docs/design/ais-mathematical-spec-v1.md):
   - Four normalized axes in `[0, 1000]`:
     * `S_E(v) = 1000 * exp(-1.5 * v^2)` for `v >= 0` (Entropy / Stability)
     * `S_G(h) = 1000 * clamp(h, 0, 1)` (Grounding / Verification)
     * `S_S(g) = 1000 * min(log10(g + 1) / 3, 1)` for `g >= 0` (Contribution)
     * `S_C(p) = 1000 * (1 - clamp(p, 0, 1))` (Compliance / Penalty complement)
   - Log-domain weighted geometric mean with all-zero annihilation if any
     positive-weight axis is `0`.
   - `ZK_boost(rho) = 1 + 0.15 * clamp(rho, 0, 1)` capped by DID tier ceiling
     (`0: 300, 1: 600, 2: 850, 3: 1000`).
2. `ClosedLoopAISController`:
   - Feedback state machine (`GREEN`, `YELLOW`, `RED`) with hysteresis recovery
     (`tau_recover = 920.0`) and external constraint interlocks (`c_j(x_t) <= 0`).
3. `AISRewardFunction`:
   - Step-level off-chain RL / GRPO / DPO reward:
     `R_total(t) = R_task(t) + lambda_ais * (AIS_t / 1000) + (gamma * Phi(AIS_t) - Phi(AIS_{t-1})) - penalty`
   - On-chain epoch settlement and slashing multiplier (`Y_e`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Dict, Iterable, Mapping, Optional, Sequence, Set, Tuple

AIS_FORMULA_VERSION = "ais/v1-geometric-1"

DEFAULT_AXIS_WEIGHTS: Tuple[float, float, float, float] = (0.30, 0.25, 0.15, 0.30)

TIER_CEILINGS: Mapping[int, float] = {
    0: 300.0,
    1: 600.0,
    2: 850.0,
    3: 1000.0,
}

WEIGHT_SUM_TOLERANCE = 1e-9


class AISControlZone(str, Enum):
    """Closed-loop control zones governed by AIS."""

    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


@dataclass(frozen=True)
class AISInputs:
    """Raw inputs to the `ais/v1-geometric-1` transfer functions.

    Attributes:
        entropy_variance: `v` in `[0, +inf)` (normalized routing/latency/entropy variance).
        grounding_ratio: `h` in `[0, 1]` (fraction of claims backed by verified evidence).
        graph_contribution: `g` in `[0, +inf)` (verified structural contribution units).
        penalty_severity: `p` in `[0, 1]` (cumulative active policy violation severity).
        zk_coverage_ratio: `rho` in `[0, 1]` (fraction of high-risk steps with ZK/TEE proof).
        did_tier: DID verification tier (`0`, `1`, `2`, or `3`).
        weights: Tuple `(w_E, w_G, w_S, w_C)` summing to `1.0`.
    """

    entropy_variance: float
    grounding_ratio: float
    graph_contribution: float
    penalty_severity: float
    zk_coverage_ratio: float = 0.0
    did_tier: int = 3
    weights: Tuple[float, float, float, float] = DEFAULT_AXIS_WEIGHTS


@dataclass(frozen=True)
class AISComponents:
    """Deterministic evaluation result of `ais/v1-geometric-1`."""

    s_entropy: float
    s_grounding: float
    s_contribution: float
    s_compliance: float
    ais_base: float
    zk_boost: float
    tier_ceiling: float
    ais_final: float
    ais_int: int
    zero_annihilated: bool
    formula_version: str = AIS_FORMULA_VERSION

    @property
    def normalized(self) -> float:
        """Normalized AIS in `[0.0, 1.0]`."""
        return self.ais_final / 1000.0

    def to_dict(self) -> Dict[str, object]:
        return {
            "formula_version": self.formula_version,
            "s_entropy": round(self.s_entropy, 6),
            "s_grounding": round(self.s_grounding, 6),
            "s_contribution": round(self.s_contribution, 6),
            "s_compliance": round(self.s_compliance, 6),
            "ais_base": round(self.ais_base, 6),
            "zk_boost": round(self.zk_boost, 6),
            "tier_ceiling": round(self.tier_ceiling, 6),
            "ais_final": round(self.ais_final, 6),
            "ais_int": self.ais_int,
            "zero_annihilated": self.zero_annihilated,
        }


def _validate_weights(weights: Sequence[float]) -> Tuple[float, float, float, float]:
    if len(weights) != 4:
        raise ValueError(f"Expected 4 axis weights (w_E, w_G, w_S, w_C), got {len(weights)}")
    for w in weights:
        if math.isnan(w) or math.isinf(w) or w < 0.0 or w > 1.0:
            raise ValueError(f"Axis weight out of [0, 1]: {w}")
    total = math.fsum(weights)
    if abs(total - 1.0) > WEIGHT_SUM_TOLERANCE:
        raise ValueError(f"Axis weights must sum to 1.0 within {WEIGHT_SUM_TOLERANCE}, got {total}")
    return (float(weights[0]), float(weights[1]), float(weights[2]), float(weights[3]))


def compute_entropy_score(v: float, alpha: float = 1.5) -> float:
    """S_E(v) = 1000 * exp(-alpha * v^2) on [0, +inf). Fail closed to 0 on NaN, <0, or +inf."""
    if math.isnan(v) or v < 0.0 or math.isinf(v):
        return 0.0
    exponent = -alpha * (v * v)
    if exponent < -700.0:
        return 0.0
    return 1000.0 * math.exp(exponent)


def compute_grounding_score(h: float) -> float:
    """S_G(h) = 1000 * clamp(h, 0, 1). Fail closed to 0 on NaN or -inf; saturate to 1000 on +inf."""
    if math.isnan(h):
        return 0.0
    if math.isinf(h):
        return 1000.0 if h > 0 else 0.0
    clamped = min(max(h, 0.0), 1.0)
    return 1000.0 * clamped


def compute_contribution_score(g: float, g_max: float = 1000.0) -> float:
    """S_S(g) = 1000 * min(log10(g + 1) / log10(g_max), 1). Fail closed on NaN/<0; saturate on +inf."""
    if math.isnan(g) or g < 0.0:
        return 0.0
    if math.isinf(g):
        return 1000.0
    denom = math.log10(g_max)
    if denom <= 0.0:
        raise ValueError("g_max must be > 1.0")
    ratio = math.log10(g + 1.0) / denom
    return 1000.0 * min(max(ratio, 0.0), 1.0)


def compute_compliance_score(p: float) -> float:
    """S_C(p) = 1000 * (1 - clamp(p, 0, 1)). Fail closed to 0 on NaN, -inf, or +inf."""
    if math.isnan(p) or math.isinf(p):
        return 0.0
    clamped = min(max(p, 0.0), 1.0)
    return 1000.0 * (1.0 - clamped)


def compute_zk_boost(rho: float) -> float:
    """ZK_boost(rho) = 1.0 + 0.15 * clamp(rho, 0, 1). Fail closed to 1.0 on NaN or +/-inf."""
    if math.isnan(rho) or math.isinf(rho):
        return 1.0
    clamped = min(max(rho, 0.0), 1.0)
    return 1.0 + 0.15 * clamped


def evaluate_ais_v1_geometric(inputs: AISInputs) -> AISComponents:
    """Evaluate the canonical `ais/v1-geometric-1` specification."""
    weights = _validate_weights(inputs.weights)
    tier_ceiling = float(TIER_CEILINGS.get(inputs.did_tier, 0.0))

    s_e = compute_entropy_score(inputs.entropy_variance)
    s_g = compute_grounding_score(inputs.grounding_ratio)
    s_s = compute_contribution_score(inputs.graph_contribution)
    s_c = compute_compliance_score(inputs.penalty_severity)

    axes = (s_e, s_g, s_s, s_c)
    zero_annihilated = any(w > 0.0 and s <= 0.0 for w, s in zip(weights, axes))

    if zero_annihilated:
        ais_base = 0.0
    else:
        log_sum = math.fsum(w * math.log(s) for w, s in zip(weights, axes) if w > 0.0)
        ais_base = math.exp(log_sum)

    zk_boost = compute_zk_boost(inputs.zk_coverage_ratio)
    boosted = ais_base * zk_boost
    ais_final = min(boosted, tier_ceiling, 1000.0)
    if math.isnan(ais_final) or ais_final < 0.0:
        ais_final = 0.0

    return AISComponents(
        s_entropy=s_e,
        s_grounding=s_g,
        s_contribution=s_s,
        s_compliance=s_c,
        ais_base=ais_base,
        zk_boost=zk_boost,
        tier_ceiling=tier_ceiling,
        ais_final=ais_final,
        ais_int=int(round(ais_final)),
        zero_annihilated=zero_annihilated,
    )


@dataclass
class ClosedLoopState:
    """Snapshot of the closed-loop AIS controller state at step `t`."""

    step_index: int
    ais_components: AISComponents
    zone: AISControlZone
    allowed_actions: Set[str]
    interlock_tripped: bool
    active_interlocks: Tuple[str, ...] = ()


class ClosedLoopAISController:
    """Feedback control loop mapping `AIS_t` and hard interlocks to executable action sets.

    Enforces:
    - `GREEN` (`AIS >= 900.0`)
    - `YELLOW` (`750.0 <= AIS < 900.0`)
    - `RED` (`AIS < 750.0` or any hard interlock tripped)
    - Hysteresis recovery: once degraded into `YELLOW` or `RED`, recovering to
      `GREEN` requires `AIS >= recovery_threshold` (`920.0` by default) to
      prevent chatter around the `900.0` boundary.
    """

    def __init__(
        self,
        zone_permissions: Optional[Mapping[AISControlZone, Iterable[str]]] = None,
        green_threshold: float = 900.0,
        yellow_threshold: float = 750.0,
        recovery_threshold: float = 920.0,
        initial_ais: float = 1000.0,
    ) -> None:
        if not (0.0 <= yellow_threshold < green_threshold <= recovery_threshold <= 1000.0):
            raise ValueError("Thresholds must satisfy 0 <= yellow < green <= recovery <= 1000")
        self.green_threshold = green_threshold
        self.yellow_threshold = yellow_threshold
        self.recovery_threshold = recovery_threshold

        default_permissions: Dict[AISControlZone, Set[str]] = {
            AISControlZone.GREEN: {"read", "draft", "execute", "escalate"},
            AISControlZone.YELLOW: {"read", "draft", "escalate"},
            AISControlZone.RED: {"escalate"},
        }
        if zone_permissions is not None:
            self.zone_permissions = {
                zone: set(actions) for zone, actions in zone_permissions.items()
            }
        else:
            self.zone_permissions = default_permissions

        self._step_index = 0
        self._current_ais = min(max(initial_ais, 0.0), 1000.0)
        self._current_zone = self._initial_zone(self._current_ais)
        self._history: list[ClosedLoopState] = []

    def _initial_zone(self, ais_score: float) -> AISControlZone:
        if ais_score >= self.green_threshold:
            return AISControlZone.GREEN
        if ais_score >= self.yellow_threshold:
            return AISControlZone.YELLOW
        return AISControlZone.RED

    @property
    def current_ais(self) -> float:
        return self._current_ais

    @property
    def current_zone(self) -> AISControlZone:
        return self._current_zone

    @property
    def history(self) -> Tuple[ClosedLoopState, ...]:
        return tuple(self._history)

    def get_allowed_actions(self) -> Set[str]:
        return set(self.zone_permissions.get(self._current_zone, set()))

    def is_action_permitted(self, action_name: str) -> bool:
        return action_name in self.zone_permissions.get(self._current_zone, set())

    def step(
        self,
        inputs: AISInputs,
        hard_interlocks: Optional[Mapping[str, bool]] = None,
    ) -> ClosedLoopState:
        """Advance the closed-loop controller by one control tick."""
        self._step_index += 1
        components = evaluate_ais_v1_geometric(inputs)
        score = components.ais_final

        tripped_names = tuple(
            sorted(name for name, tripped in (hard_interlocks or {}).items() if tripped)
        )
        interlock_tripped = len(tripped_names) > 0

        if interlock_tripped or score < self.yellow_threshold:
            next_zone = AISControlZone.RED
        elif self._current_zone in (AISControlZone.YELLOW, AISControlZone.RED):
            # Hysteresis deadband: must reach recovery_threshold (920) to re-enter GREEN
            if score >= self.recovery_threshold:
                next_zone = AISControlZone.GREEN
            else:
                next_zone = AISControlZone.YELLOW
        else:
            if score >= self.green_threshold:
                next_zone = AISControlZone.GREEN
            else:
                next_zone = AISControlZone.YELLOW

        self._current_ais = score
        self._current_zone = next_zone

        state = ClosedLoopState(
            step_index=self._step_index,
            ais_components=components,
            zone=next_zone,
            allowed_actions=self.get_allowed_actions(),
            interlock_tripped=interlock_tripped,
            active_interlocks=tripped_names,
        )
        self._history.append(state)
        return state


@dataclass(frozen=True)
class StepRewardBreakdown:
    """Auditable breakdown of the off-chain & step-level AIS reward function."""

    r_task: float
    ais_t: float
    ais_prev: float
    ais_term: float
    potential_shaping: float
    violation_penalty: float
    r_total: float
    gated_by_compliance: bool

    def to_dict(self) -> Dict[str, object]:
        return {
            "r_task": round(self.r_task, 6),
            "ais_t": round(self.ais_t, 6),
            "ais_prev": round(self.ais_prev, 6),
            "ais_term": round(self.ais_term, 6),
            "potential_shaping": round(self.potential_shaping, 6),
            "violation_penalty": round(self.violation_penalty, 6),
            "r_total": round(self.r_total, 6),
            "gated_by_compliance": self.gated_by_compliance,
        }


@dataclass(frozen=True)
class EpochSettlementResult:
    """Deterministic on-chain epoch reward & slashing settlement."""

    base_fee_pool: float
    ais_epoch: float
    ais_min: float
    multiplier: float
    slashed: bool
    slash_amount: float
    payout: float

    def to_dict(self) -> Dict[str, object]:
        return {
            "base_fee_pool": round(self.base_fee_pool, 6),
            "ais_epoch": round(self.ais_epoch, 6),
            "ais_min": round(self.ais_min, 6),
            "multiplier": round(self.multiplier, 6),
            "slashed": self.slashed,
            "slash_amount": round(self.slash_amount, 6),
            "payout": round(self.payout, 6),
        }


class AISRewardFunction:
    """Deterministic AIS Reward Function for both off-chain RL/GRPO/DPO and on-chain settlement.

    Implements:
    1. Canonical linear-plus-shaping step reward:
       `R_total(t) = r_task_eff + lambda_ais * (AIS_t / 1000) + (gamma * Phi(AIS_t) - Phi(AIS_{t-1})) - penalty`
       where `Phi(AIS) = (AIS / 1000)^2` is a policy-invariant potential function
       (Ng et al., 1999) and `r_task_eff` is multiplicatively gated to `0` if
       `gate_task_on_compliance=True` and `S_C == 0` (preventing reward hacking via
       policy violations).
    2. On-chain epoch settlement (`settle_epoch`):
       Convex superlinear yield multiplier above `ais_min` (`750.0` by default) and
       deterministic slashing on verified fraud/violation proofs.
    """

    def __init__(
        self,
        lambda_ais: float = 0.50,
        gamma: float = 0.99,
        shaping_weight: float = 0.25,
        deny_penalty: float = 1.0,
        gate_task_on_compliance: bool = True,
        ais_min: float = 750.0,
        convex_beta: float = 2.0,
    ) -> None:
        if lambda_ais < 0.0:
            raise ValueError("lambda_ais must be non-negative")
        if not (0.0 <= gamma <= 1.0):
            raise ValueError("gamma must be in [0, 1]")
        if not (0.0 <= ais_min < 1000.0):
            raise ValueError("ais_min must be in [0, 1000)")
        if convex_beta < 1.0:
            raise ValueError("convex_beta must be >= 1.0")

        self.lambda_ais = lambda_ais
        self.gamma = gamma
        self.shaping_weight = shaping_weight
        self.deny_penalty = deny_penalty
        self.gate_task_on_compliance = gate_task_on_compliance
        self.ais_min = ais_min
        self.convex_beta = convex_beta

    @staticmethod
    def potential(ais_score: float) -> float:
        """Potential function Phi(AIS) = (clamp(AIS, 0, 1000) / 1000)^2 in [0, 1]."""
        if math.isnan(ais_score) or ais_score <= 0.0:
            return 0.0
        norm = min(max(ais_score, 0.0), 1000.0) / 1000.0
        return norm * norm

    def compute_step_reward(
        self,
        r_task: float,
        ais_t: AISComponents | float,
        ais_prev: AISComponents | float = 1000.0,
        deny_count: int = 0,
    ) -> StepRewardBreakdown:
        """Compute step-level reward `R_total(t)`."""
        score_t = ais_t.ais_final if isinstance(ais_t, AISComponents) else float(ais_t)
        score_prev = ais_prev.ais_final if isinstance(ais_prev, AISComponents) else float(ais_prev)

        compliance_zero = (
            (ais_t.s_compliance <= 0.0 or ais_t.zero_annihilated)
            if isinstance(ais_t, AISComponents)
            else (score_t <= 0.0)
        )

        gated = bool(self.gate_task_on_compliance and (compliance_zero or deny_count > 0))
        effective_task = 0.0 if gated else float(r_task)

        ais_norm = min(max(score_t, 0.0), 1000.0) / 1000.0
        ais_term = self.lambda_ais * ais_norm

        phi_t = self.potential(score_t)
        phi_prev = self.potential(score_prev)
        shaping = self.shaping_weight * (self.gamma * phi_t - phi_prev)

        penalty = float(max(0, deny_count)) * self.deny_penalty
        r_total = effective_task + ais_term + shaping - penalty

        return StepRewardBreakdown(
            r_task=effective_task,
            ais_t=score_t,
            ais_prev=score_prev,
            ais_term=ais_term,
            potential_shaping=shaping,
            violation_penalty=penalty,
            r_total=r_total,
            gated_by_compliance=gated,
        )

    def settle_epoch(
        self,
        base_fee_pool: float,
        ais_epoch: float,
        stake_amount: float = 0.0,
        fraud_proof_verified: bool = False,
        slash_fraction: float = 0.50,
    ) -> EpochSettlementResult:
        """Compute on-chain epoch reward payout `Y_e` and stake slashing."""
        if base_fee_pool < 0.0:
            raise ValueError("base_fee_pool must be >= 0")
        score = 0.0 if math.isnan(ais_epoch) else min(max(ais_epoch, 0.0), 1000.0)

        if fraud_proof_verified:
            clamped_slash = min(max(slash_fraction, 0.0), 1.0)
            return EpochSettlementResult(
                base_fee_pool=base_fee_pool,
                ais_epoch=0.0,
                ais_min=self.ais_min,
                multiplier=0.0,
                slashed=True,
                slash_amount=max(0.0, stake_amount) * clamped_slash,
                payout=0.0,
            )

        if score < self.ais_min:
            multiplier = 0.0
        else:
            ratio = (score - self.ais_min) / (1000.0 - self.ais_min)
            multiplier = math.pow(min(max(ratio, 0.0), 1.0), self.convex_beta)

        payout = base_fee_pool * multiplier
        return EpochSettlementResult(
            base_fee_pool=base_fee_pool,
            ais_epoch=score,
            ais_min=self.ais_min,
            multiplier=multiplier,
            slashed=False,
            slash_amount=0.0,
            payout=payout,
        )
