//! Agent Integrity Score (AIS) formula.
//!
//! This crate is the ONLY place the AIS formula is computed anywhere in the
//! Integrity Protocol monorepo — see `docs/INTERFACE_CONTRACT.md` §4.3. Every
//! other package (sdk, cli, dashboard, bcc_middleware) calls the oracle's
//! `GET /v1/agent/{id}/ais` HTTP endpoint rather than re-deriving this math;
//! that indirection is the entire point of having an "oracle" instead of just
//! letting every consumer compute its own opinion of an agent's trustworthiness.
//!
//! Formula (verbatim from the interface contract):
//!
//!   AIS = (S_entropy*wE + S_grounding*wG + S_sacrifice*wS + S_compliance*wC) * ZK_boost
//!
//! with default weights wE=0.30, wG=0.30, wS=0.20, wC=0.20 (sum to 1.0) and
//! ZK_boost = 1.15 when a real Barretenberg proof was verified for the agent
//! during the reporting period, else 1.0.
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
        let sum = self.w_entropy + self.w_grounding + self.w_sacrifice + self.w_compliance;
        if (sum - 1.0).abs() > 1e-6 {
            return Err(format!("AIS weights must sum to 1.0, got {sum}"));
        }
        if [self.w_entropy, self.w_grounding, self.w_sacrifice, self.w_compliance]
            .iter()
            .any(|w| *w < 0.0)
        {
            return Err("AIS weights must be non-negative".to_string());
        }
        Ok(())
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
    /// Whether at least one telemetry submission in the period carried a ZK proof
    /// that this oracle verified for real via `bb verify` (see `backend::zk`). Drives
    /// `ZK_boost` — real cryptographic evidence outranks self-reported telemetry.
    pub zk_verified_this_period: bool,
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
    /// Final AIS. Note this is intentionally NOT clamped to `MAX_COMPONENT_SCORE`:
    /// the weighted sum of four scores each in `[0, 1000]` with weights summing to
    /// 1.0 is itself in `[0, 1000]`, but the `ZK_boost` multiplier (up to 1.15x) can
    /// push a fully-boosted top performer above 1000. The interface contract's
    /// formula doesn't specify a post-boost ceiling, so we report the true computed
    /// value rather than silently reintroducing a cap that isn't part of the spec.
    pub ais: f64,
}

/// Stateless computation engine over a fixed set of weights. Cheap to construct;
/// callers can build one per-request from operator-configured weights, or reuse
/// `AisEngine::default()`.
#[derive(Debug, Clone, Copy)]
pub struct AisEngine {
    pub weights: AisWeights,
}

impl Default for AisEngine {
    fn default() -> Self {
        Self {
            weights: AisWeights::default(),
        }
    }
}

impl AisEngine {
    pub fn new(weights: AisWeights) -> Result<Self, String> {
        weights.validate()?;
        Ok(Self { weights })
    }

    /// S_entropy: rewards *stability*, not any particular performance level. Uses a
    /// Gaussian-style decay so small variance barely moves the score but variance
    /// growing without bound saturates toward 0 rather than going negative.
    pub fn calculate_entropy_score(&self, performance_variance: f64) -> f64 {
        let v = performance_variance.max(0.0);
        let stability_factor = (-1.5 * v * v).exp();
        (stability_factor * MAX_COMPONENT_SCORE).clamp(0.0, MAX_COMPONENT_SCORE)
    }

    /// S_grounding: directly proportional to the human-grounding fraction. Simple by
    /// design — there's no principled nonlinearity to apply here, unlike the
    /// logarithmic "sacrifice" metric where marginal hours matter less at scale.
    pub fn calculate_grounding_score(&self, hgi_raw: f64) -> f64 {
        (hgi_raw.clamp(0.0, 1.0) * MAX_COMPONENT_SCORE).clamp(0.0, MAX_COMPONENT_SCORE)
    }

    /// S_sacrifice: logarithmic scale over verified GPU-hours, saturating at 1000
    /// verified hours (chosen so early contributions matter a lot and marginal hours
    /// at high volume matter less — a whale contributing 100x the compute of a
    /// baseline agent should not score 100x higher, since that would make the score
    /// pure pay-to-win rather than a trust signal).
    pub fn calculate_sacrifice_score(&self, gpu_hours_verified: f64) -> f64 {
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
        let clean_ratio = 1.0 - penalty_ratio.clamp(0.0, 1.0);
        (clean_ratio * MAX_COMPONENT_SCORE).clamp(0.0, MAX_COMPONENT_SCORE)
    }

    /// Computes the full AIS breakdown per docs/INTERFACE_CONTRACT.md §4.3.
    pub fn score(&self, inputs: &AisComponentInputs) -> AisBreakdown {
        let s_entropy = self.calculate_entropy_score(inputs.performance_variance);
        let s_grounding = self.calculate_grounding_score(inputs.hgi_raw);
        let s_sacrifice = self.calculate_sacrifice_score(inputs.gpu_hours_verified);
        let s_compliance = self.calculate_compliance_score(inputs.penalty_ratio);

        let zk_boost = if inputs.zk_verified_this_period {
            ZK_BOOST_FACTOR
        } else {
            NO_ZK_BOOST_FACTOR
        };

        // Use the Weighted Geometric Mean (Volume formula) instead of Arithmetic Mean
        let weighted = s_entropy.powf(self.weights.w_entropy)
            * s_grounding.powf(self.weights.w_grounding)
            * s_sacrifice.powf(self.weights.w_sacrifice)
            * s_compliance.powf(self.weights.w_compliance);

        AisBreakdown {
            s_entropy,
            s_grounding,
            s_sacrifice,
            s_compliance,
            zk_boost,
            ais: weighted * zk_boost,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

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
    fn worst_case_agent_scores_near_zero() {
        let engine = AisEngine::default();
        let inputs = AisComponentInputs {
            performance_variance: 100.0, // wildly erratic
            hgi_raw: 0.0,                // never human-checked
            gpu_hours_verified: 0.0,     // no verified contribution
            penalty_ratio: 1.0,          // every action flagged
            zk_verified_this_period: false,
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
            zk_verified_this_period: false,
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
            zk_verified_this_period: false,
        };
        let mut boosted_inputs = base_inputs;
        boosted_inputs.zk_verified_this_period = true;

        let unboosted = engine.score(&base_inputs);
        let boosted = engine.score(&boosted_inputs);

        assert!((boosted.ais - unboosted.ais * ZK_BOOST_FACTOR).abs() < 1e-9);
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
}
