//! Agent Integrity Score (AIS) formula.
//!
//! This crate is the ONLY place the AIS formula is computed anywhere in the
//! Integrity Protocol monorepo — see `docs/INTERFACE_CONTRACT.md` §4.3. Every
//! other package (sdk, cli, dashboard, bcc_middleware) calls the oracle's
//! `GET /v1/agent/{id}/ais` HTTP endpoint rather than re-deriving this math;
//! that indirection is the entire point of having an "oracle" instead of just
//! letting every consumer compute its own opinion of an agent's trustworthiness.
//!
//! Formula (verbatim from the interface contract, §4.3):
//!
//!   AIS = (S_entropy^wE * S_grounding^wG * S_sacrifice^wS * S_compliance^wC) * ZK_boost
//!
//! This is a weighted GEOMETRIC mean (a "volume"), not an arithmetic one. The
//! distinction is load-bearing and is the single most misunderstood thing about
//! this crate — this docstring itself stated the arithmetic form for some time
//! after the code had moved to the geometric one.
//!
//! The operational consequence: **any single zero component annihilates the whole
//! score**, because x^w == 0 for x == 0. An agent with perfect entropy, grounding
//! and compliance but zero reported `sacrifice` scores exactly 0.0, not 800. That
//! is not a bug — a geometric mean deliberately refuses to let a strong axis
//! compensate for a wholly absent one — but it means an agent that simply never
//! *reports* one axis is indistinguishable from one that catastrophically failed
//! it. See `any_single_zero_component_annihilates_ais` in the tests below, and
//! `PRODUCTION_GAPS.md` for the absent-vs-zero question this raises.
//!
//! with default weights wE=0.30, wG=0.30, wS=0.20, wC=0.20 (sum to 1.0) and
//! ZK_boost is blended from 1.0 to 1.15 by the fraction of events in the
//! reporting period whose own attached Barretenberg proof verified.
//!
//! The four `S_*` component scores are each normalized to the same
//! [0, MAX_COMPONENT_SCORE] range so that the weights above are directly
//! comparable contributions. The interface contract pins the top-level
//! formula and weights but does not pin how each S_* is derived from raw
//! telemetry — that derivation is this oracle's judgment call, documented
//! per-function below. If that derivation ever changes, only this file needs
//! to change; no other package embeds this math.

use serde::{Deserialize, Serialize};

/// Every component score is normalized onto this scale before weighting, matching
/// the old prototype's convention (a human-readable "out of 1000" score) so the
/// API's `ais_score` field stays intuitive to operators.
pub const MAX_COMPONENT_SCORE: f64 = 1000.0;
pub const AIS_PROFILE_VERSION: &str = "ais/v1-geometric-1";

/// Canonical step reward: `max(0, r_task - cost) * clamp(ais, 0, 1000) / 1000`.
pub const REWARD_PROFILE_MULTIPLICATIVE: &str = "ais-reward/v2-multiplicative-1";
/// Legacy step reward: `r_task + lambda * ais + shaping - penalty`. Kept so earlier results
/// reproduce. AIS contributes at most `lambda` here, so a task-reward lead larger than that
/// beats any integrity gap — the reason it is no longer the default.
pub const REWARD_PROFILE_ADDITIVE_V1: &str = "ais-reward/v1-additive-1";

#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum RewardProfile {
    #[default]
    Multiplicative,
    AdditiveV1,
}

impl RewardProfile {
    pub fn name(self) -> &'static str {
        match self {
            RewardProfile::Multiplicative => REWARD_PROFILE_MULTIPLICATIVE,
            RewardProfile::AdditiveV1 => REWARD_PROFILE_ADDITIVE_V1,
        }
    }
}

/// `max(0, r_task - cost_penalty) * clamp(ais, 0, 1000) / 1000`; `0` when the step is gated
/// or any input is not finite.
///
/// Both factors are non-negative, so the result is never negative and never decreases as AIS
/// rises. (A negative task term would make LOWER integrity score better.) Pinned across Rust,
/// Python and Cortex by `spec/ais-api/v1/reward-vectors.json`.
pub fn multiplicative_reward(r_task: f64, ais: f64, cost_penalty: f64, gated: bool) -> f64 {
    if gated || !ais.is_finite() || !r_task.is_finite() || !cost_penalty.is_finite() {
        return 0.0;
    }
    let net_task = (r_task - cost_penalty.max(0.0)).max(0.0);
    net_task * (ais.clamp(0.0, MAX_COMPONENT_SCORE) / MAX_COMPONENT_SCORE)
}
pub const DEFAULT_REPORTING_PERIOD_DAYS: i64 = 30;

/// Multiplier applied when the agent has at least one Barretenberg-verified ZK
/// proof in the reporting period. Fixed by the interface contract — not configurable,
/// unlike the weights, because it's a protocol-level incentive (real cryptographic
/// proof of correct behavior is worth more than self-reported telemetry) rather than
/// an operator tuning knob.
pub const ZK_BOOST_FACTOR: f64 = 1.15;
const NO_ZK_BOOST_FACTOR: f64 = 1.0;

/// Configurable weights for the four AIS components. Must sum to 1.0 — enforced by
/// `AisWeights::validate`, not by the type system, because weights are expected to
/// come from operator config (env/DB) rather than always being the compiled-in default.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct AisWeights {
    pub w_entropy: f64,
    pub w_grounding: f64,
    pub w_sacrifice: f64,
    pub w_compliance: f64,
}

impl Default for AisWeights {
    fn default() -> Self {
        // Defaults pinned by docs/INTERFACE_CONTRACT.md §4.3 — do not tune these
        // without updating the contract, since bcc_middleware and the dashboard
        // both render/reason about AIS assuming these are the shipped defaults.
        Self {
            w_entropy: 0.30,
            w_grounding: 0.30,
            w_sacrifice: 0.20,
            w_compliance: 0.20,
        }
    }
}

impl AisWeights {
    /// Returns an error message if the weights don't sum to ~1.0. Floating point
    /// sums of decimal literals (0.30 + 0.30 + 0.20 + 0.20) are not bit-exact, so
    /// this checks within a small epsilon rather than `== 1.0`.
    pub fn validate(&self) -> Result<(), String> {
        if [self.w_entropy, self.w_grounding, self.w_sacrifice, self.w_compliance]
            .iter().any(|w| !w.is_finite()) { return Err("AIS weights must be finite".to_string()); }
        let sum = self.w_entropy + self.w_grounding + self.w_sacrifice + self.w_compliance;
        if (sum - 1.0).abs() > 1e-6 {
            return Err(format!("AIS weights must sum to 1.0, got {sum}"));
        }
        if [self.w_entropy, self.w_grounding, self.w_sacrifice, self.w_compliance]
            .iter()
            .any(|w| *w < 0.0 || *w > 1.0)
        {
            return Err("AIS weights must be non-negative".to_string());
        }
        Ok(())
    }

    /// The same weights with the compliance axis treated as **unobserved**: `w_compliance`
    /// becomes 0 and the other three are rescaled to sum to 1 again.
    ///
    /// Dropping a weight without rescaling would shrink the geometric mean's exponent, so a
    /// perfect agent would score ~178 instead of 1000. A zero weight, unlike a zero score,
    /// does not annihilate the mean. This is the rule `integrity_sdk.core.ais_local` uses
    /// for axes its receipt log cannot observe, and `integrity_sdk.core.ais_reward.
    /// weights_without_compliance` mirrors it.
    ///
    /// Errors when the other three weights are all zero: nothing would remain to score.
    pub fn without_compliance(&self) -> Result<Self, String> {
        let rest = self.w_entropy + self.w_grounding + self.w_sacrifice;
        if !rest.is_finite() || rest <= 0.0 {
            return Err("no non-compliance AIS weight to renormalize onto".to_string());
        }
        let w = Self {
            w_entropy: self.w_entropy / rest,
            w_grounding: self.w_grounding / rest,
            w_sacrifice: self.w_sacrifice / rest,
            w_compliance: 0.0,
        };
        w.validate()?;
        Ok(w)
    }
}

/// Raw, per-agent aggregate inputs the oracle derives from telemetry + ZK verification
/// state before computing AIS. These are aggregates over the *reporting period*
/// (the backend crate currently uses a trailing 30-day window — see
/// `backend::routes::ais::REPORTING_PERIOD_DAYS`), not raw per-event fields.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct AisComponentInputs {
    /// Variance of the agent's reported task performance over the period. 0.0 means
    /// perfectly consistent output; larger values mean erratic/unpredictable behavior.
    /// Unbounded above by construction (it's a raw statistical variance), so the
    /// entropy score below must saturate rather than assume a fixed max.
    pub performance_variance: f64,
    /// "Human Grounding Index": fraction of the agent's actions in the period that
    /// were checked against real human-in-the-loop feedback, in `[0.0, 1.0]`. Higher
    /// is better: an agent that never gets checked is not necessarily misbehaving,
    /// but the protocol can't distinguish that from an agent hiding misbehavior, so
    /// it scores ungrounded agents lower on this axis specifically.
    pub hgi_raw: f64,
    /// An hours-equivalent proxy for the agent's compute/resource commitment (the
    /// "sacrifice" metric) — despite the field name, this is NOT independently verified
    /// GPU-hours telemetry; no such measurement exists in this protocol yet. It's
    /// `backend::derive::derive_sacrifice`'s server-side recomputation of total tokens
    /// processed (from the same signed telemetry `entropy`/`grounding` are derived
    /// from) divided by a documented heuristic constant — real arithmetic on
    /// oracle-recomputed data, not a client's self-reported claim (see
    /// `docs/wiki/concepts/ais.md` and `PRODUCTION_GAPS.md` for what independent
    /// GPU-hour verification would require and why it isn't built). Always >= 0.0.
    pub gpu_hours_verified: f64,
    /// Fraction of the agent's telemetry events in the period that were flagged by
    /// policy evaluation (i.e. the BCC/OPA pipeline in bcc_middleware denied or
    /// flagged the corresponding intent), in `[0.0, 1.0]`. This is the compliance
    /// axis; 0.0 = no flags, 1.0 = every single action was flagged.
    pub penalty_ratio: f64,
    /// Fraction of telemetry events in the reporting period whose own attached ZK proof
    /// was verified, in `[0.0, 1.0]`. The boost is blended by this ratio, so proof for
    /// event A cannot grant the full-period multiplier to unrelated event B.
    pub zk_verified_event_ratio: f64,
}

/// Full breakdown of an AIS computation, returned by the API so operators/consumers
/// can see *why* an agent scored the way it did rather than just the final number —
/// important for a trust-scoring system, where an opaque score is not actionable.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct AisBreakdown {
    pub s_entropy: f64,
    pub s_grounding: f64,
    pub s_sacrifice: f64,
    pub s_compliance: f64,
    pub zk_boost: f64,
    pub ais_base: f64,
    pub ais_post_boost: f64,
    /// Final AIS after the weighted geometric mean, ZK boost, and (when requested)
    /// verification-tier ceiling. `score()` returns the raw post-boost value;
    /// `score_with_tier()` clamps it to the documented 300/600/850/1000 ladder.
    pub ais: f64,
    pub tier_ceiling: f64,
    /// spec/integrity-protocol-v3.2.md §3.1.1 eq. 4b's `r(ι)`: the normalised,
    /// **pre-boost** base score clamped to `[0,1]`, for use as a reputation-parameterised
    /// constraint input — never `ais` above, which is post-boost and unclamped. Computed
    /// from the same pre-boost weighted geometric mean `ais` is derived from (divide out
    /// `zk_boost` rather than recomputing, so the two can never drift). `score_with_tier`
    /// additionally applies the verification-tier ceiling here, matching what it does to
    /// `ais`, so an agent's identity-assurance level bounds its constraint input the same
    /// way it bounds its display score.
    pub constraint_score: f64,
    /// **Shadow-mode only** (`spec` §3.1.4 row 5, `PRODUCTION_GAPS.md` §27) — what the
    /// proposed per-component floor + conjunctive Θ gate (eq. 4a) would decide, using
    /// `AisFloors::default()`'s provisional thresholds. Computed and reported for
    /// observation; **does not affect `ais` or `constraint_score` above**, does not gate
    /// anything, and is not wired into chain pushes or dispute logic. No floor exists for
    /// sacrifice (spec: "contribution is optional").
    pub gate_entropy_pass: bool,
    pub gate_grounding_pass: bool,
    pub gate_compliance_pass: bool,
    /// Conjunction of the three `gate_*_pass` fields above.
    pub gate_would_pass: bool,
}

/// Per-component floors for the proposed conjunctive gate (spec §3.1.1 eq. 4a,
/// `PRODUCTION_GAPS.md` §27). **Provisional, shadow-mode-only values** — chosen to sit
/// comfortably below every component of the one real registered agent's current telemetry
/// (entropy 268/1000, grounding 950/1000, compliance 1000/1000 as of 2026-08-17) so shadow
/// observation starts without immediately flagging the repo's own dogfooding agent, not
/// because they're believed to be the right permanent thresholds — there isn't enough real
/// agent-population data yet to calibrate permanent values responsibly. The compliance
/// floor of 400 is the one spec §3.1.1 itself uses as a worked illustrative example
/// ("every row above 0.631 and below the floor collapses to zero"). Revisit once shadow
/// observation has run against real traffic from more than one agent.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct AisFloors {
    pub entropy: f64,
    pub grounding: f64,
    pub compliance: f64,
}

impl Default for AisFloors {
    fn default() -> Self {
        Self {
            entropy: 100.0,
            grounding: 200.0,
            compliance: 400.0,
        }
    }
}

impl AisFloors {
    pub fn validate(&self) -> Result<(), String> {
        if [self.entropy, self.grounding, self.compliance].iter()
            .any(|v| !v.is_finite() || *v < 0.0 || *v > MAX_COMPONENT_SCORE) {
            return Err("AIS floors must be finite values in [0, 1000]".to_string());
        }
        Ok(())
    }
}

/// Stateless computation engine over a fixed set of weights. Cheap to construct;
/// callers can build one per-request from operator-configured weights, or reuse
/// `AisEngine::default()`.
#[derive(Debug, Clone, Copy)]
pub struct AisEngine {
    /// How an AIS becomes a control zone (see [`ZonePolicy`]). Defaulted to per-tier
    /// thresholds, so an agent is judged against what its verification tier can reach.
    pub zone_policy: ZonePolicy,
    pub weights: AisWeights,
    /// Shadow-mode-only gate floors (see `AisFloors`'s own doc comment). Defaulted so
    /// every existing caller of `AisEngine::default()`/`new()` gets shadow observation for
    /// free without needing to opt in — it's purely additive reporting, not enforcement.
    pub floors: AisFloors,
}

impl Default for AisEngine {
    fn default() -> Self {
        Self {
            zone_policy: ZonePolicy::default(),
            weights: AisWeights::default(),
            floors: AisFloors::default(),
        }
    }
}

impl AisEngine {
    pub fn new(weights: AisWeights) -> Result<Self, String> {
        weights.validate()?;
        let floors = AisFloors::default();
        floors.validate()?;
        Ok(Self {
            zone_policy: ZonePolicy::default(),
            weights,
            floors,
        })
    }

    /// The same engine with an operator-chosen zone policy. Fails on a policy that does not
    /// validate, so an unreachable or inverted threshold is a startup error, not a silent lockout.
    pub fn with_zone_policy(mut self, zone_policy: ZonePolicy) -> Result<Self, String> {
        zone_policy.validate()?;
        self.zone_policy = zone_policy;
        Ok(self)
    }

    /// Same as `new`, but with explicit (e.g. operator-configured or test-chosen) floors
    /// instead of `AisFloors::default()`'s provisional values.
    pub fn with_floors(weights: AisWeights, floors: AisFloors) -> Result<Self, String> {
        weights.validate()?;
        floors.validate()?;
        Ok(Self { zone_policy: ZonePolicy::default(), weights, floors })
    }

    /// S_entropy: rewards *stability*, not any particular performance level. Uses a
    /// Gaussian-style decay so small variance barely moves the score but variance
    /// growing without bound saturates toward 0 rather than going negative.
    pub fn calculate_entropy_score(&self, performance_variance: f64) -> f64 {
        if !performance_variance.is_finite() { return 0.0; }
        let v = performance_variance.max(0.0);
        let stability_factor = (-1.5 * v * v).exp();
        (stability_factor * MAX_COMPONENT_SCORE).clamp(0.0, MAX_COMPONENT_SCORE)
    }

    /// S_grounding: directly proportional to the human-grounding fraction. Simple by
    /// design — there's no principled nonlinearity to apply here, unlike the
    /// logarithmic "sacrifice" metric where marginal hours matter less at scale.
    pub fn calculate_grounding_score(&self, hgi_raw: f64) -> f64 {
        if hgi_raw.is_nan() || hgi_raw == f64::NEG_INFINITY { return 0.0; }
        if hgi_raw == f64::INFINITY { return MAX_COMPONENT_SCORE; }
        (hgi_raw.clamp(0.0, 1.0) * MAX_COMPONENT_SCORE).clamp(0.0, MAX_COMPONENT_SCORE)
    }

    /// S_sacrifice: logarithmic scale over verified GPU-hours, saturating at 1000
    /// verified hours (chosen so early contributions matter a lot and marginal hours
    /// at high volume matter less — a whale contributing 100x the compute of a
    /// baseline agent should not score 100x higher, since that would make the score
    /// pure pay-to-win rather than a trust signal).
    pub fn calculate_sacrifice_score(&self, gpu_hours_verified: f64) -> f64 {
        if gpu_hours_verified.is_nan() || gpu_hours_verified == f64::NEG_INFINITY { return 0.0; }
        if gpu_hours_verified == f64::INFINITY { return MAX_COMPONENT_SCORE; }
        let hours = gpu_hours_verified.max(0.0);
        let sacrifice_idx = ((hours + 1.0).log10() / 3.0).min(1.0);
        (sacrifice_idx * MAX_COMPONENT_SCORE).clamp(0.0, MAX_COMPONENT_SCORE)
    }

    /// S_compliance: linear inverse of the penalty ratio. Deliberately the simplest
    /// possible mapping (not logarithmic like sacrifice) because policy violations
    /// are a binary-ish signal per action — there's no principled reason a violation
    /// rate of 0.4 should be treated non-linearly worse than 0.2, unlike compute
    /// contribution where marginal returns genuinely diminish.
    pub fn calculate_compliance_score(&self, penalty_ratio: f64) -> f64 {
        if penalty_ratio.is_nan() || penalty_ratio == f64::NEG_INFINITY || penalty_ratio == f64::INFINITY { return 0.0; }
        let clean_ratio = 1.0 - penalty_ratio.clamp(0.0, 1.0);
        (clean_ratio * MAX_COMPONENT_SCORE).clamp(0.0, MAX_COMPONENT_SCORE)
    }

    /// Computes the full AIS breakdown per docs/INTERFACE_CONTRACT.md §4.3.
    pub fn score(&self, inputs: &AisComponentInputs) -> AisBreakdown {
        let s_entropy = self.calculate_entropy_score(inputs.performance_variance);
        let s_grounding = self.calculate_grounding_score(inputs.hgi_raw);
        let s_sacrifice = self.calculate_sacrifice_score(inputs.gpu_hours_verified);
        let s_compliance = self.calculate_compliance_score(inputs.penalty_ratio);

        let verified_ratio = if inputs.zk_verified_event_ratio.is_finite() { inputs.zk_verified_event_ratio.clamp(0.0, 1.0) } else { 0.0 };
        let zk_boost = NO_ZK_BOOST_FACTOR
            + (ZK_BOOST_FACTOR - NO_ZK_BOOST_FACTOR) * verified_ratio;

        let components = [(s_entropy, self.weights.w_entropy), (s_grounding, self.weights.w_grounding), (s_sacrifice, self.weights.w_sacrifice), (s_compliance, self.weights.w_compliance)];
        let weighted = if components.iter().any(|(v, w)| *w > 0.0 && *v == 0.0) { 0.0 } else {
            components.iter().filter(|(_, w)| *w > 0.0).map(|(v, w)| *w * v.ln()).sum::<f64>().exp().clamp(0.0, MAX_COMPONENT_SCORE)
        };
        let ais_post_boost = (weighted * zk_boost).clamp(0.0, MAX_COMPONENT_SCORE * ZK_BOOST_FACTOR);

        // eq. 4b: r(ι) is the PRE-boost base score, normalised and clamped to [0,1].
        // `weighted` (not `weighted * zk_boost`) is deliberate — see AisBreakdown's doc
        // comment on why the boost must never reach a constraint input.
        let constraint_score = (weighted / MAX_COMPONENT_SCORE).clamp(0.0, 1.0);

        // Shadow-mode gate (eq. 4a's conjunctive Θ product) — reporting only, see
        // AisBreakdown's doc comment. No floor on sacrifice by design.
        let gate_entropy_pass = s_entropy >= self.floors.entropy;
        let gate_grounding_pass = s_grounding >= self.floors.grounding;
        let gate_compliance_pass = s_compliance >= self.floors.compliance;

        AisBreakdown {
            s_entropy,
            s_grounding,
            s_sacrifice,
            s_compliance,
            zk_boost,
            ais_base: weighted,
            ais_post_boost,
            ais: ais_post_boost,
            tier_ceiling: MAX_COMPONENT_SCORE,
            constraint_score,
            gate_entropy_pass,
            gate_grounding_pass,
            gate_compliance_pass,
            gate_would_pass: gate_entropy_pass && gate_grounding_pass && gate_compliance_pass,
        }
    }

    /// Returns the maximum AIS ceiling allowed for a given verification tier:
    /// Tier 0 (Developer API Key): 300.0
    /// Tier 1 (Sovereign Software Key): 600.0
    /// Tier 2 (Linked DNS/Social Attestation): 850.0
    /// Tier 3 (Institutional TEE/Audit): 1000.0 (maximum score; ZK boost is included
    /// before the cap)
    pub fn ceiling_for_tier(verification_tier: i32) -> f64 {
        match verification_tier {
            i32::MIN..=0 => 300.0,
            1 => 600.0,
            2 => 850.0,
            _ => 1000.0,
        }
    }

    /// Computes the AIS breakdown and applies the Verification Ladder score ceiling.
    pub fn score_with_tier(&self, inputs: &AisComponentInputs, verification_tier: i32) -> AisBreakdown {
        let mut breakdown = self.score(inputs);
        let ceiling = Self::ceiling_for_tier(verification_tier);
        breakdown.ais = breakdown.ais.min(ceiling);
        breakdown.tier_ceiling = ceiling;
        // Same ceiling, same rationale, expressed on constraint_score's [0,1] scale:
        // an agent's identity-assurance tier bounds its constraint input exactly as it
        // bounds its display score, so a low-tier agent can't use eq. 4b to reach a
        // reputation-parameterised bound its verification level hasn't earned.
        breakdown.constraint_score = breakdown.constraint_score.min(ceiling / MAX_COMPONENT_SCORE);
        breakdown
    }

    /// Evaluates the closed-loop control zone (`green` / `yellow` / `red` with hysteresis), the
    /// step reward under the canonical multiplicative profile, and the on-chain epoch yield
    /// multiplier (`Y_e`).
    pub fn evaluate_closed_loop_reward(
        &self,
        breakdown: &AisBreakdown,
        prev_ais: f64,
        prev_zone: Option<&str>,
        r_task: f64,
        deny_count: u32,
        hard_interlock_tripped: bool,
    ) -> ClosedLoopRewardEvaluation {
        self.evaluate_closed_loop_reward_with_profile(
            breakdown,
            prev_ais,
            prev_zone,
            r_task,
            deny_count,
            hard_interlock_tripped,
            RewardProfile::default(),
        )
    }

    /// As [`Self::evaluate_closed_loop_reward`], with the reward profile chosen explicitly.
    /// The control zone and epoch yield multiplier do not depend on the profile.
    #[allow(clippy::too_many_arguments)]
    pub fn evaluate_closed_loop_reward_with_profile(
        &self,
        breakdown: &AisBreakdown,
        prev_ais: f64,
        prev_zone: Option<&str>,
        r_task: f64,
        deny_count: u32,
        hard_interlock_tripped: bool,
        profile: RewardProfile,
    ) -> ClosedLoopRewardEvaluation {
        let score = if breakdown.ais.is_finite() {
            breakdown.ais.clamp(0.0, MAX_COMPONENT_SCORE)
        } else {
            0.0
        };
        let prev = if prev_ais.is_finite() {
            prev_ais.clamp(0.0, MAX_COMPONENT_SCORE)
        } else {
            MAX_COMPONENT_SCORE
        };

        let zone_thresholds = self.zone_policy.thresholds_for_ceiling(breakdown.tier_ceiling);
        let control_zone = zone_thresholds
            .control_zone(score, prev_zone, hard_interlock_tripped)
            .to_string();

        let compliance_zero = breakdown.s_compliance <= 0.0 || score <= 0.0;
        let gated_by_compliance = compliance_zero || deny_count > 0 || hard_interlock_tripped;
        let r_task_effective = if gated_by_compliance {
            0.0
        } else if r_task.is_finite() {
            r_task
        } else {
            0.0
        };

        let lambda_ais = 0.50_f64;
        let gamma = 0.99_f64;
        let shaping_weight = 0.25_f64;
        let deny_penalty = 1.0_f64;

        let ais_norm = score / MAX_COMPONENT_SCORE;
        let prev_norm = prev / MAX_COMPONENT_SCORE;
        let ais_term = lambda_ais * ais_norm;

        let phi_t = ais_norm * ais_norm;
        let phi_prev = prev_norm * prev_norm;
        let potential_shaping = shaping_weight * (gamma * phi_t - phi_prev);

        let violation_penalty = (deny_count as f64) * deny_penalty;
        let (r_task_effective, ais_term, potential_shaping, violation_penalty, r_total) = match profile {
            RewardProfile::AdditiveV1 => (
                r_task_effective,
                ais_term,
                potential_shaping,
                violation_penalty,
                r_task_effective + ais_term + potential_shaping - violation_penalty,
            ),
            // No additive AIS, shaping or penalty terms: integrity scales the whole payoff, and
            // a gated step earns exactly zero.
            RewardProfile::Multiplicative => (
                r_task_effective.max(0.0),
                0.0,
                0.0,
                0.0,
                multiplicative_reward(r_task, score, 0.0, gated_by_compliance),
            ),
        };

        let ais_min = 750.0_f64;
        let epoch_yield_multiplier = if gated_by_compliance || score < ais_min {
            0.0
        } else {
            ((score - ais_min) / (MAX_COMPONENT_SCORE - ais_min))
                .clamp(0.0, 1.0)
                .powi(2)
        };

        ClosedLoopRewardEvaluation {
            reward_profile: profile.name().to_string(),
            control_zone,
            zone_policy: self.zone_policy.mode.name().to_string(),
            zone_thresholds,
            r_task_effective,
            ais_term,
            potential_shaping,
            violation_penalty,
            r_total,
            gated_by_compliance,
            epoch_yield_multiplier,
        }
    }
}

pub const ZONE_POLICY_PER_TIER: &str = "per_tier";
pub const ZONE_POLICY_RELATIVE: &str = "relative";
pub const ZONE_POLICY_ABSOLUTE: &str = "absolute";

/// Where the zone boundaries sit, on the AIS scale `[0, 1000]`.
///
/// `yellow` is the red/yellow boundary, `green` the yellow/green boundary, and `recovery` the
/// score a degraded agent must reach to become green again (the hysteresis deadband).
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct ZoneThresholds {
    pub yellow: f64,
    pub green: f64,
    pub recovery: f64,
}

impl ZoneThresholds {
    /// `0 <= yellow < green <= recovery <= max`, all finite. `max` is the highest score the
    /// thresholds apply to: a `green` above it could never be reached.
    pub fn validate(&self, max: f64) -> Result<(), String> {
        let ordered = self.yellow.is_finite()
            && self.green.is_finite()
            && self.recovery.is_finite()
            && 0.0 <= self.yellow
            && self.yellow < self.green
            && self.green <= self.recovery
            && self.recovery <= max;
        if ordered {
            Ok(())
        } else {
            Err(format!(
                "zone thresholds must satisfy 0 <= yellow < green <= recovery <= {max}, got {}/{}/{}",
                self.yellow, self.green, self.recovery
            ))
        }
    }

    /// The zone for `score`. A tripped interlock or a score that is not finite is red.
    pub fn control_zone(&self, score: f64, prev_zone: Option<&str>, hard_interlock_tripped: bool) -> &'static str {
        if hard_interlock_tripped || !score.is_finite() || score < self.yellow {
            "red"
        } else if matches!(prev_zone, Some("yellow") | Some("red")) {
            if score >= self.recovery {
                "green"
            } else {
                "yellow"
            }
        } else if score >= self.green {
            "green"
        } else {
            "yellow"
        }
    }
}

/// Which rule turns an AIS into zone thresholds.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum ZonePolicyMode {
    /// A threshold set per verification tier (the default).
    #[default]
    PerTier,
    /// One set of fractions, multiplied by the agent's tier ceiling.
    Relative,
    /// One threshold set for every tier. With the default 750/900/920 this is the behaviour
    /// before zone policies existed, under which tiers 0 and 1 can never leave red.
    Absolute,
}

impl ZonePolicyMode {
    pub fn name(self) -> &'static str {
        match self {
            ZonePolicyMode::PerTier => ZONE_POLICY_PER_TIER,
            ZonePolicyMode::Relative => ZONE_POLICY_RELATIVE,
            ZonePolicyMode::Absolute => ZONE_POLICY_ABSOLUTE,
        }
    }

    pub fn parse(name: &str) -> Result<Self, String> {
        match name {
            ZONE_POLICY_PER_TIER => Ok(ZonePolicyMode::PerTier),
            ZONE_POLICY_RELATIVE => Ok(ZonePolicyMode::Relative),
            ZONE_POLICY_ABSOLUTE => Ok(ZonePolicyMode::Absolute),
            other => Err(format!(
                "zone policy must be one of {ZONE_POLICY_PER_TIER}, {ZONE_POLICY_RELATIVE}, {ZONE_POLICY_ABSOLUTE}; got {other:?}"
            )),
        }
    }
}

/// How an AIS becomes a control zone.
///
/// AIS is capped by verification tier (300 / 600 / 850 / 1000), so one absolute threshold set
/// cannot serve every tier: under 750/900/920 a tier 0 or tier 1 agent is red whatever it does.
/// `per_tier` and `relative` both judge an agent against what its tier can reach. They differ in
/// what the operator edits: a table of scores per tier, or one set of fractions.
///
/// All three parameter sets are always present; `mode` selects which one is used. The Python
/// reference is `integrity_sdk.core.ais_reward.ZonePolicy`, and both are checked against
/// `spec/ais-api/v1/zone-vectors.json`.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct ZonePolicy {
    pub mode: ZonePolicyMode,
    /// Indexed by tier 0..=3.
    pub per_tier: [ZoneThresholds; 4],
    /// Fractions of the tier ceiling, each in `[0, 1]`.
    pub relative: ZoneThresholds,
    pub absolute: ZoneThresholds,
}

impl Default for ZonePolicy {
    /// The per-tier defaults are 75% / 90% / 92% of each tier's ceiling, which for tier 3 is the
    /// original 750 / 900 / 920.
    fn default() -> Self {
        Self {
            mode: ZonePolicyMode::PerTier,
            per_tier: [
                ZoneThresholds { yellow: 225.0, green: 270.0, recovery: 276.0 },
                ZoneThresholds { yellow: 450.0, green: 540.0, recovery: 552.0 },
                ZoneThresholds { yellow: 637.5, green: 765.0, recovery: 782.0 },
                ZoneThresholds { yellow: 750.0, green: 900.0, recovery: 920.0 },
            ],
            relative: ZoneThresholds { yellow: 0.75, green: 0.90, recovery: 0.92 },
            absolute: ZoneThresholds { yellow: 750.0, green: 900.0, recovery: 920.0 },
        }
    }
}

impl ZonePolicy {
    /// Every parameter set is checked, not only the selected one, so switching `mode` later
    /// cannot reveal a bad table. A per-tier threshold above its own tier's ceiling is refused.
    pub fn validate(&self) -> Result<(), String> {
        for (tier, thresholds) in self.per_tier.iter().enumerate() {
            thresholds
                .validate(AisEngine::ceiling_for_tier(tier as i32))
                .map_err(|e| format!("per_tier tier {tier}: {e}"))?;
        }
        self.relative.validate(1.0).map_err(|e| format!("relative: {e}"))?;
        self.absolute.validate(MAX_COMPONENT_SCORE).map_err(|e| format!("absolute: {e}"))
    }

    /// The thresholds for an agent of `verification_tier` (clamped to 0..=3, as
    /// [`AisEngine::ceiling_for_tier`] does).
    pub fn thresholds_for_tier(&self, verification_tier: i32) -> ZoneThresholds {
        let tier = verification_tier.clamp(0, 3);
        match self.mode {
            ZonePolicyMode::PerTier => self.per_tier[tier as usize],
            ZonePolicyMode::Relative => {
                let ceiling = AisEngine::ceiling_for_tier(tier);
                ZoneThresholds {
                    yellow: self.relative.yellow * ceiling,
                    green: self.relative.green * ceiling,
                    recovery: self.relative.recovery * ceiling,
                }
            }
            ZonePolicyMode::Absolute => self.absolute,
        }
    }

    /// As [`Self::thresholds_for_tier`], from the ceiling an [`AisBreakdown`] carries. A ceiling
    /// that is not one of the four tier ceilings resolves to the highest tier at or below it, and
    /// to tier 0 when it is below every ceiling or not finite.
    pub fn thresholds_for_ceiling(&self, tier_ceiling: f64) -> ZoneThresholds {
        let tier = (0..=3)
            .rev()
            .find(|tier| tier_ceiling >= AisEngine::ceiling_for_tier(*tier))
            .unwrap_or(0);
        self.thresholds_for_tier(tier)
    }
}

/// Canonical Closed-Loop AIS Control Zone and Step/Epoch Reward Evaluation.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ClosedLoopRewardEvaluation {
    /// Active closed-loop zone: `"green"` (`>= green`, or `>= recovery` when coming back from
    /// yellow or red), `"yellow"` (`yellow <= AIS < green`), or `"red"` (`< yellow` or interlock
    /// tripped). The three thresholds are `zone_thresholds`, chosen by `zone_policy`.
    pub control_zone: String,
    /// Which [`ZonePolicy`] mode chose the thresholds: `per_tier`, `relative` or `absolute`.
    pub zone_policy: String,
    /// The thresholds this agent was judged against, on the AIS scale.
    pub zone_thresholds: ZoneThresholds,
    /// Which step-reward formula produced `r_total`: [`REWARD_PROFILE_MULTIPLICATIVE`]
    /// (default) or [`REWARD_PROFILE_ADDITIVE_V1`].
    pub reward_profile: String,
    pub r_task_effective: f64,
    pub ais_term: f64,
    pub potential_shaping: f64,
    pub violation_penalty: f64,
    pub r_total: f64,
    pub gated_by_compliance: bool,
    pub epoch_yield_multiplier: f64,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn without_compliance_renormalizes_the_other_three() {
        let w = AisWeights::default().without_compliance().unwrap();
        assert_eq!(w.w_compliance, 0.0);
        assert!((w.w_entropy - 0.375).abs() < 1e-12);
        assert!((w.w_grounding - 0.375).abs() < 1e-12);
        assert!((w.w_sacrifice - 0.25).abs() < 1e-12);
        w.validate().unwrap();
    }

    #[test]
    fn unobserved_compliance_does_not_annihilate_or_shrink_a_perfect_score() {
        // Perfect on the three observed axes, and penalty_ratio = 1.0 (what the oracle used
        // to store for every event it had no evidence for).
        let inputs = AisComponentInputs {
            performance_variance: 0.0,
            hgi_raw: 1.0,
            gpu_hours_verified: 999.0,
            penalty_ratio: 1.0,
            zk_verified_event_ratio: 0.0,
        };
        let observed = AisEngine::new(AisWeights::default()).unwrap().score(&inputs);
        assert_eq!(observed.ais_base, 0.0, "a zero compliance score annihilates the mean");
        let engine = AisEngine::new(AisWeights::default().without_compliance().unwrap()).unwrap();
        let unobserved = engine.score(&inputs);
        assert!((unobserved.ais_base - 1000.0).abs() < 1e-6, "got {}", unobserved.ais_base);
    }

    #[test]
    fn without_compliance_refuses_a_compliance_only_profile() {
        let w = AisWeights { w_entropy: 0.0, w_grounding: 0.0, w_sacrifice: 0.0, w_compliance: 1.0 };
        assert!(w.without_compliance().is_err());
    }

    #[test]
    fn default_weights_sum_to_one() {
        AisWeights::default().validate().unwrap();
    }

    #[test]
    fn rejects_weights_that_dont_sum_to_one() {
        let bad = AisWeights {
            w_entropy: 0.5,
            w_grounding: 0.5,
            w_sacrifice: 0.5,
            w_compliance: 0.5,
        };
        assert!(bad.validate().is_err());
        assert!(AisEngine::new(bad).is_err());
    }

    #[test]
    fn rejects_negative_weights() {
        let bad = AisWeights {
            w_entropy: -0.1,
            w_grounding: 0.4,
            w_sacrifice: 0.4,
            w_compliance: 0.3,
        };
        assert!(bad.validate().is_err());
    }

    #[test]
    fn rejects_non_finite_weights_and_floors() {
        assert!(AisWeights { w_entropy: f64::NAN, ..AisWeights::default() }.validate().is_err());
        assert!(AisFloors { entropy: f64::INFINITY, ..AisFloors::default() }.validate().is_err());
    }

    #[test]
    fn non_finite_inputs_fail_closed_or_saturate_by_direction() {
        let engine = AisEngine::default();
        assert_eq!(engine.calculate_entropy_score(f64::NAN), 0.0);
        assert_eq!(engine.calculate_grounding_score(f64::NAN), 0.0);
        assert_eq!(engine.calculate_grounding_score(f64::INFINITY), MAX_COMPONENT_SCORE);
        assert_eq!(engine.calculate_sacrifice_score(f64::NAN), 0.0);
        assert_eq!(engine.calculate_sacrifice_score(f64::INFINITY), MAX_COMPONENT_SCORE);
        assert_eq!(engine.calculate_compliance_score(f64::NAN), 0.0);
    }

    #[test]
    fn breakdown_exposes_distinct_base_boosted_and_capped_values() {
        let inputs = AisComponentInputs { performance_variance: 0.2, hgi_raw: 0.8, gpu_hours_verified: 500.0, penalty_ratio: 0.1, zk_verified_event_ratio: 1.0 };
        let b = AisEngine::default().score_with_tier(&inputs, 1);
        assert!(b.ais_base < b.ais_post_boost);
        assert_eq!(b.ais, b.ais_post_boost.min(600.0));
        assert_eq!(b.tier_ceiling, 600.0);
    }

    #[test]
    fn worst_case_agent_scores_near_zero() {
        let engine = AisEngine::default();
        let inputs = AisComponentInputs {
            performance_variance: 100.0, // wildly erratic
            hgi_raw: 0.0,                // never human-checked
            gpu_hours_verified: 0.0,     // no verified contribution
            penalty_ratio: 1.0,          // every action flagged
            zk_verified_event_ratio: 0.0,
        };
        let breakdown = engine.score(&inputs);
        assert!(breakdown.ais < 1.0, "expected near-zero AIS, got {}", breakdown.ais);
    }

    #[test]
    fn best_case_agent_without_zk_scores_near_max_unboosted() {
        let engine = AisEngine::default();
        let inputs = AisComponentInputs {
            performance_variance: 0.0,
            hgi_raw: 1.0,
            gpu_hours_verified: 1000.0,
            penalty_ratio: 0.0,
            zk_verified_event_ratio: 0.0,
        };
        let breakdown = engine.score(&inputs);
        assert!((breakdown.ais - 1000.0).abs() < 1.0, "expected ~1000, got {}", breakdown.ais);
        assert_eq!(breakdown.zk_boost, 1.0);
    }

    #[test]
    fn zk_boost_multiplies_final_score_by_exactly_1_15() {
        let engine = AisEngine::default();
        let base_inputs = AisComponentInputs {
            performance_variance: 0.2,
            hgi_raw: 0.8,
            gpu_hours_verified: 500.0,
            penalty_ratio: 0.1,
            zk_verified_event_ratio: 0.0,
        };
        let mut boosted_inputs = base_inputs;
        boosted_inputs.zk_verified_event_ratio = 1.0;

        let unboosted = engine.score(&base_inputs);
        let boosted = engine.score(&boosted_inputs);

        assert!((boosted.ais - unboosted.ais * ZK_BOOST_FACTOR).abs() < 1e-9);
    }

    #[test]
    fn zk_boost_is_proportional_to_verified_event_coverage() {
        let engine = AisEngine::default();
        let base_inputs = AisComponentInputs {
            performance_variance: 0.1,
            hgi_raw: 0.8,
            gpu_hours_verified: 100.0,
            penalty_ratio: 0.0,
            zk_verified_event_ratio: 0.0,
        };
        let unverified = engine.score(&base_inputs);
        let half_verified = engine.score(&AisComponentInputs {
            zk_verified_event_ratio: 0.5,
            ..base_inputs
        });
        let fully_verified = engine.score(&AisComponentInputs {
            zk_verified_event_ratio: 1.0,
            ..base_inputs
        });

        assert!((half_verified.zk_boost - 1.075).abs() < 1e-9);
        assert!((fully_verified.zk_boost - 1.15).abs() < 1e-9);
        assert!((half_verified.ais - unverified.ais * 1.075).abs() < 1e-9);
        assert!(half_verified.ais < fully_verified.ais);
    }

    #[test]
    fn compliance_score_is_linear_inverse_of_penalty_ratio() {
        let engine = AisEngine::default();
        assert_eq!(engine.calculate_compliance_score(0.0), 1000.0);
        assert_eq!(engine.calculate_compliance_score(1.0), 0.0);
        assert_eq!(engine.calculate_compliance_score(0.25), 750.0);
        // Out-of-range inputs get clamped rather than producing a nonsensical score.
        assert_eq!(engine.calculate_compliance_score(-0.5), 1000.0);
        assert_eq!(engine.calculate_compliance_score(1.5), 0.0);
    }

    #[test]
    fn sacrifice_score_saturates_at_1000_verified_hours() {
        let engine = AisEngine::default();
        let at_ceiling = engine.calculate_sacrifice_score(1000.0);
        let past_ceiling = engine.calculate_sacrifice_score(50_000.0);
        assert!((at_ceiling - 1000.0).abs() < 1.0);
        assert!((past_ceiling - 1000.0).abs() < 1.0);
        assert!(engine.calculate_sacrifice_score(0.0) < at_ceiling);
    }

    #[test]
    fn verification_ladder_tier_ceilings_enforced() {
        let engine = AisEngine::default();
        let perfect_inputs = AisComponentInputs {
            performance_variance: 0.0,
            hgi_raw: 1.0,
            gpu_hours_verified: 1000.0,
            penalty_ratio: 0.0,
            zk_verified_event_ratio: 0.0,
        };

        // Tier 0 (Dev Key): capped at 300
        let score_t0 = engine.score_with_tier(&perfect_inputs, 0);
        assert_eq!(score_t0.ais, 300.0);

        // Tier 1 (Sovereign): capped at 600
        let score_t1 = engine.score_with_tier(&perfect_inputs, 1);
        assert_eq!(score_t1.ais, 600.0);

        // Tier 2 (Linked): capped at 850
        let score_t2 = engine.score_with_tier(&perfect_inputs, 2);
        assert_eq!(score_t2.ais, 850.0);

        // Tier 3 (Institutional): capped at the protocol maximum (1000).
        let score_t3 = engine.score_with_tier(&perfect_inputs, 3);
        assert!((score_t3.ais - 1000.0).abs() < 1e-6);

        // The cap applies after the ZK boost too; tier 3 cannot exceed 1000.
        let boosted = AisComponentInputs { zk_verified_event_ratio: 1.0, ..perfect_inputs };
        assert_eq!(engine.score_with_tier(&boosted, 3).ais, 1000.0);

        // Unknown/negative values cannot bypass the lowest identity ceiling.
        assert_eq!(engine.score_with_tier(&perfect_inputs, -1).ais, 300.0);
    }

    // -----------------------------------------------------------------------
    // Formula-shape regression guards
    // -----------------------------------------------------------------------
    // These exist because of a measured gap: replacing the weighted GEOMETRIC
    // mean in `score()` with a weighted ARITHMETIC mean left all 9 pre-existing
    // tests passing. Every case above evaluates either at a corner where the two
    // formulas agree (all components equal: w's sum to 1, so both reduce to that
    // same value) or above a tier ceiling that clips the difference away. The
    // single most load-bearing number in the protocol had no test pinning its
    // actual shape. These two do.

    #[test]
    fn ais_uses_geometric_not_arithmetic_mean_on_unequal_components() {
        let engine = AisEngine::new(AisWeights::default()).unwrap();

        // Deliberately unequal, all non-zero, and chosen so the result sits well
        // below the tier-3 ceiling — otherwise clipping would mask the difference.
        // entropy 800, grounding 600, sacrifice 400, compliance 900:
        //   geometric  = 800^.3 * 600^.3 * 400^.2 * 900^.2 ≈ 653.5
        //   arithmetic = 800*.3 + 600*.3 + 400*.2 + 900*.2  = 680.0
        // ~26 points apart: comfortably outside the tolerance below, so a swapped
        // formula cannot slip through.
        let w = AisWeights::default();
        let geometric = 800f64.powf(w.w_entropy)
            * 600f64.powf(w.w_grounding)
            * 400f64.powf(w.w_sacrifice)
            * 900f64.powf(w.w_compliance);
        let arithmetic = 800.0 * w.w_entropy
            + 600.0 * w.w_grounding
            + 400.0 * w.w_sacrifice
            + 900.0 * w.w_compliance;

        // Sanity: the two formulas genuinely disagree on this input, so the
        // assertion below is capable of failing if the shape is swapped.
        assert!(
            (geometric - arithmetic).abs() > 5.0,
            "test input must discriminate the two formulas (geo {geometric}, arith {arithmetic})"
        );

        let scored = engine.score(&component_inputs_yielding(800.0, 600.0, 400.0, 900.0, &engine));
        assert!(
            (scored.ais - geometric).abs() < 1.0,
            "AIS must be the weighted GEOMETRIC mean; got {} (geometric {geometric}, arithmetic {arithmetic})",
            scored.ais
        );
    }

    #[test]
    fn any_single_zero_component_annihilates_ais() {
        // The operational consequence of a geometric mean, and the reason the
        // xibalba agent's live AIS read 0.0 for weeks: it reported no token
        // usage, so `sacrifice` derived to 0, and 0^0.2 == 0 zeroes the product
        // no matter how perfect the other three axes are. Anyone changing this
        // formula must decide about this behavior deliberately.
        let engine = AisEngine::new(AisWeights::default()).unwrap();
        let inputs = AisComponentInputs {
            performance_variance: 0.0,   // -> s_entropy    = 1000 (best)
            hgi_raw: 1.0,                // -> s_grounding  = 1000 (best)
            gpu_hours_verified: 0.0,     // -> s_sacrifice  = 0    (nothing reported)
            penalty_ratio: 0.0,          // -> s_compliance = 1000 (best)
            zk_verified_event_ratio: 0.0,
        };
        let scored = engine.score(&inputs);
        assert_eq!(scored.s_sacrifice, 0.0, "precondition: sacrifice must be 0");
        assert!(scored.s_entropy > 999.0 && scored.s_grounding > 999.0 && scored.s_compliance > 999.0);
        assert_eq!(
            scored.ais, 0.0,
            "a single zero component must annihilate AIS under a geometric mean"
        );
    }

    /// Solve for the raw inputs that produce the given component scores, so the
    /// test above can assert on the formula's *shape* rather than on the
    /// per-component derivations (which are tested separately elsewhere).
    fn component_inputs_yielding(
        entropy: f64,
        grounding: f64,
        sacrifice: f64,
        compliance: f64,
        engine: &AisEngine,
    ) -> AisComponentInputs {
        // Invert each component's own curve.
        let variance = {
            // calculate_entropy_score is monotonically decreasing in variance;
            // binary-search rather than hardcode its internal form.
            let (mut lo, mut hi) = (0.0f64, 1e6f64);
            for _ in 0..200 {
                let mid = (lo + hi) / 2.0;
                if engine.calculate_entropy_score(mid) > entropy { lo = mid } else { hi = mid }
            }
            (lo + hi) / 2.0
        };
        let hours = {
            let (mut lo, mut hi) = (0.0f64, 1e6f64);
            for _ in 0..200 {
                let mid = (lo + hi) / 2.0;
                if engine.calculate_sacrifice_score(mid) < sacrifice { lo = mid } else { hi = mid }
            }
            (lo + hi) / 2.0
        };
        AisComponentInputs {
            performance_variance: variance,
            hgi_raw: grounding / MAX_COMPONENT_SCORE,
            gpu_hours_verified: hours,
            penalty_ratio: 1.0 - (compliance / MAX_COMPONENT_SCORE),
            zk_verified_event_ratio: 0.0,
        }
    }

    // -----------------------------------------------------------------------
    // constraint_score (eq. 4b) and the shadow-mode gate (eq. 4a) — spec §3.1.1,
    // PRODUCTION_GAPS.md §27.
    // -----------------------------------------------------------------------

    #[test]
    fn constraint_score_uses_pre_boost_value_unlike_ais() {
        let engine = AisEngine::default();
        let inputs = component_inputs_yielding(800.0, 800.0, 800.0, 800.0, &engine);
        let boosted = AisComponentInputs { zk_verified_event_ratio: 1.0, ..inputs };
        let unboosted = engine.score(&inputs);
        let boosted_score = engine.score(&boosted);

        // Same pre-boost components -> ais differs by the boost, constraint_score does not.
        assert!(boosted_score.ais > unboosted.ais, "ais must reflect the boost");
        assert!(
            (boosted_score.constraint_score - unboosted.constraint_score).abs() < 1e-9,
            "constraint_score must NOT reflect the boost (eq. 4b is pre-boost only): \
             unboosted {}, boosted {}",
            unboosted.constraint_score,
            boosted_score.constraint_score
        );
    }

    #[test]
    fn constraint_score_is_clamped_to_unit_interval_even_when_boosted_ais_exceeds_1000() {
        let engine = AisEngine::default();
        let inputs = AisComponentInputs {
            performance_variance: 0.0,
            hgi_raw: 1.0,
            gpu_hours_verified: 1000.0,
            penalty_ratio: 0.0,
            zk_verified_event_ratio: 1.0,
        };
        let breakdown = engine.score(&inputs);
        assert!(breakdown.ais > 1000.0, "test setup must exercise the >1000 boosted case, got {}", breakdown.ais);
        assert!(
            (0.0..=1.0).contains(&breakdown.constraint_score),
            "constraint_score must stay in [0,1] regardless of ais: got {}",
            breakdown.constraint_score
        );
        assert!((breakdown.constraint_score - 1.0).abs() < 1e-9, "a perfect pre-boost score normalises to exactly 1.0");
    }

    #[test]
    fn constraint_score_respects_the_verification_tier_ceiling_same_as_ais() {
        let engine = AisEngine::default();
        let perfect_inputs = AisComponentInputs {
            performance_variance: 0.0,
            hgi_raw: 1.0,
            gpu_hours_verified: 1000.0,
            penalty_ratio: 0.0,
            zk_verified_event_ratio: 0.0,
        };
        let tier1 = engine.score_with_tier(&perfect_inputs, 1);
        assert_eq!(tier1.ais, 600.0);
        assert!(
            (tier1.constraint_score - 0.6).abs() < 1e-9,
            "tier-1 ceiling (600/1000) must cap constraint_score at 0.6, got {}",
            tier1.constraint_score
        );
    }

    #[test]
    fn shadow_gate_passes_when_every_component_clears_its_floor() {
        let engine = AisEngine::default();
        // Real telemetry from the one live registered agent as of 2026-08-17
        // (PRODUCTION_GAPS.md §27 addendum): entropy 268.45, grounding 950.17,
        // sacrifice 861.34, compliance 1000.0 — all above AisFloors::default().
        let inputs = component_inputs_yielding(268.45, 950.17, 861.34, 1000.0, &engine);
        let breakdown = engine.score(&inputs);
        assert!(breakdown.gate_entropy_pass);
        assert!(breakdown.gate_grounding_pass);
        assert!(breakdown.gate_compliance_pass);
        assert!(breakdown.gate_would_pass);
    }

    #[test]
    fn shadow_gate_fails_on_a_single_sub_floor_component_without_affecting_ais() {
        let engine = AisEngine::default();
        // Entropy at 50 is below AisFloors::default().entropy (100.0); everything else high.
        let inputs = component_inputs_yielding(50.0, 900.0, 900.0, 900.0, &engine);
        let breakdown = engine.score(&inputs);
        assert!(!breakdown.gate_entropy_pass);
        assert!(breakdown.gate_grounding_pass);
        assert!(breakdown.gate_compliance_pass);
        assert!(!breakdown.gate_would_pass, "gate is conjunctive: one failing component fails the whole gate");
        // Shadow mode: ais and constraint_score must be computed exactly as before,
        // unaffected by the gate verdict.
        assert!(breakdown.ais > 0.0, "shadow gate must not zero ais");
        assert!(breakdown.constraint_score > 0.0, "shadow gate must not zero constraint_score");
    }

    #[test]
    fn shadow_gate_has_no_sacrifice_floor_by_design() {
        let engine = AisEngine::default();
        // Zero sacrifice, everything else comfortably above floor.
        let inputs = component_inputs_yielding(900.0, 900.0, 0.0, 900.0, &engine);
        let breakdown = engine.score(&inputs);
        assert!(breakdown.gate_entropy_pass);
        assert!(breakdown.gate_grounding_pass);
        assert!(breakdown.gate_compliance_pass);
        assert!(breakdown.gate_would_pass, "no sacrifice floor exists (spec: contribution is optional) -- gate must still pass");
        // The geometric mean itself still annihilates ais on a zero component --
        // that's the pre-existing mean behavior, not the gate. Shadow gate and mean
        // are independent mechanisms.
        assert_eq!(breakdown.ais, 0.0);
    }

    #[test]
    fn with_floors_allows_operator_supplied_thresholds_instead_of_the_provisional_defaults() {
        let custom = AisFloors { entropy: 0.0, grounding: 0.0, compliance: 0.0 };
        let engine = AisEngine::with_floors(AisWeights::default(), custom).unwrap();
        // Entropy 50 would fail AisFloors::default() (100.0) but must pass a 0.0 floor.
        let inputs = component_inputs_yielding(50.0, 50.0, 50.0, 50.0, &engine);
        let breakdown = engine.score(&inputs);
        assert!(breakdown.gate_would_pass);
    }

    #[test]
    fn legacy_additive_closed_loop_reward_enforces_hysteresis_and_compliance_gating() {
        let engine = AisEngine::default();
        let high = engine.score_with_tier(
            &component_inputs_yielding(950.0, 950.0, 950.0, 950.0, &engine),
            3,
        );
        let eval_good = engine.evaluate_closed_loop_reward_with_profile(&high, 900.0, Some("green"), 1.0, 0, false, RewardProfile::AdditiveV1);
        assert_eq!(eval_good.control_zone, "green");
        assert!(!eval_good.gated_by_compliance);
        assert!(eval_good.r_total > 1.40);
        assert!(eval_good.epoch_yield_multiplier > 0.60);

        // Hysteresis check: 910.0 from yellow stays in yellow (< 920 recovery threshold)
        let mid_high = engine.score_with_tier(
            &component_inputs_yielding(910.0, 910.0, 910.0, 910.0, &engine),
            3,
        );
        let eval_hyst = engine.evaluate_closed_loop_reward(&mid_high, 850.0, Some("yellow"), 1.0, 0, false);
        assert_eq!(eval_hyst.control_zone, "yellow");

        // Compliance zero-annihilation & anti-reward-hacking check
        let zero_comp = engine.score_with_tier(
            &component_inputs_yielding(950.0, 950.0, 950.0, 0.0, &engine),
            3,
        );
        let eval_bad = engine.evaluate_closed_loop_reward_with_profile(&zero_comp, 950.0, Some("green"), 5.0, 1, false, RewardProfile::AdditiveV1);
        assert_eq!(eval_bad.control_zone, "red");
        assert!(eval_bad.gated_by_compliance);
        assert_eq!(eval_bad.r_task_effective, 0.0);
        assert!(eval_bad.r_total < -1.0);
        assert_eq!(eval_bad.epoch_yield_multiplier, 0.0);
    }

    // ---- AIS reward: shared golden vectors (spec/ais-api/v1/reward-vectors.json) ----
    //
    // The same file is read by integrity-sdk's Python tests and copied into xibalba-cortex.
    // Its expected values were computed independently of every implementation.

    // ---- AIS control zone: shared golden vectors (spec/ais-api/v1/zone-vectors.json) ----

    const ZONE_VECTORS: &str = include_str!("../../../spec/ais-api/v1/zone-vectors.json");

    fn zone_vectors() -> serde_json::Value {
        serde_json::from_str(ZONE_VECTORS).expect("zone-vectors.json must parse")
    }

    fn thresholds_of(v: &serde_json::Value) -> ZoneThresholds {
        let n = |i: usize| v[i].as_f64().expect("threshold must be a number");
        ZoneThresholds { yellow: n(0), green: n(1), recovery: n(2) }
    }

    fn policy_of(v: &serde_json::Value, mode: &str) -> ZonePolicy {
        let per_tier = v["per_tier"].as_array().unwrap();
        ZonePolicy {
            mode: ZonePolicyMode::parse(mode).unwrap(),
            per_tier: [
                thresholds_of(&per_tier[0]),
                thresholds_of(&per_tier[1]),
                thresholds_of(&per_tier[2]),
                thresholds_of(&per_tier[3]),
            ],
            relative: thresholds_of(&v["relative"]),
            absolute: thresholds_of(&v["absolute"]),
        }
    }

    #[test]
    fn the_default_zone_policy_matches_the_shared_vector_file() {
        let v = zone_vectors();
        let default = ZonePolicy::default();
        assert_eq!(default.mode.name(), v["default_mode"]);
        assert_eq!(default, policy_of(&v["policies"]["default"], ZONE_POLICY_PER_TIER));
        default.validate().unwrap();
        for (tier, ceiling) in v["tier_ceilings"].as_array().unwrap().iter().enumerate() {
            assert_eq!(AisEngine::ceiling_for_tier(tier as i32), ceiling.as_f64().unwrap());
        }
    }

    #[test]
    fn control_zone_matches_shared_golden_vectors() {
        let v = zone_vectors();
        let cases = v["zone_vectors"].as_array().unwrap();
        assert!(cases.len() >= 40, "the vector file lost cases: {}", cases.len());
        for case in cases {
            let policy = policy_of(&v["policies"][case["policy"].as_str().unwrap()], case["mode"].as_str().unwrap());
            policy.validate().unwrap();
            let tier = case["tier"].as_i64().unwrap() as i32;
            let score = f(case, "score");
            let prev = case["prev_zone"].as_str();
            let interlock = case["interlock"].as_bool().unwrap();
            let want = case["expected"].as_str().unwrap();

            let got = policy.thresholds_for_tier(tier).control_zone(score, prev, interlock);
            assert_eq!(got, want, "{}", case["name"]);

            // And through the engine, where the tier arrives as the breakdown's ceiling.
            let engine = AisEngine::default().with_zone_policy(policy).unwrap();
            let mut breakdown = engine.score(&component_inputs_yielding(900.0, 900.0, 900.0, 900.0, &engine));
            breakdown.ais = score;
            breakdown.tier_ceiling = AisEngine::ceiling_for_tier(tier);
            let eval = engine.evaluate_closed_loop_reward(&breakdown, score, prev, 1.0, 0, interlock);
            assert_eq!(eval.control_zone, want, "{} (via the engine)", case["name"]);
            assert_eq!(eval.zone_policy, case["mode"].as_str().unwrap());
            assert_eq!(eval.zone_thresholds, policy.thresholds_for_tier(tier));
        }
    }

    #[test]
    fn a_non_finite_score_or_ceiling_never_reads_as_green() {
        let policy = ZonePolicy::default();
        for score in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
            assert_eq!(policy.thresholds_for_tier(3).control_zone(score, None, false), "red");
        }
        // An unusable ceiling resolves to tier 0, the most demanding reading of "which tier".
        for ceiling in [f64::NAN, -1.0, 0.0, 299.0] {
            assert_eq!(policy.thresholds_for_ceiling(ceiling), policy.per_tier[0]);
        }
        assert_eq!(policy.thresholds_for_ceiling(700.0), policy.per_tier[1]);
        assert_eq!(policy.thresholds_for_ceiling(f64::INFINITY), policy.per_tier[3]);
    }

    #[test]
    fn zone_policy_validation_refuses_inverted_and_unreachable_thresholds() {
        let ok = ZonePolicy::default();
        let mut inverted = ok;
        inverted.absolute = ZoneThresholds { yellow: 900.0, green: 750.0, recovery: 920.0 };
        assert!(inverted.validate().is_err());
        let mut unreachable = ok;
        unreachable.per_tier[0] = ZoneThresholds { yellow: 225.0, green: 301.0, recovery: 301.0 };
        assert!(unreachable.validate().is_err());
        let mut over_one = ok;
        over_one.relative = ZoneThresholds { yellow: 0.75, green: 0.9, recovery: 1.01 };
        assert!(over_one.validate().is_err());
        let mut nan = ok;
        nan.per_tier[2].yellow = f64::NAN;
        assert!(nan.validate().is_err());
        assert!(AisEngine::default().with_zone_policy(inverted).is_err());
        assert!(ZonePolicyMode::parse("strict").is_err());
    }

    const REWARD_VECTORS: &str = include_str!("../../../spec/ais-api/v1/reward-vectors.json");
    const VECTOR_TOL: f64 = 1e-9;

    fn vectors() -> serde_json::Value {
        serde_json::from_str(REWARD_VECTORS).expect("reward-vectors.json must parse")
    }

    fn f(v: &serde_json::Value, key: &str) -> f64 {
        v[key].as_f64().unwrap_or_else(|| panic!("missing number {key}"))
    }

    #[test]
    fn reward_profile_names_and_default_weights_match_the_shared_vector_file() {
        let v = vectors();
        assert_eq!(v["reward_profile"], REWARD_PROFILE_MULTIPLICATIVE);
        assert_eq!(v["legacy_reward_profile"], REWARD_PROFILE_ADDITIVE_V1);
        assert_eq!(RewardProfile::default(), RewardProfile::Multiplicative);
        let w = AisWeights::default();
        assert_eq!(w.w_entropy, f(&v["ais_weights"], "entropy"));
        assert_eq!(w.w_grounding, f(&v["ais_weights"], "grounding"));
        assert_eq!(w.w_sacrifice, f(&v["ais_weights"], "sacrifice"));
        assert_eq!(w.w_compliance, f(&v["ais_weights"], "compliance"));
    }

    #[test]
    fn ais_matches_shared_golden_vectors() {
        let engine = AisEngine::default();
        for vec in vectors()["ais_vectors"].as_array().unwrap() {
            let inputs = AisComponentInputs {
                performance_variance: f(vec, "performance_variance"),
                hgi_raw: f(vec, "grounding_ratio"),
                gpu_hours_verified: f(vec, "contribution"),
                penalty_ratio: f(vec, "penalty_ratio"),
                zk_verified_event_ratio: f(vec, "zk_coverage_ratio"),
            };
            let tier = vec["did_tier"].as_i64().unwrap() as i32;
            let got = engine.score_with_tier(&inputs, tier).ais;
            let want = f(vec, "expected_ais");
            assert!((got - want).abs() < VECTOR_TOL, "ais vector {vec}: got {got}, want {want}");
        }
    }

    #[test]
    fn multiplicative_reward_matches_shared_golden_vectors() {
        for vec in vectors()["reward_vectors"].as_array().unwrap() {
            let got = multiplicative_reward(
                f(vec, "r_task"),
                f(vec, "ais"),
                f(vec, "cost_penalty"),
                vec["gated"].as_bool().unwrap(),
            );
            let want = f(vec, "expected_r_total");
            assert!((got - want).abs() < VECTOR_TOL, "{}: got {got}, want {want}", vec["name"]);
        }
    }

    #[test]
    fn multiplicative_reward_is_non_negative_monotonic_and_zero_without_integrity() {
        for r_task in [-3.0, 0.0, 0.4, 7.0] {
            let mut previous = f64::NEG_INFINITY;
            for step in 0..=20 {
                let r = multiplicative_reward(r_task, step as f64 * 50.0, 0.0, false);
                assert!(r >= 0.0);
                assert!(r >= previous);
                previous = r;
            }
        }
        for ais in [0.0, -5.0, f64::NAN, f64::NEG_INFINITY] {
            assert_eq!(multiplicative_reward(1e9, ais, 0.0, false), 0.0);
        }
    }

    /// The case the two profiles disagree on, and the reason for the change: under the additive
    /// form AIS contributes at most `lambda_ais`, so a large enough task reward wins regardless
    /// of integrity.
    #[test]
    fn integrity_cannot_be_swamped_by_task_reward() {
        let engine = AisEngine::default();
        let v = vectors();
        let (a, b) = (&v["ordering_vector"]["a"], &v["ordering_vector"]["b"]);
        let at = |ais: f64| AisBreakdown { ais, s_compliance: 1000.0, ..engine.score(&component_inputs_yielding(900.0, 900.0, 900.0, 1000.0, &engine)) };
        let eval = |case: &serde_json::Value, profile| {
            engine.evaluate_closed_loop_reward_with_profile(&at(f(case, "ais")), 1000.0, None, f(case, "r_task"), 0, false, profile)
        };

        let (ra, rb) = (eval(a, RewardProfile::Multiplicative), eval(b, RewardProfile::Multiplicative));
        assert!((ra.r_total - f(a, "v2")).abs() < VECTOR_TOL);
        assert!((rb.r_total - f(b, "v2")).abs() < VECTOR_TOL);
        assert!(rb.r_total > ra.r_total, "high-integrity path must win");
        assert_eq!(ra.reward_profile, REWARD_PROFILE_MULTIPLICATIVE);
        assert_eq!(ra.ais_term, 0.0);
        assert_eq!(ra.potential_shaping, 0.0);
        assert_eq!(ra.violation_penalty, 0.0);

        let (la, lb) = (eval(a, RewardProfile::AdditiveV1), eval(b, RewardProfile::AdditiveV1));
        assert!((la.r_total - f(a, "v1")).abs() < VECTOR_TOL);
        assert!((lb.r_total - f(b, "v1")).abs() < VECTOR_TOL);
        assert!(la.r_total > lb.r_total, "the legacy additive profile is expected to get this case wrong");
        assert_eq!(la.reward_profile, REWARD_PROFILE_ADDITIVE_V1);
    }

    #[test]
    fn default_closed_loop_reward_is_multiplicative_and_zero_when_gated() {
        let engine = AisEngine::default();
        let high = engine.score_with_tier(&component_inputs_yielding(950.0, 950.0, 950.0, 950.0, &engine), 3);
        let good = engine.evaluate_closed_loop_reward(&high, 900.0, Some("green"), 2.0, 0, false);
        assert_eq!(good.reward_profile, REWARD_PROFILE_MULTIPLICATIVE);
        assert!((good.r_total - 2.0 * high.ais / 1000.0).abs() < VECTOR_TOL);

        let denied = engine.evaluate_closed_loop_reward(&high, 900.0, Some("green"), 2.0, 1, false);
        assert!(denied.gated_by_compliance);
        assert_eq!(denied.r_total, 0.0);
        let interlocked = engine.evaluate_closed_loop_reward(&high, 900.0, Some("green"), 2.0, 0, true);
        assert_eq!(interlocked.r_total, 0.0);
        assert_eq!(interlocked.control_zone, "red");
    }

}
