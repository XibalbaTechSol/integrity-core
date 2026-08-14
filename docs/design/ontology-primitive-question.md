# Design Question — Should "Ontology" Be a Fifth Foundational Primitive?

**Written:** 2026-08-13
**Type:** Decision memo, checked against the existing closure argument in
`docs/wiki/concepts/foundational-primitives.md` and `docs/design/primitive-set-coherence.md`.
No spec/contract changes proposed here.
**Trigger:** Semantica competitive analysis — Semantica's ontology layer (OWL generation, SHACL
validation, SKOS vocabularies) is one of its real capabilities Integrity Protocol lacks.

## The proposal being evaluated

Add "agent ontology" — a formal vocabulary/schema for what kinds of entities, claims, and
relations are valid — as a fifth foundational primitive, alongside Persistent Memory,
Agent-Owned Contracts, Authority, and Reputation.

## Test it against the protocol's own closure argument

`foundational-primitives.md` doesn't treat "primitive" as a loose label — it derives the set of
four from spec §1's definition of an Economic Sovereign, with each of seven thesis clauses
entailed by exactly one primitive (or explicitly named as a *medium property*, not a primitive,
when it doesn't fit):

| Thesis clause | Entailed by |
|---|---|
| ① owns its smart contracts | Agent-Owned Contracts |
| ② remembers via anchored memory | Persistent Memory |
| ③ can bind future behavior | Reputation (before-acting) |
| ④ holds material value at risk | Agent-Owned Contracts (stake) |
| ⑤ produces checkable evidence | Reputation (after-acting) |
| ⑥ cannot rewrite after finality | *medium property* — not a primitive |
| ⑦ acts under delegated authority | Authority |

The same page already ran this test once and failed cryptographic self-sovereignty on it
deliberately: keys are "the substrate all four are *expressed in*," present in all four, so they
belong "beside attribution as a property of the medium," not as a fifth peer. That's the
precedent to apply here, not a new argument to invent.

**Does ontology entail an eighth, currently-unentailed thesis clause?** Each of the four
primitives answers a question a counterparty must resolve *before delegating anything of
value*: is this the same agent, can it act and lose, may it act and for whom, how has it acted.
Ontology answers a different kind of question: *do we agree on what these terms and claims
mean* — a semantic-interoperability question. It's a precondition for **interpreting** evidence
correctly (was this event a "HIPAA violation" under a shared vocabulary), not a precondition for
**trusting** it. A counterparty can resolve all four trust questions about an agent it shares no
formal ontology with at all — the two axes are independent.

## Recommendation: no, not a fifth primitive — but real, and it already has a home

Adding it as a primitive would blur the closure argument the docs are explicitly proud of (the
"why these four, and not others" section exists precisely to make additions like this
answerable, not just debatable). The correct move is the same one the docs already made for
cryptographic self-sovereignty: name what ontology actually *is* — infrastructure that deepens
primitive #3 (Authority: "may it act, and for whom, under what compliance framework") and
primitive #4's evidence interpretation — not a peer of the four.

Concretely, this isn't new work to invent: `docs/design/evidence-export.md`'s Phase B is already
a minimal ontology — a versioned `reason_code/intent_type → {framework, control_id,
control_title}` control map, scoped for exactly the compliance-vertical vocabulary problem
Semantica's OWL/SHACL tooling targets. If Semantica-grade rigor is wanted here (formal schema
validation, not just a static lookup table), the answer is: **graduate evidence-export.md's
Phase B into a real control ontology**, framed as compliance-control infrastructure under
Authority, not as a new foundational concept. `docs/plans/2026-08-13-reasoning-engine-decision.md`
(option 2) independently arrives at the same place from the reasoning-engine question — a small
rule layer over that same control map. The two questions converge on one piece of work, which is
a good sign the scoping is right.

## What this doesn't settle

Whether to actually build the graduated control ontology now, later, or as part of the
reasoning-engine decision's option 2 — that's the same sequencing call
`2026-08-13-reasoning-engine-decision.md` poses, not a new one.
