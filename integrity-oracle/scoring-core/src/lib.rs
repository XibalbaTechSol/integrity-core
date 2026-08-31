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

/// Stateless computation engine over a fixed set of weights. Cheap to construct;
/// callers can build one per-request from operator-configured weights, or reuse
/// `AisEngine::default()`.
#[derive(Debug, Clone, Copy)]
pub struct AisEngine {
    pub weights: AisWeights,
    /// Shadow-mode-only gate floors (see `AisFloors`'s own doc comment). Defaulted so
    /// every existing caller of `AisEngine::default()`/`new()` gets shadow observation for
    /// free without needing to opt in — it's purely additive reporting, not enforcement.
    pub floors: AisFloors,
}

impl Default for AisEngine {
    fn default() -> Self {
        Self {
            weights: AisWeights::default(),
            floors: AisFloors::default(),
        }
    }
}

impl AisEngine {
    pub fn new(weights: AisWeights) -> Result<Self, String> {
        weights.validate()?;
        Ok(Self {
            weights,
            floors: AisFloors::default(),
        })
    }

    /// Same as `new`, but with explicit (e.g. operator-configured or test-chosen) floors
    /// instead of `AisFloors::default()`'s provisional values.
    pub fn with_floors(weights: AisWeights, floors: AisFloors) -> Result<Self, String> {
        weights.validate()?;
        Ok(Self { weights, floors })
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
            ais: weighted * zk_boost,
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
    /// Tier 3 (Institutional TEE/Audit): 1000.0 (uncapped, ZK boost applies)
    pub fn ceiling_for_tier(verification_tier: i32) -> f64 {
        match verification_tier {
            0 => 300.0,
            1 => 600.0,
            2 => 850.0,
            _ => 1000.0,
        }
    }

    /// Computes the AIS breakdown and applies the Verification Ladder score ceiling.
    pub fn score_with_tier(&self, inputs: &AisComponentInputs, verification_tier: i32) -> AisBreakdown {
        let mut breakdown = self.score(inputs);
        let ceiling = Self::ceiling_for_tier(verification_tier);
        if verification_tier < 3 {
            breakdown.ais = breakdown.ais.min(ceiling);
            // Same ceiling, same rationale, expressed on constraint_score's [0,1] scale:
            // an agent's identity-assurance tier bounds its constraint input exactly as it
            // bounds its display score, so a low-tier agent can't use eq. 4b to reach a
            // reputation-parameterised bound its verification level hasn't earned.
            breakdown.constraint_score = breakdown.constraint_score.min(ceiling / MAX_COMPONENT_SCORE);
        }
        breakdown
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

    #[test]
    fn verification_ladder_tier_ceilings_enforced() {
        let engine = AisEngine::default();
        let perfect_inputs = AisComponentInputs {
            performance_variance: 0.0,
            hgi_raw: 1.0,
            gpu_hours_verified: 1000.0,
            penalty_ratio: 0.0,
            zk_verified_this_period: false,
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

        // Tier 3 (Institutional): uncapped (1000)
        let score_t3 = engine.score_with_tier(&perfect_inputs, 3);
        assert!((score_t3.ais - 1000.0).abs() < 1e-6);
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
            zk_verified_this_period: false,
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
            zk_verified_this_period: false,
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
        let boosted = AisComponentInputs { zk_verified_this_period: true, ..inputs };
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
            zk_verified_this_period: true,
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
            zk_verified_this_period: false,
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
}
