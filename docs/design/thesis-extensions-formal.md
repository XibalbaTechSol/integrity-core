# Closing the logic — formal treatment of authority, termination, and symmetry

Follows [`primitive-set-coherence.md`](primitive-set-coherence.md), which found the primitive
set complete with respect to §1's thesis but identified three clauses the thesis does not
make. This formalizes each: definition, invariants, mechanism mapping, and what adopting it
costs.

Notation: `P` principal, `A` agent, `D` delegation, `S` scope, `t` time, `⊑` "is contained
in". Invariants are labelled so they can be cited from the spec and from tests.

---

## 1. Authority

**Clause to add to §1:** *…acts only under a verifiable delegation of authority from a
principal, within a scope that agent cannot widen.*

### 1.1 Definition

A **delegation** is a signed tuple:

```
D = (principal, agent_did, scope, not_before, not_after, revocation_ref, sig_P)
```

`sig_P` is the principal's signature over the canonical encoding of the rest. `scope` is a
domain-specific capability set (§4.x verticals define their own; the protocol treats it as
opaque and only enforces containment).

An action `a` at time `t` is **authorized** iff:

```
∃ D : sig_P valid ∧ not_before ≤ t ≤ not_after ∧ ¬revoked(D, t) ∧ a ⊑ D.scope
```

### 1.2 Invariants

- **A1 — Attribution.** Every trust-affecting action is attributable to exactly one
  delegation chain rooted at a principal. An action with no chain is unauthorized, not
  merely unattributed.
- **A2 — Scope containment.** `a ⊑ D.scope`. The gate refuses anything outside it.
- **A3 — Non-authorship.** `A` cannot mint `D` for itself. Only `P`'s key produces `sig_P`.
  This is the same structural property that makes reputation meaningful: **the agent owns the
  contract but cannot author the content.**
- **A4 — Revocability.** `P` may revoke unilaterally; revocation is observable on-chain, and
  actions after it are invalid. Revocation must not require `A`'s cooperation.
- **A5 — Non-expanding subdelegation.** If `A` delegates to `A'`, then
  `D'.scope ⊑ D.scope` and `D'.not_after ≤ D.not_after`. Authority may narrow down a chain,
  never widen.

### 1.3 Mechanism — mostly built, in one vertical

**`SmartBAA` is already a delegation instrument.** It has a covered entity (`P`), a business
associate (`A`), `sign()`, `revoke()`, `raiseDispute()`/`arbitrate()`, and posted collateral.
That is A1, A3, A4 and consequence, implemented — just named for HIPAA rather than generally.

So authority is not a missing mechanism; it is a **missing generalization**. The protocol
already has the shape and applies it in one vertical.

Adopting the clause means: generalize `SmartBAA` to a domain-neutral `Delegation` (with the
BAA as a subtype carrying HIPAA-specific terms), and have `bcc_middleware` resolve the
delegation chain as part of the gate decision rather than accepting a claim.

**This closes `MAINNET_READINESS.md` item 8.** `covered_entity_address` is client-supplied
today precisely because there is no delegation lookup — with A1/A2 enforced, the field stops
being an assertion and becomes a resolution.

---

## 2. Termination

**Clause to add to §1:** *…and whose standing can be ended, without erasing what it did.*

### 2.1 Definition — lifecycle as a state machine

```
Unregistered ──register──▶ Active ──retire(self)────▶ Retired    (terminal)
                             │  ▲                  ▲
                             │  └──reinstate───┐   │
                             └──suspend(cause)─┴─revoke(cause)──▶ Revoked (terminal)
```

`Retired` is voluntary and blameless. `Revoked` is for cause, via the dispute path. Both are
absorbing: no transition leaves them.

### 2.2 Invariants

- **T1 — History is monotone.** Termination never deletes or invalidates anchored history.
  Every root that verified before still verifies after. Termination changes *standing*, not
  *record* — this is what distinguishes it from deletion and keeps it compatible with §3.1.
- **T2 — Finality.** In a terminal state, no new BCC commitments, telemetry, or score updates
  are accepted, and the DID is spent: it can never return to `Active` nor be re-registered.
- **T3 — Settlement.** `Active → Retired` requires no open disputes and passes a challenge
  window, after which remaining stake returns to the controller. Termination must not be an
  exit from accountability — otherwise it becomes the cheapest way to escape a pending slash.
- **T4 — Distinguishability.** `Retired` ≠ silent. A terminated agent is explicitly marked;
  an agent that merely stops reporting is a *liveness* signal, not a lifecycle state. Without
  T4 the two are indistinguishable, which is exactly the hole `silence-as-signal`
  (Appendix A gap 8) leaves open.
- **T5 — Authority to terminate.** Self-termination by the controller; `Revoked` only through
  governance-arbitrated dispute, never unilaterally by the protocol.

### 2.3 Mechanism — not built, and it collides with a known constraint

`XibalbaAgentRegistry.AgentRecord` carries `{primitives, controller, domainId, registeredAt,
exists}` — **no lifecycle state** — and the registry exposes `registerPrimitives` plus reads
only. There is no transition function at all.

Two consequences worth stating plainly:

1. **T2 needs registry mutability**, which the registry deliberately does not have. This is
   the same constraint the upgradeability decision ran into
   ([`upgradeability-decision.md`](upgradeability-decision.md)) and it should be settled in
   the same breath: whatever mechanism allows a status transition is the mechanism that would
   also allow a primitive rotation.
2. **T1 suggests a tombstone root.** The cleanest expression of "ended, not erased" is a final
   `StateAnchor` root committing to the terminal state — the agent's own last word, anchored
   by its own controller. That reuses the memory primitive rather than adding machinery.

---

## 3. Symmetry

**Ruling recommended: adopt as a generalization, not a new primitive.**

### 3.1 Definition

Reputation is currently modelled as an attribute of one agent, evaluated by an unspecified
observer. Formally it is a **relation over an interaction**.

An interaction between `A` and `B` is a pair of commitments over a shared intent:

```
I = (c_A, c_B),  c_X = BCC(agent=X, counterparty=Y, intent_hash=h, …)
```

with the same `h` on both sides, each signed by its own agent and anchored in its own vault.

### 3.2 Invariants

- **S1 — Universal verifiability.** `V(agent, evidence)` is evaluable by any party with chain
  access, without permission from the agent. *Already holds* — §3.2.
- **S2 — Pre-commitment symmetry.** Both parties can evaluate the other **before** committing.
  Not a new mechanism: it is S1 plus the requirement that evaluation be possible at that
  point in time.
- **S3 — Bilateral evidence.** An interaction yields evidence on both sides bound by the same
  `h`. A one-sided record of a two-sided interaction is a claim, not evidence.

### 3.3 Mechanism — one field short

BCC already carries `covered_entity_address`: a counterparty field, specialized to HIPAA.
Generalizing it to `counterparty_did` (+ optionally `counterparty_commitment_hash`) gives S3
directly, and reuses the same generalization authority needs in §1.3.

**Note the convergence:** authority and symmetry both resolve by generalizing a
HIPAA-specific field into a domain-neutral one. That is a strong signal the Shield vertical
was doing the general thing all along and the protocol simply never lifted it.

---

## Can authority *replace* reputation?

Asked directly, and worth answering formally rather than by preference. Two primitives are
interchangeable only if each entails the other. Test both directions with counterexamples.

### Does authority entail reputation?

**No.** Counterexample: agent `A` holds a valid, unrevoked delegation from principal `P` with
scope `S`, and has performed every action within `S` incompetently — hallucinating, burning
capital, failing every task. `A` is fully *authorized* and worth nothing to a counterparty.

Authority is **permission**, granted ex ante by a principal. Reputation is **performance**,
earned ex post through behavior. A delegation says an agent *may* act; it says nothing about
whether it acts *well*. Two agents with identical delegations can have opposite track records,
so no function from delegation to behavior exists.

### Does reputation entail authority?

**No**, symmetrically. Agent `B` has an impeccable anchored track record and no delegation
from anyone. It is trustworthy and unauthorized — it may not act on your behalf, however well
it has behaved before.

### Therefore: orthogonal

Neither is derivable from the other, so by the independence test both survive. They answer
different questions:

| | Question | Direction | Source |
|---|---|---|---|
| Authority | *May it act, and for whom?* | ex ante | granted by a principal |
| Reputation | *How has it acted?* | ex post | earned through behavior |

### The decisive argument: completeness

Independence alone would permit dropping one if the thesis did not need it. It does.

Reputation carries thesis clauses ③ (*can bind future behavior*) and ⑤ (*produces
independently checkable evidence*). Authority carries **neither** — it is not currently a
thesis clause at all. Replace reputation with authority and ③ and ⑤ become unentailed: the set
stops being complete, which is the one property the audit established it has.

### The partial overlap, quantified

There is a real intersection, and it is worth being exact about its size rather than waving at
it. Evidence that an agent stayed within its delegated scope *is* behavioral evidence — so
authority does cover part of reputation's territory.

Precisely: it covers **compliance**, one of AIS's four components (`wC = 0.20`). It says
nothing about entropy, grounding, or sacrifice — the other 80%. Authority makes the compliance
component *resolvable rather than claimed*, which is exactly the mainnet item-8 fix. It does
not make the other three components exist.

### Conclusion

Authority is an **addition**, not a substitution. The natural ordering is a progression, and
the count follows from it rather than being chosen:

```
memory      → continuity   (is there a subject?)
ownership   → capability   (can it act, and lose?)
authority   → permission   (may it act, for whom?)
reputation  → performance  (how has it acted?)
```

Four, not three — and that is fine, because the count was never the criterion. The partition
is still exact: memory ⊨ ②, ownership ⊨ ①+④, reputation ⊨ ③+⑤, authority ⊨ the new clause,
⑥ remains a property of the medium.

## Summary of what adopting all three costs

| | Thesis change | New mechanism | Reuses | Blocks/unblocks |
|---|---|---|---|---|
| Authority | +1 clause | generalize `SmartBAA` → `Delegation`; gate resolves the chain | ComplianceGate, bcc_middleware | **Closes readiness item 8** |
| Termination | +1 clause | registry lifecycle state + tombstone root | StateAnchor, dispute path | **Blocked on** the registry-mutability question the upgradeability decision also faces |
| Symmetry | generalization only | `counterparty_did` on BCC | BCC, existing verifiability | Enables A2A honestly |

Two of the three cost almost nothing structural — they lift an existing Shield mechanism to
the protocol level. Termination is the genuinely new one, and it is entangled with a decision
already open.

**Recommendation:** adopt authority and symmetry now (both are generalizations of built
mechanisms), and settle termination together with registry mutability rather than separately —
they are the same question wearing two hats.
