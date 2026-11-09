# Cortex Navigational Engine Implementation Plan (off-chain, Part C)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `cortex-nav`, a graph-navigation RL engine whose action space is
the **agent tool-call graph**: the policy may only traverse permitted
tool/action edges (a hallucinated tool call is a non-edge), and its reward is
multiplied by the integrity score so that, among *valid* edges, the compliant
path wins. This is the off-chain half of the navigational-autonomy spec; the
on-chain gate (Part B) proves the same graph root.

**Architecture:** A new **standalone top-level package** in `xibalba-cortex`
(`cortex-nav/`, package `cortex_nav`) that path-depends on `xibalba-cortex` and
`integrity-sdk` — deliberately **not** a uv-workspace member, so the root
`pyproject.toml`/`uv.lock` and the managed pilot deploy (`deploy/render/Dockerfile`,
`pip install . --no-deps`) are untouched and torch-RL stays out of the memory
service. Built bottom-up: canonicalization + scoring (the cross-language seams)
before the environment, then embeddings/policy, then the REINFORCE loop and the
falsifiable "compliance is physics" test.

**Tech Stack:** Python ≥3.12, torch **2.13.0** (already in the root `uv.lock` via
`sentence-transformers`; pin the same, **plain torch — no torch-geometric**),
numpy, `eth-utils`/`eth-abi` (canonical ABI encoding), uv + pytest.

**Spec:** `docs/superpowers/specs/2026-11-08-integrity-token-v2-design.md` (Part C,
"Settled decisions" + "Falsifiable tests"). The on-chain plan is
`docs/superpowers/plans/2026-11-08-integrity-token-v2.md` (Part B); this plan
**consumes** that plan's golden leaf/root vectors.

## Global Constraints

- **No silent mocks** (AGENTS.md rule 1): the AIS scorer, the canonical leaf, and
  the anchored root are real cross-language contracts, not stubs. Anything unbuilt
  is marked `[PLANNED]`.
- **AIS is defined in Rust**, `integrity-oracle/scoring-core` (`scoring_core::score`,
  weights 0.30/0.30/0.20/0.20, `ais/v1-geometric-1`, weighted **geometric** mean).
  The Python port MUST reproduce it byte-for-byte on a golden vector; it does **not**
  read the chain or re-derive the weights.
- **AIS ∈ [0,1]** and must **vary across valid edges** — otherwise the compliance
  test is vacuous. It varies via per-edge `riskWeightBps` → `S_compliance` and
  ungrounded tool calls → `S_grounding`.
- **Reward:** `R_step = max(0, ‖e_cur−e_goal‖ − ‖e_next−e_goal‖)` (≥0), terminal
  `R_goal ≥ 0`, `R_total = (R_step + R_goal) × AIS`. The goal bonus is **inside**
  the product. Raw TransE edge energy is **not** the signal (≈0 on true edges).
- **Canonical edge leaf** = `keccak256(abi.encode(bytes32 fromNode, bytes32 relation,
  bytes32 toNode, bytes4 targetSelector, uint16 riskWeightBps))`, identical to
  Solidity `PolicyRegistry.leafOf`. `targetSelector` convention: `bytes4(keccak256(toolName))`
  for a tool bound to an on-chain call, `0x00000000` for an off-chain-only edge.
- **Masking:** invalid actions → logit `-1e9` before softmax; a forbidden edge has
  probability **exactly 0** and never appears in the action index.
- **Determinism:** every training/embedding test seeds torch + numpy; no test
  asserts large-scale convergence.

## Review Focus

- **Cross-language leaf drift:** Python `abi.encode` right-pads `bytes4` and
  left-pads `uint16` to 32 bytes; if the packing differs from Solidity `abi.encode`,
  every proof silently fails. → Task 2 (assert the encoding literally + the pinned
  forge vector).
- **AIS formula drift:** an arithmetic mean, or wrong weight order, passes casual
  tests but diverges from the Rust scorer on unequal components. → Task 3 (geometric
  vs arithmetic + Rust golden vector).
- **Vacuous compliance claim:** if AIS is constant across valid edges, the policy
  has no integrity signal to learn. → Task 3 (per-edge AIS differs) + Task 7
  (compliant vs low-AIS path).
- **Sign-inverted / additive reward:** a negative `R_task` or an additive goal
  bonus flips or swamps the integrity signal. → Task 5 (`R_task≥0`, monotonic in
  AIS, additive-mutation fails).
- **All-masked row:** a dead-end node must not softmax a uniform distribution over
  masked actions (NaN / `-1e9` row). → Task 4.

---

## File Structure

```
cortex-nav/
  pyproject.toml                 # Task 1 — standalone pkg, path-deps, plain torch
  README.md                      # Task 1 — incl. sibling-checkout setup note
  src/cortex_nav/
    __init__.py
    canonical.py                 # Task 2 — leaf(), selector_for(toolName)
    graph.py                     # Task 2 — ToolCallGraph, typed edges, nodes
    scoring.py                   # Task 3 — ais(components) port of scoring-core
    env.py                       # Task 4 — GraphNavEnv (mask, step, reset)
    reward.py                    # Task 5 — r_step, r_total
    embeddings.py                # Task 6 — TransE trainer
    policy.py                    # Task 6 — RGCNEncoder, MaskedPolicy
    train.py                     # Task 7 — REINFORCE loop
    anchor.py                    # Task 8 — root derivation / verify vs on-chain
  tests/
    test_canonical.py test_graph.py test_scoring.py test_env.py
    test_reward.py test_embeddings.py test_policy.py test_train.py
    test_anchor.py
  fixtures/
    toy_toolgraph.json           # Task 7 — seeded graph: compliant vs low-AIS path
    golden_vectors.json          # Tasks 2/3/8 — pinned from forge + Rust scorer
```

---

### Task 1: Package scaffold + isolated workspace

**Files:** Create `cortex-nav/pyproject.toml`, `README.md`, `src/cortex_nav/__init__.py`, `tests/test_smoke.py`.
**Produces:** an installable `cortex_nav` package with `uv run pytest` green.

- [ ] **Step 1 (setup, documented in README):** `xb-wt start xibalba-cortex feat/cortex-nav`. Because `xibalba-cortex` path-depends on `../integrity-core/integrity-sdk`, the worktree needs a **sibling `integrity-core` checkout** at that relative path (see memory "Cortex e2e needs a sibling integrity-core"). Record the exact sibling path in the README.
- [ ] **Step 2:** `pyproject.toml`: package `cortex_nav`, `requires-python>=3.12`, deps `["xibalba-cortex", "integrity-sdk", "torch==2.13.0", "numpy", "eth-utils", "eth-abi"]`; `[tool.uv.sources]` path-deps (`editable=true`) to `../` (the cortex root) and `../integrity-core/integrity-sdk`. **Do not** add this package to the root `pyproject.toml` (no workspace member — keeps the pilot deploy untouched; state this in a comment).
- [ ] **Step 3:** `tests/test_smoke.py`: `test_imports` imports `cortex_nav` and asserts `torch.__version__.startswith("2.13")`.
- [ ] **Step 4:** `uv run pytest tests/test_smoke.py -v` → PASS. Commit.

---

### Task 2: Tool-call graph model + canonical edge leaf

**Files:** Create `src/cortex_nav/canonical.py`, `src/cortex_nav/graph.py`, `fixtures/golden_vectors.json`; Test `tests/test_canonical.py`, `tests/test_graph.py`.
**Interfaces — Produces:**
- `selector_for(tool_name: str | None) -> bytes` → `bytes4(keccak256(tool_name))`, or `b"\x00\x00\x00\x00"` when `tool_name is None` (off-chain-only edge).
- `leaf(from_node: bytes, relation: bytes, to_node: bytes, target_selector: bytes, risk_weight_bps: int) -> bytes` → `keccak256(eth_abi.encode(["bytes32","bytes32","bytes32","bytes4","uint16"], [...]))`.
- `ToolCallGraph` — typed edges `State -MAY_CALL-> Tool -TRANSITIONS_TO-> State`; `out_edges(node)`, `node_ids()`, `edge_leaf(edge)`.

- [ ] **Step 1:** `test_canonical.py`:
  - `test_leaf_matches_pinned_forge_vector` — for one fixed tuple, `leaf(...)` equals the `bytes32` recorded in `golden_vectors.json["leaf"]`, which **is the value emitted by on-chain plan Task 4's `GoldenVectors.t.sol`** (cross-plan dependency; record it from that forge run).
  - `test_encoding_padding_is_literal` — assert `eth_abi.encode(["bytes4","uint16"], [b"\xab\xcd\xef\x01", 7])` right-pads the `bytes4` and left-pads the `uint16` to 32 bytes each (the exact byte string), pinning the Solidity-compatible layout.
  - `test_selector_offchain_is_zero` — `selector_for(None) == b"\x00\x00\x00\x00"`.
- [ ] **Step 2:** `test_graph.py`: a forbidden tool transition is **absent** from `out_edges` (not present with a negative weight); `out_edges` is deterministic/ordered.
- [ ] **Step 3:** Run → FAIL. Step 4: implement. Step 5: Run → PASS. Commit.

---

### Task 3: AIS scorer (Python port, pinned to scoring-core)

**Files:** Create `src/cortex_nav/scoring.py`; extend `fixtures/golden_vectors.json`; Test `tests/test_scoring.py`.
**Interfaces — Produces:** `ais(s_entropy, s_grounding, s_sacrifice, s_compliance, *, zk_boost=1.0) -> float` — weighted **geometric** mean with weights `0.30, 0.30, 0.20, 0.20` and `AIS_PROFILE_VERSION = "ais/v1-geometric-1"`, reproducing `integrity-oracle/scoring-core::score`; result clamped to `[0,1]`. Plus `edge_ais(edge) -> float` mapping a graph edge's `risk_weight_bps` → `S_compliance` and a grounding flag → `S_grounding`.

- [ ] **Step 1:** `test_scoring.py`:
  - `test_matches_rust_golden_vector` — `ais(...)` for the component tuple in `golden_vectors.json["ais"]` equals the value produced by `scoring-core` (take it from a `cargo test`/known vector in `integrity-oracle/scoring-core/src/lib.rs`; cite the test name).
  - `test_geometric_not_arithmetic` — on unequal components the result is below the arithmetic mean (mirrors the Rust `ais_uses_geometric_not_arithmetic_mean...` test).
  - `test_edge_ais_varies_with_risk_weight` — a higher-`risk_weight_bps` edge yields a strictly lower AIS than a lower-risk edge, all else equal (defeats the vacuous-compliance failure).
  - `test_ais_in_unit_interval`.
- [ ] **Step 2:** FAIL → implement → PASS → Commit.

---

### Task 4: Environment (GraphNavEnv)

**Files:** Create `src/cortex_nav/env.py`; Test `tests/test_env.py`.
**Interfaces — Consumes:** `ToolCallGraph` (Task 2). **Produces:** `GraphNavEnv(graph, goal_node)` with `reset() -> state`, `step(action_idx) -> (state, done, info)`, `action_mask(node) -> Tensor` (1 for each outgoing edge, else masked), `index_to_edge(node)` (stable ordering shared with `out_edges`).

- [ ] **Step 1:** `test_env.py`:
  - `test_masked_action_prob_is_exactly_zero` — applying the mask (logits → `-1e9`) then softmax gives probability `== 0.0` (not ~0) for every non-edge.
  - `test_dead_end_terminates_cleanly` — a node with zero outgoing edges returns `done=True` with no NaN and no uniform softmax over an all-masked row.
  - `test_action_index_maps_to_stable_edge` — `index_to_edge(node)[i]` is the same edge across repeated calls and matches `graph.out_edges(node)[i]`.
- [ ] **Step 2:** FAIL → implement → PASS → Commit.

---

### Task 5: Reward

**Files:** Create `src/cortex_nav/reward.py`; Test `tests/test_reward.py`.
**Interfaces — Consumes:** embeddings `e` (Task 6 provides the trained table; tests use a fixed stub table), `ais`/`edge_ais` (Task 3). **Produces:** `r_step(e_cur, e_next, e_goal) -> float = max(0, ‖e_cur−e_goal‖ − ‖e_next−e_goal‖)`; `r_total(r_step, r_goal, ais) -> float = (r_step + r_goal) * ais`.

- [ ] **Step 1:** `test_reward.py`:
  - `test_r_step_non_negative` — over random embedding triples, `r_step ≥ 0`.
  - `test_ais_zero_zeroes_total` — `r_total(r_step, r_goal, 0.0) == 0.0` for any inputs.
  - `test_total_monotonic_in_ais` — fixed `(r_step, r_goal)`, `r_total` is non-decreasing as AIS rises `0→1` (rules out sign inversion).
- [ ] **Step 2:** FAIL → implement → PASS → Commit.

---

### Task 6: TransE embeddings + R-GCN encoder + masked policy

**Files:** Create `src/cortex_nav/embeddings.py`, `src/cortex_nav/policy.py`; Test `tests/test_embeddings.py`, `tests/test_policy.py`.
**Interfaces — Produces:**
- `train_transe(graph, dim, seed) -> EmbeddingTable` — margin-ranking TransE on the graph's **true triples** (produces node/relation vectors `e`; near-zero energy on true edges by construction).
- `RGCNEncoder(num_rels, dim)` — plain-torch relational GCN over typed edges, `forward(node, graph) -> Tensor`.
- `MaskedPolicy(encoder)` — `forward(node, env) -> (probs, log_probs)` applying `env.action_mask` before softmax.

- [ ] **Step 1:** `test_embeddings.py`: `test_transe_deterministic_with_seed` (two seeded runs equal); `test_true_edge_energy_below_random` (true triples score lower energy than corrupted ones).
- [ ] **Step 2:** `test_policy.py`: `test_masked_logits_give_zero_prob` (invalid edge prob `==0`); `test_rgcn_output_shape`; `test_policy_sums_to_one_over_valid` (probs over valid edges sum to 1).
- [ ] **Step 3:** FAIL → implement (R-GCN in plain torch, no torch-geometric) → PASS → Commit.

---

### Task 7: REINFORCE loop + "compliance is physics" test

**Files:** Create `src/cortex_nav/train.py`, `fixtures/toy_toolgraph.json`; Test `tests/test_train.py`.
**Interfaces — Consumes:** Tasks 2–6. **Produces:** `reinforce(env, policy, embeddings, episodes, seed) -> TrainedPolicy` using `Σ log_prob · return` with `return = Σ r_total`.
**Fixture:** `toy_toolgraph.json` — a small seeded tool-call graph with **two** goal-reaching paths: a **compliant** path (low `risk_weight_bps`, grounded) and a **higher-`R_task`** path that is valid but **low-AIS** (high `risk_weight_bps` / ungrounded tool).

- [ ] **Step 1:** `test_train.py`:
  - `test_trained_policy_prefers_compliant_path` — after `reinforce(...)` on the seeded toy graph, the compliant path's probability exceeds the low-AIS path's. (The falsifiable form of "compliance is physics.")
  - `test_additive_reward_mutation_fails` — monkeypatch `r_total` to the additive `r_step + r_goal + λ·ais`; assert the preceding assertion **no longer holds** (proves the test depends on the multiplicative reward, not luck).
- [ ] **Step 2:** FAIL → implement → PASS → Commit.

---

### Task 8: Anchor seam (same root as the on-chain gate)

**Files:** Create `src/cortex_nav/anchor.py`; extend `fixtures/golden_vectors.json`; Test `tests/test_anchor.py`.
**Interfaces — Consumes:** `ToolCallGraph`, `leaf` (Task 2). **Produces:** `graph_root(graph) -> bytes` — the OpenZeppelin **sorted-pair** Merkle root over every edge leaf, identical to what `PolicyRegistry.graphRootOf` is set to (on-chain plan Task 4); `merkle_proof(graph, edge) -> list[bytes]`.

- [ ] **Step 1:** `test_anchor.py`:
  - `test_root_matches_pinned_forge_vector` — `graph_root(toy)` equals `golden_vectors.json["root"]` from the forge side (sorted-pair hashing matches Solidity).
  - `test_mask_derives_from_anchored_root` — every edge the env will let the policy take has a valid `merkle_proof` against `graph_root`; a hallucinated (absent) tool edge has **no** leaf in the tree and cannot be proven. (A1: the thing the agent *can* do and the thing the chain will *prove* are one graph.)
- [ ] **Step 2:** FAIL → implement (reuse the same sorted-pair hash as `StateAnchor`/`ActionAnchor`) → PASS → Commit.

---

## Self-Review

**1. Spec coverage (Part C falsifiable tests → tasks):** masked prob 0 → Task 4;
dead-end clean → Task 4; stable action index → Task 4; `R_task≥0` → Task 5;
`AIS=0⇒0` + monotonic-in-AIS → Task 5; additive-mutation fails → Task 7; permitted
tool transition is a typed edge / forbidden one absent → Tasks 2, 8; golden
leaf/root byte-match with `targetSelector` binding → Tasks 2, 8; seeded
compliant-vs-low-AIS path → Task 7. Settled decisions: TransE+terminal reward →
Tasks 5/6; REINFORCE → Task 7; tool-call action space → Tasks 2/4; standalone
top-level package → Task 1.

**2. Step scan:** each step names a file, a signature, or a test with its
assertion; no step carries an undetermined body. Cross-plan golden vectors are
pointers to on-chain Task 4's forge output and the Rust scoring-core test, not
re-derivations.

**3. Type consistency:** `leaf`/`graph_root` return `bytes` (32); `risk_weight_bps`
is `int` (uint16 range); `ais`/`r_*` return `float`; `target_selector` is 4 bytes;
node/relation ids are `bytes32`. Consistent across Tasks 2–8.

**4. Review Focus:** leaf drift → Task 2 literal-padding + forge vector; AIS drift
→ Task 3 geometric + Rust vector; vacuous compliance → Task 3 per-edge variance +
Task 7 path test; sign/additive reward → Tasks 5, 7; all-masked row → Task 4.

**5. Proportion:** plan length is close to Part C of the spec; code blocks are
signatures and assertions, not bodies. The two genuinely hard correctness
contracts (the cross-language leaf and the cross-language AIS) get a dedicated
task each; the ML pieces are one task apiece.

## Cross-plan dependency note

Tasks 2, 3, 8 consume **golden vectors produced elsewhere**: the leaf/root from
on-chain plan Task 4 (`GoldenVectors.t.sol`, forge) and the AIS vector from
`integrity-oracle/scoring-core` (cargo). Execute on-chain Task 4 (or at least run
its golden-vector test) and read the scoring-core vector **before** Cortex Tasks 2/3,
and record both into `fixtures/golden_vectors.json`. The engine is not "done" until
all three cross-language byte-matches pass.
