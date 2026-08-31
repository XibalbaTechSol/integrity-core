# Spec — open definitions

What remains to **define**, as distinct from what remains to **build**. Most `[PLANNED]`
markers in the spec are fully specified and merely unimplemented; the six below are places the
spec names something without saying what it is, so no implementation could be checked against
it.

**Retargeted 2026-08-31** from `spec/integrity-protocol-v0.4.md` (now archived,
non-normative — see `docs/SPEC.md` §16) to the current normative `docs/SPEC.md` v1.0.0-draft.
Gap 1 (scope algebra) below was re-verified against `docs/SPEC.md` §4.5 directly — the
`delegation_active` primitive family still names `scope`/`scope_hash` without defining it, so
the gap and proposal are unchanged. **Gaps 2–6 still cite `spec/integrity-protocol-v0.4.md`'s
section numbers and have NOT been re-verified against `docs/SPEC.md`'s restructured sections**
(trust tiers, AIS, and governance all moved and changed shape between the two documents) —
treat those five as needing a fresh look against `docs/SPEC.md` before acting on them, not as
current claims about §11 Trust tiers / §10 AIS / governance-over-primitives as it stands today.

Ordered by whether they block work already approved.

| # | Gap | Blocks | State |
|---|---|---|---|
| 1 | Scope algebra | **Authority generalization (approved)** | Proposed below |
| 2 | Undefined quantities | Minimum stake, lineage, silence-as-signal | Needs decisions |
| 3 | Verification ladder tiers 2–3 | Tier elevation | Undefined |
| 4 | ZK-boost binding | Mainnet blocker #1 | Shape known, binding undefined |
| 5 | AIS formula versioning | Interpreting historical scores | Undefined |
| 6 | Governance authority | Upgradeability decision | Undefined |

---

## 1. Scope algebra — proposed

### The problem

`docs/SPEC.md` §4.5's `delegation_active` primitive family defines a grant as
`(principal, agent, scope_hash) → {active, expires, meter}` and requires the hook to treat an
"out-of-scope grant" as `V = 0` — **and never defines what a scope is**, only an opaque hash of
one. It is a plain omission there, same as it was in the archived v0.4 §4.3 formalism
(`a ⊑ D.scope`) this proposal originally targeted.

The design note behind it goes further and makes the omission an inconsistency:
[`thesis-extensions-formal.md`](../archive/2026-08/thesis-extensions-formal.md) §1.1 calls scope "a
domain-specific capability set … the protocol treats it as opaque and only enforces
containment." Containment over an opaque value is undecidable — you cannot check `⊑` on
something you refuse to interpret.

Either way the consequence is the same: `[PLANNED]` items that depend on scope (§4.5's
kernel-level `(principal, agent, scope_hash)` view, IP-license packs distinguishing themselves
from `SmartBAA` by scope alone) cannot be implemented or verified against anything more precise
than `SmartBAA`'s own hard-coded PHI-class check.

### Proposal — typed capability tuples

A **scope** is a set of capabilities. A **capability** is a triple:

```
c = (action, resource, constraints)

action      : a dot-separated identifier, e.g. "phi.read", "market.enter", "tool.invoke"
resource    : a slash-separated path, e.g. "ce/0xABC…/patients", "market/*"
constraints : a map of named bounds, e.g. {max_value_wei: 10^18, before: 1793000000}
```

### Containment

An action `a = (action, resource, constraints)` is permitted by scope `S` iff some capability
in `S` covers it:

```
a ⊑ S   iff   ∃ c ∈ S :  action_covers(c.action, a.action)
                       ∧ resource_covers(c.resource, a.resource)
                       ∧ constraints_satisfied(c.constraints, a)
```

with

- **`action_covers`** — exact match, or `c.action` is a dot-prefix of `a.action` at a segment
  boundary. `phi` covers `phi.read`; `phi.re` does **not** cover `phi.read`.
- **`resource_covers`** — exact match, or `c.resource` ends in `/*` and is a segment-boundary
  path prefix. `ce/0xABC/*` covers `ce/0xABC/patients`, not `ce/0xABCD/patients`.
- **`constraints_satisfied`** — every named bound in `c` holds for `a`. A bound absent from `c`
  is unconstrained; a bound absent from `a` when `c` requires one **fails**. Silence must not
  satisfy a constraint, or omitting a field would widen authority.

Scope containment for subdelegation follows directly:

```
S' ⊑ S   iff   ∀ c' ∈ S' : c' ⊑ S
```

which is decidable in `O(|S'| · |S|)` with the primitive checks above.

### Deliberate exclusions, and why

- **No deny rules / negation.** Negation makes containment order-dependent and, combined with
  wildcards, generally undecidable. It also invites the classic failure where a subdelegation
  *widens* authority by removing a deny. Authority narrows monotonically or the algebra is not
  worth having.
- **No regular expressions.** Regex containment (is L(r₁) ⊆ L(r₂)?) is decidable but expensive
  and easy to get wrong, and regexes invite catastrophic backtracking in a gate on the hot
  path. Segment-boundary prefixes cover the real cases.
- **No arbitrary predicates.** A scope must be checkable by a third party reading the chain,
  not by executing code the delegator supplied.

The exclusions are what make A5 mechanically checkable rather than aspirational.

### It already fits Shield

`SmartBAA` becomes one capability, which is the test that the algebra describes reality rather
than an idealization:

```
scope = [ ("phi", "ce/<coveredEntity>/*", {}) ]
```

A BAA is a delegation whose scope is "everything PHI-shaped, for this covered entity,
unbounded in value." Generalizing does not change Shield's behavior; it names it.

### Open sub-question

Whether `scope` is stored on-chain (canonical, costly, publicly checkable) or committed to by
hash with the body off-chain (cheap, and consistent with how memory treats vault contents).
Hash-committed matches the protocol's existing posture — commitments on-chain, content
off-chain — but makes a third party unable to evaluate `⊑` without being given the body.
**Recommendation:** hash-committed with the body retrievable, since a counterparty who cannot
obtain the scope body should not be relying on the delegation anyway.

---

## 2. Quantities the spec names but never values

Each currently appears as a word with no number, and every one is a policy decision rather
than an engineering one:

| Quantity | Where | What must be decided |
|---|---|---|
| Minimum bonded stake | §4.2, §6 | Amount, denomination, and **who may change it** (fixed constant vs governance parameter) |
| Challenge window | §7.4 lineage, T3 termination | Duration. Used by two different mechanisms — they may or may not share a value, and the spec should say which |
| `reputation_policy: partial` cap | §7.4 | What fraction of predecessor standing transfers, and against what baseline |
| Silence-as-signal | §4.4, App A.7 | Expected reporting cadence, silence threshold relative to it, and the score effect. Note this interacts with termination: without T4, silence and retirement are indistinguishable |

A caution on the first: making minimum stake a governance parameter hands governance a lever
over who may register at all. That is a real authority question, not a tuning knob — see §6
below.

## 3. Verification ladder, tiers 2 and 3

§13 lists "DNS / social" and "TEE + audit" with AIS ceilings of 850 and 1000. Those are
labels. To be implementable the spec must state, per tier: what artifact proves the claim
(DNS TXT record format? which attestation document types — Nitro, SGX quote?), who verifies it,
how it expires, and how it is revoked. Tier 1 is the only tier presently specified enough to
build.

Until then the ladder is descriptive, which §13 now says — but a ceiling that is advertised
and unenforced is a claim the protocol does not keep.

## 4. ZK-boost binding

Appendix A.1 says "per-event / public inputs." That names the shape, not the binding. The spec
must state **which public input commits to what**: minimally, the proof's public inputs should
commit to the telemetry event (or window) it vouches for, so a proof for event A cannot boost
unrelated event B. Until that is written, "tighter binding" is not a specification anyone can
implement or review against.

## 5. AIS formula versioning

§2 calls AIS "versioned and replaceable," and §8.1 fixes the weights. Nothing defines:

- how a weight change is proposed and adopted,
- whether historical scores are recomputed or frozen under the weights of their epoch,
- how a consumer reading `GET /v1/agent/{id}/ais` knows which version produced a number.

For a protocol whose evidence is permanent and whose consumers may compare scores across time,
"replaceable" without a version discipline means scores from different eras are silently
incomparable. This is cheap to define now and expensive to retrofit.

## 6. Governance authority over primitives

`IntegrityGovernance` is deployed; §16 never states what it may change. The spec should
enumerate the boundary explicitly, because the natural reading — governance may change
anything it holds a role on — collides directly with §4's claim that primitives are the
agent's.

Concretely it must say whether governance may: change AIS weights; set the minimum stake; hold
a proxy/beacon upgrade authority over agent contracts (the open
[upgradeability decision](upgradeability-decision.md)); slash without dispute; or force a
lifecycle transition once termination exists.

**This is the same question as upgradeability wearing a different hat**, and answering it in
the spec would settle both.

---

## Suggested order

1. **Scope algebra** — unblocks the authority work already approved.
2. **Governance authority** — settles upgradeability at the same time.
3. **AIS versioning** — cheap now, expensive after mainnet.
4. **Quantities** — a set of decisions, not research.
5. **ZK-boost binding** — needed for mainnet blocker #1.
6. **Ladder tiers** — needed only when tier elevation is actually offered.
