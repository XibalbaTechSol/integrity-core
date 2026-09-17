# AIS mathematical specification — `ais/v1-geometric-1`

All component scores have codomain `[0,1000]`. The composite is dimensionless;
raw inputs retain their source units until normalized by the transfer function.
The Oracle is the only authoritative evaluator.

| Axis | Raw input/domain | Transfer function | Direction / saturation |
|---|---|---|---|
| Entropy/stability (v) | performance variance, `v >= 0` | `S_E = 1000 exp(-1.5 v^2)` | non-increasing; `v=0 -> 1000`, unbounded positive input tends to 0 |
| Grounding (h) | fraction, nominal `[0,1]` | `S_G = 1000 clamp(h,0,1)` | non-decreasing; zero is 0; above 1 saturates |
| Contribution (g) | hours-equivalent proxy, nominal `g >= 0` | `S_S = 1000 min(log10(g+1)/3,1)` | non-decreasing; zero is 0; 1000 hours saturates |
| Compliance (p) | flagged-event ratio, nominal `[0,1]` | `S_C = 1000(1-clamp(p,0,1))` | non-increasing; zero violations is 1000; all violations is 0 |

Negative raw values clamp to the safe endpoint. NaN and negative infinity fail
closed to zero. Positive infinity saturates only grounding/contribution because
those are bounded high-is-good inputs; it fails closed for stability,
compliance, and proof coverage. Missing evidence is zero. These rules make
malformed values deterministic across Rust and JSON consumers.

For validated weights `w >= 0`, `sum(w)=1`, the base score is evaluated in the
log domain:

```text
if any component == 0 and its weight > 0: AIS_base = 0
otherwise AIS_base = exp(sum(weight_i * ln(S_i)))
```

This is exactly the weighted geometric mean, not an arithmetic mean. The proof
coverage ratio is clamped to `[0,1]` after finite validation and gives
`ZK_boost = 1 + 0.15 ratio`. The boost is outside the pre-boost constraint
input. Final display AIS is post-boost and capped by the server-derived
identity ceiling: tier 0 = 300, tier 1 = 600, tier 2 = 850, tier 3+ = 1000.

The floor/conjunctive result is a shadow diagnostic under the active profile. It
is not an enforcement gate and must not be used to push scores, raise disputes,
or authorize actions until the proposed profile is accepted and calibrated.

## Required vectors

The implementation tests pin: all-zero annihilation; unequal-component
geometric-vs-arithmetic separation; zero/negative/large/non-finite transfer
inputs; exact boost ratios; tier ceilings; weight/floor validation; and distinct
base, post-boost, constraint, and final values. Cross-language consumers must
compare these values at the wire/display boundary without intermediate rounding.
