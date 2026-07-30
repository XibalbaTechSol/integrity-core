# Is the primitive set closed? — a coherence audit

Companion to [`three-foundational-primitives.md`](three-foundational-primitives.md). That note
argued for a *count*; this one asks the question that actually matters: **is the set coherent,
non-redundant, and closed?**

Treat the primitives as an axiom set and the thesis as the theorem they must entail. Three
tests:

- **Completeness** — does every clause of the thesis follow from the primitives?
- **Independence** — does any primitive follow from the others? (A derivable primitive is not
  a primitive.)
- **Groundedness** — does each derive from a stated principle, or merely from what happens to
  be implemented?

## The closure condition

Spec v0.3 §1 defines the target. An agent is an **Economic Sovereign** iff it is:

> a continuing entity that ① owns its smart contracts, ② remembers via durable anchored
> memory, ③ can bind future behavior, ④ holds material value at risk, ⑤ produces
> independently checkable evidence, and ⑥ cannot unilaterally rewrite that evidence after
> finality.

That sentence *is* the closure criterion. The set is complete if and only if ①–⑥ are each
entailed. Anything not needed for ①–⑥ is not foundational; anything required by ①–⑥ but
absent is a hole.

## Completeness

| Thesis clause | Entailed by | Status |
|---|---|---|
| ① owns its smart contracts | Agent-Owned Contracts | ✅ built |
| ② remembers via anchored memory | Persistent Memory | ✅ gate built; §7.2 enforcement open |
| ③ can bind future behavior | Reputation *(before-acting half: BCC)* | ✅ built |
| ④ holds material value at risk | Agent-Owned Contracts *(stake)* | ⚠️ `[PARTIAL]` — no minimum at registration |
| ⑤ produces checkable evidence | Reputation *(after-acting half: observability)* | ✅ ingest + re-derivation built |
| ⑥ cannot rewrite after finality | **medium property** §3.1, not a primitive | ✅ built |

**Result: the set is complete with respect to the stated thesis.** Every clause maps, nothing
is orphaned, and ⑥ correctly falls out as a property of the medium rather than something an
agent possesses — which is itself a consistency check passing, since ⑥ is the only clause
phrased as an inability rather than a capability.

Note what this shows about the count: **three is not load-bearing.** ①–⑥ could be grouped as
three, four, or six. What matters is that the grouping is a partition — every clause covered
exactly once, no clause covered twice, no primitive covering nothing.

## Independence

Where the current six-item list is *not* a partition:

| Pair | Relationship | Verdict |
|---|---|---|
| §4.3 self-sovereignty vs §4.2 agent-owned contracts | 4.3 is the key; 4.2 is what the key controls. Ownership is *expressed through* signing. | **Not independent.** 4.3 is the substrate — belongs in §3 with attribution. |
| §4.5 stake vs §4.2 ownership | You can only stake what you own; stake is ownership with consequence attached. | **Not independent.** Two views of clause ①+④. |
| §4.4 BCC vs §4.6 observability | Pre-action commitment and post-action evidence. | **Independent in mechanism, joint in purpose** — together they are one record. Grouping is a judgment call, not an error. |
| §4.1 memory vs §4.6 observability | Both concern history. | **Independent, and the boundary is sharp:** memory is the agent's *own* record (agent-authored, agent-anchored); observability is the *counterparty-checkable* record (re-derived by the oracle, never trusted from the client). Same subject, opposite trust direction. |

So the six-item list has **two genuine redundancies** (4.3, 4.5) and one grouping choice
(4.4/4.6). Collapsing those is what produces three — but the reason to collapse is
non-independence, not tidiness.

## Groundedness

Each surviving primitive derives from an economic principle stated in §4, not from the code:

- Memory ← continuity of the economic agent
- Ownership+stake ← residual rights of control + internalization of consequences
- Reputation ← credible commitment + verifiability

All three are principles, not mechanisms. Passes.

## Where the logic is NOT closed

Three clauses the thesis does not make, which a reader will nonetheless expect. Each is either
a genuine hole or a deliberate scope boundary — and right now the spec says neither.

### 1. Authority — *on whose behalf does this agent act?*

The protocol calls agents Economic Sovereigns, but a real agent acts **for** someone: an
operator, a company, a user. `SovereignAgent` has a `controller` and supports rotation, so the
mechanism exists — but "who authorized this agent, with what scope, and how is that
delegation revoked?" is not a thesis clause and not a primitive.

This is the largest gap. Every regulated use case (Shield especially) needs it: a covered
entity delegating to an agent is a *delegation*, and §8's client-supplied
`covered_entity_address` is exactly the hole where that delegation should be proven rather
than claimed.

**Closure requires either** adding a clause — *acts under a verifiable delegation of authority
from a principal* — **or** stating explicitly that authority is out of scope and the
controller is opaque to the protocol.

### 2. Termination — *how does an agent stop being one?*

Nothing covers decommissioning, revocation of standing, or death. §7.4 lineage covers
fork/migration/recovery — becoming a *different* agent — but not ceasing. Since memory is
append-only and registration is once-per-DID with no update path, an agent currently cannot be
ended, only abandoned.

For a system whose premise is that history cannot be rewritten, "how does this end" is not a
detail: an abandoned agent with stake and standing is indistinguishable from a live one until
silence-as-signal exists (`[PLANNED]`).

### 3. Symmetry — *can the agent verify its counterparty?*

Reputation as written is one-directional: others verify the agent. But A2A is a stated goal,
and in an agent-to-agent trade both sides need it. The mechanism generalizes trivially — the
question is whether the thesis intends it. §15 treats ERC-8004 as discovery, not verification.

## Recommendation

The set **is** closed with respect to the thesis as written. To make the logic closed in the
stronger sense — no reader-expected clause silently missing — do two things:

1. **Adopt the partition** (whatever the count): memory / ownership-with-stake / reputation,
   with self-sovereignty demoted to a medium property. Justified by non-independence, not
   aesthetics.
2. **Rule on the three open clauses explicitly.** Authority is the one that matters most and I
   would argue belongs *in* the thesis; termination and symmetry can legitimately be declared
   out of scope — but declared, in §17 ("What This Protocol Is Not"), rather than left for a
   reader to notice.

Consistency demands one further edit either way: **§2's "AIS is downstream of primitives"
must be reconciled with reputation being one.** AIS is the score; reputation is the record it
summarizes. Without that sentence the two readings contradict.
