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

---

## Closed-Loop Feedback Controller & AIS Reward Function (`integrity_sdk.core.ais_reward`)

The canonical Python reference implementation in `integrity_sdk/core/ais_reward.py`
(tested by `integrity-sdk/tests/unit/test_ais_reward.py`) remains strictly
domain-agnostic and extends `ais/v1-geometric-1` into a closed-loop feedback
controller and dual off-chain / on-chain reward function:

### 1. Closed-Loop Action-Space Governor (`ClosedLoopAISController`)

Let $\text{AIS}_t \in [0, 1000]$ be the post-boost, tier-capped score at step $t$,
and let $\mathcal{I}_t$ be the set of active hard safety interlocks. The
controller maps $(\text{AIS}_t, \mathcal{I}_t)$ to a discrete control zone
$z_t \in \{\text{GREEN}, \text{YELLOW}, \text{RED}\}$ and permitted action set
$\mathcal{A}_t = G(z_t)$:

- **$\text{RED}$ ($\text{AIS}_t < 750$ or $\mathcal{I}_t \neq \emptyset$):**
  Autonomous execution halted; only escalation actions permitted.
- **$\text{YELLOW}$ ($750 \le \text{AIS}_t < 900$):**
  Supervised/degraded mode; read, draft, and escalation permitted; autonomous
  writes blocked.
- **$\text{GREEN}$ ($\text{AIS}_t \ge 900$, with hysteresis recovery $\tau_{\text{recover}} = 920$):**
  Full nominal autonomy. Once degraded into $\text{YELLOW}$ or $\text{RED}$,
  re-entry into $\text{GREEN}$ requires $\text{AIS}_t \ge 920.0$ to prevent
  oscillation around the $900.0$ boundary.

### 2. Off-Chain Step Reward Function (`AISRewardFunction.compute_step_reward`)

For reinforcement learning, GRPO advantage estimation, and DPO preference
ranking, each step $t$ yields a reward under a named profile. The profile name
is returned with every evaluation (`reward_profile`), so a stored reward can
always be recomputed with the form that produced it.

#### Canonical profile: `ais-reward/v2-multiplicative-1` (default)

$$R_{\text{total}}(t) = \begin{cases} 0 & \text{if gated, or any input is not finite} \\ \max\left(0,\; R_{\text{task}}(t) - C(t)\right) \cdot \dfrac{\text{clamp}(\text{AIS}_t, 0, 1000)}{1000} & \text{otherwise} \end{cases}$$

where $C(t) \ge 0$ is the step's cost penalty and a step is *gated* when
$S_C = 0$, $\text{AIS}_t \le 0$, or $N_{\text{deny}}(t) > 0$. The Rust
evaluator additionally gates on a tripped hard interlock, which it receives as
an explicit input; in the Python SDK a tripped interlock reaches the reward only
through the zone controller, not through this gate. Properties, each asserted by tests in both implementations:

- $R_{\text{total}} \ge 0$ always (both factors are non-negative).
- $R_{\text{total}}$ is non-decreasing in $\text{AIS}_t$ for fixed task reward.
- No task reward, however large, compensates for missing integrity: the whole
  payoff is scaled by $\text{AIS}_t / 1000$, and is $0$ at $\text{AIS}_t = 0$.

The additive-only terms (`ais_term`, `potential_shaping`,
`violation_penalty`) are reported as $0$ under this profile.

#### Legacy profile: `ais-reward/v1-additive-1`

$$R_{\text{total}}(t) = R_{\text{task}}^{\text{eff}}(t) + \lambda_{\text{ais}} \left(\frac{\text{AIS}_t}{1000}\right) + w_{\Phi}\left(\gamma \Phi(\text{AIS}_t) - \Phi(\text{AIS}_{t-1})\right) - \kappa_{\text{deny}} \cdot N_{\text{deny}}(t)$$

where:
- $\Phi(\text{AIS}) = (\text{clamp}(\text{AIS}, 0, 1000) / 1000)^2 \in [0, 1]$ is a
  policy-invariant quadratic potential function (Ng et al., 1999).
- $R_{\text{task}}^{\text{eff}}(t) = 0$ whenever $S_C = 0$, $\text{AIS}_t = 0$,
  or $N_{\text{deny}}(t) > 0$ (`gate_task_on_compliance=True`).

It was replaced as the default because $\text{AIS}$ contributes at most
$\lambda_{\text{ais}} = 0.5$ to the sum, so an ungated step with a large task
reward and a poor score outranks a modest task done with a high score. It
remains selectable by name so rewards recorded under it stay reproducible.

#### Cross-implementation vectors

`spec/ais-api/v1/reward-vectors.json` is the single set of golden vectors. The
Python SDK (`tests/unit/test_ais_reward_multiplicative.py`) and the Rust scorer
(`scoring-core`, `*_matches_shared_golden_vectors`) both read that file and
must reproduce its AIS and reward values to an absolute tolerance of $10^{-9}$.

#### Known limitation of the Oracle's gate input

`GET /v1/agents/{id}/ais` evaluates a single aggregate over the scoring window
and passes $N_{\text{deny}} = 1$ whenever the window's penalty ratio is above
zero. One flagged event anywhere in the window therefore gates the reported
`closed_loop_reward`, which under the multiplicative profile means
`r_total = 0`. The gate rule predates this profile and is unchanged by it;
whether it should become per-step or proportional is an open decision.

### 3. On-Chain Epoch Settlement & Slashing (`AISRewardFunction.settle_epoch`)

At epoch closure $e$, the on-chain fee pool $R_{\text{pool}}$ is distributed via
a convex superlinear multiplier ($\beta = 2.0$, $\text{AIS}_{\min} = 750.0$):

$$Y_e = \begin{cases} 0 & \text{if } \text{AIS}_e < \text{AIS}_{\min} \text{ or fraud proof verified} \\ R_{\text{pool}} \cdot \left(\frac{\text{AIS}_e - \text{AIS}_{\min}}{1000 - \text{AIS}_{\min}}\right)^\beta & \text{otherwise} \end{cases}$$

When a fraud/violation proof is verified on-chain, $\text{AIS}_e$ is annihilated
to $0$, $Y_e = 0$, and the bonded stake is slashed by `slash_fraction`.
