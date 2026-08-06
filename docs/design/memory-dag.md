# Memory as a Merkle DAG

**Status:** design — **not implemented, not tested.** No shell this session
(see `e2e-audit-2026-07-31.md` "Method"). Nothing below has been run.

**Goal:** make the protocol's *evidence* a hierarchical, content-addressed graph
whose relationships are cryptographically committed — so lineage and provenance are
provable rather than asserted. Closes §7.4 lineage attestation, recorded as
**"OPEN … Not started"** in `docs/wiki/concepts/agent-memory.md:79`.

> **Scope, corrected 2026-07-31.** An earlier draft folded the agent's *working*
> memory into this graph. That was wrong and is reversed: this DAG covers
> **protocol evidence only** — commits, sessions, test results, telemetry lineage,
> agent fork/migration/recovery. It is append-only and anchored on-chain.
>
> Xibalba's day-to-day recall (notes, facts, preferences, project context) is a
> **separate local system** — see `docs/design/xibalba-supermemory.md`. The two
> must not be one store, because their defining properties are contradictory: a
> recall layer must update, re-rank and **forget**; an evidence layer must
> **never** forget, since forgetting is exactly what anchoring prevents.
>
> The permitted coupling is one-way and optional: a recall entry MAY cite an
> anchored `node_id` as evidence. Nothing in this graph depends on the recall layer.

---

## 1. Why the existing Merkle tree cannot do this

The Trust Vault's tree is a commitment over a **flat set**, and the repo's
convention deliberately erases structure. `vault.py:38-42`:

> Sorting … means a verifier does not need to know which side a sibling was on …
> **The root becomes a function of the *set* of leaves.**

`StateAnchor.sol:17-23` states the same intent — the root is "a true function of
the *set* of leaves, **not their arrangement**." Sorted-pair hashing exists to make
position meaningless.

So the anchored root answers exactly one question — *was this leaf in this set?* —
and by construction can answer nothing about order, hierarchy, or derivation.
Adding more leaf kinds to that tree (the approach in
`merkle-standardization.md`) widens coverage but cannot express a relationship.
**A different structure is required, not a bigger tree.**

## 2. What Merkle structure does and does not give you

Stated up front because the distinction decides what to build:

- **It proves relationships you assert**, and makes them tamper-evident. You
  cannot rewrite a parent without changing every descendant's identity.
- **It does not discover relationships.** Hashes verify; they do not cluster or
  infer similarity. Behavioral similarity is explicitly observational-only in this
  protocol (`agent-memory.md:103-107`) and is a separate mechanism.

The one genuine *inference* primitive content-addressing provides — and the
payoff worth naming — is: **identical `content_hash` across sessions, runtimes, or
agents proves shared provenance without revealing content.** Same conclusion
reached twice, same evidence cited by two agents, a memory that survived a fork —
all become detectable from hashes alone.

---

## 3. Three layers, and the split is the whole design

The naive design — "make every `[[link]]` a hash edge" — **cannot work**, for two
independent reasons found by inspecting the actual memory files.

**(a) Semantic links can form cycles.** `Related:` links point both ways freely.
A cycle is unhashable: A's preimage would need B's id and B's would need A's. Git
avoids this by construction (commits only point backward in time); a wiki does not.

**(b) Memory files are edited in place.** The memory instructions require updating
an existing file rather than duplicating it. But content-addressed nodes are
immutable — an edit changes the id, orphaning every inbound reference.

Both are solved by separating layers, exactly as git separates objects from refs.

### Layer 1 — Objects (immutable, hashed, acyclic by construction)

```
node = {
  schema:       "integrity.memory.node.v1",
  agent_id:     "did:integrity:…",
  kind:         "memory" | "commit" | "session" | "test_result" | "lineage",
  content_hash: keccak256(canonical(body)),   # content itself stays local
  parents:      [ node_id … ],                # STRICTLY backward in time
  edge_type:    "supersedes" | "derived_from" | "forked_from" | "session_of",
  timestamp:    <ms>,
  source:       "claude-code" | "hermes" | "agy" | "oracle",
}
node_id = keccak256(canonical(node))
```

`parents` may contain **only** edges that are acyclic by construction — a previous
version of this node, or the session/commit it came from. Both point strictly
backward in time, so the object graph is a DAG by construction rather than by
convention. No cycle check is needed, because time supplies one.

`source` is the runtime discriminator F8 added, which is what finally lets memory
be grouped by runtime (audit open item #2).

### Layer 2 — Refs (mutable name → current head)

```
refs/memory/spec-v03-normative → <node_id of current head>
```

This is what makes editing work. Updating a memory writes a **new** node with
`parents: [<old_id>], edge_type: "supersedes"` and moves the ref. Nothing is
mutated, no descendant is orphaned, and the full revision history is walkable and
provable. `name` stays stable and human-facing; ids stay immutable and machine-facing.

### Layer 3 — Semantic links (hashed as *content*, never as edges)

`[[other-name]]` links are committed **inside** `content_hash`, as claims — not as
`parents`. Consequences, all desirable:

- **Cycles are fine.** A link is a string in a body, not a structural dependency.
- **Dangling links are fine.** The memory instructions explicitly allow a `[[name]]`
  matching nothing yet; a name has no id to point at, and needs none.
- **They remain tamper-evident.** You can still prove *this node asserted a link to
  name X at time T* — which is the useful property — without the link constraining
  the hash graph.

> **The rule:** *structural* edges are ordered, positional, backward-in-time, and
> hashed into `parents`. *Semantic* edges are unordered, possibly cyclic, and live
> in content. Never promote a semantic link into `parents`.

---

## 4. Anchoring: one head commits everything

Because every node commits to its parents, anchoring a single head id transitively
commits the entire reachable history. So the on-chain write collapses from
"one root per batch" to **one 32-byte head pointer**, and it is strictly stronger:
it covers structure, not just membership.

Where multiple refs exist, anchor a **root-of-heads** — the existing sorted-pair
Merkle tree over the current head ids. The two structures compose cleanly:

| Layer | Structure | Rule |
|---|---|---|
| Within memory | Merkle **DAG** | ordered, positional parents |
| Across heads at anchor time | Merkle **tree** | sorted pairs, position irrelevant |

Both are correct in their own layer. The tree's position-erasure is harmless over
head ids, because the DAG already carries the structure.

**Relationship to the existing gate.** Registration requires
`StateAnchor.latestRoot != bytes32(0)` (`agent-memory.md:57-62`). A DAG head is a
32-byte value, so the gate is satisfied unchanged — **no contract change, no
oracle change.** The genesis sentinel `keccak256("integrity.trust-vault.genesis.v1")`
stays valid as the empty-vault head.

**Migration is nearly free.** All 7 existing agents report `latestRoot == 0`
(`agent-memory.md:81-85`) — there is effectively **no anchored memory history to
migrate**. Each needs one controller-signed `anchorRoot` regardless, which it
already needed. This is far cheaper than the v1→v2 tree migration in
`merkle-standardization.md`, and independent of it.

---

## 5. New proof type: ancestry

Today there is one proof (Merkle inclusion). The DAG adds a second:

- **Inclusion** — "this head was anchored": Merkle path to the anchored root. Unchanged.
- **Ancestry** — "node B descends from node A": reveal the chain of intermediate
  node objects; the verifier re-hashes each and checks each `parents` link resolves
  to the next id, terminating at an anchored head.

Ancestry proofs reveal *node metadata and structure*, never content — bodies are
behind `content_hash`. Same privacy posture as the BCC hash-only commitment.

This is what makes §7.4 fall out: fork, migration and recovery become
`edge_type: "forked_from"` with a controller-signed attestation, rather than a
bespoke mechanism. Per `agent-memory.md:97-101` lineage still confers **no**
automatic AIS or stake transfer — the DAG makes the claim provable, it does not
make it privileged.

---

## 6. What this does not do

- **No similarity or clustering.** Content-addressing detects *identity*, not
  resemblance. §7.5 behavioral similarity remains observational-only.
- **No new AIS term.** `agent-memory.md:111-113`: memory adds no fifth component,
  and `scoring-core` stays the sole computer of the score.
- **No 8th contract.** Rides on `StateAnchor`, per the trap recorded in
  `spec-v03-normative` — the PrimitiveSet stays 7.
- **Does not fix the odd-node convention split** (E9). Independent problem,
  independent document; the DAG layer is unaffected by it because DAG edges are
  positional and never sorted-pair hashed.

---

## 7. Order of work

| # | Step | Verify by |
|---|---|---|
| 1 | Pin node schema + canonical encoding in `INTERFACE_CONTRACT.md` | review |
| 2 | `node_id` + canonicalization, with vectors | unit tests, independent vectors |
| 3 | Ref store (`name → head`) + supersede-on-edit | round-trip: edit 3×, walk history |
| 4 | Import existing memory files as genesis nodes; `[[links]]` → content | node count matches file count |
| 5 | Root-of-heads + `anchorRoot` of the head | `latestRoot != 0`, gate passes |
| 6 | Ancestry proof generate + verify | forked node proves descent |
| 7 | Cross-runtime provenance query on `content_hash` | the §2 payoff, demonstrated |

Step 7 is the acceptance test: two runtimes reaching the same conclusion should be
detectable from hashes alone, with no content disclosed.

**Blocked on the shell from step 2 onward.**
