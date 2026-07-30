# Three foundational primitives — a proposed consolidation

**Status: proposal.** This reframes spec v0.3 §4 and would require a spec revision to adopt.
It is written as a design note rather than applied to the wiki, because the spec is the
normative document and this changes its shape.

## The problem with six

Spec v0.3 §4 names six foundational primitives:

| § | Primitive | Principle |
|---|---|---|
| 4.1 | Persistent Memory | continuity of the economic agent |
| 4.2 | Agent-Owned Smart Contracts | residual rights of control |
| 4.3 | Cryptographic Self-Sovereignty | exclusive property rights in identity |
| 4.4 | Behavioral Commitment (BCC) | credible commitment |
| 4.5 | Economic Skin-in-the-Game | internalization of consequences |
| 4.6 | Continuous Verifiable Observability | monitoring for reputation and regulation |

Six is defensible — each is a real mechanism with real code. But six is not memorable, the
list reads as a catalogue rather than an argument, and it obscures that the six are not
peers: some are *mechanisms*, one is arguably a property of the medium, and the thing a
counterparty actually cares about (standing) is not named at all.

## The proposal

Three primitives, each answering one question a counterparty must be able to answer before
delegating anything of value:

### 1. Persistent Memory — *is this the same agent over time?*

Continuity. Without it there is no subject for anything else to attach to: an agent that
cannot carry state across sessions is a stateless function invoked repeatedly, and its score
describes a history it cannot itself produce.

Absorbs: §4.1.

### 2. Agent-Owned Contracts — *does it control its own means of action, and does it have
something to lose?*

Residual control **with consequence**. Ownership without stake is control that costs nothing
to abuse; stake without ownership is a deposit someone else administers. They are the same
primitive seen from two sides — you can only stake what you own, and ownership only means
something when losing it hurts.

Absorbs: §4.2 and §4.5.

### 3. Reputation — *can others verify how it has behaved?*

Non-forgeable standing. This is the one being elevated, and it is the only primitive the
agent **cannot author**. That is precisely what makes it worth anything: the agent owns the
contract that stores it (`ReputationRegistry` is one of its seven primitives) while being
unable to write to it — only `ORACLE_ROLE` can push a score. Ownership without authorship is
the whole trick, and it is already built.

Reputation has two halves, which is why it absorbs two of the six:

- **Before acting** — a signed commitment to what is about to be done (§4.4 BCC).
- **After acting** — signed, re-derived evidence of what was actually done (§4.6
  observability).

A record of only intentions is a promise; a record of only outcomes has no counterfactual.
Together they are a behavioral record that neither the agent nor the protocol can fabricate
unilaterally.

Absorbs: §4.4 and §4.6.

### What happens to §4.3

**Cryptographic self-sovereignty stops being a primitive and becomes a property of the
medium**, alongside §3.1 immutability, §3.2 public verifiability and §3.3 attribution — where
§3.3 (*"state transitions are authorized by cryptographic keys bound to agent-owned
contracts"*) already says most of it.

That is not a demotion. Keys are the substrate every primitive above is expressed in: memory
roots are anchored by a controller-signed transaction, contracts are owned because a key
deployed them, and reputation is attributable because evidence is signed. A substrate present
in all three is better described once as a property of the medium than repeated as a peer of
the things it enables.

## What this framing buys

- **It is an argument, not a catalogue.** Continuity, control-with-consequence, and
  verifiable standing are the three things that make an entity an economic actor. That is
  defensible from first principles rather than from an implementation inventory.
- **It names what counterparties actually want.** Nobody delegates money because an agent has
  observability. They delegate because the agent has *standing* — and standing was the one
  thing the six-item list never named.
- **It matches the credit-score analogy the protocol derives from** (§2). Persistent legal
  identity, exclusive control of accounts, and an observable hard-to-rewrite record are
  exactly three things, and AIS is the composite *downstream* of them.

## The tension this must not paper over

Spec §2 says plainly: *"AIS is downstream of primitives — not a replacement for them."*
Elevating reputation risks reading as a contradiction.

It is not, provided the distinction is kept explicit:

- **AIS is a score** — a derived, weighted composite computed in exactly one place
  (`scoring-core`), versioned, and replaceable without changing what the protocol *is*.
- **Reputation is the primitive** — the non-forgeable behavioral record that AIS summarizes.
  Change the formula tomorrow and the record stands; delete the record and no formula means
  anything.

The spec should say that in one sentence if this is adopted, because the two are easy to
conflate and the conflation is exactly what makes "reputation systems" untrustworthy
elsewhere.

## Honest consequences

1. **Consolidation must not hide status.** §4.4 BCC is implemented; §4.5 minimum stake is
   `[PARTIAL]`; §4.6 silence-as-signal is `[PLANNED]`. Folding them under two headings must
   keep each mechanism's own status visible, or the three-primitive framing becomes a way of
   making gaps disappear — the exact failure this repo's ground rule exists to prevent.
2. **It raises the stakes on the ZK-boost binding gap.** If reputation is foundational, then
   `MAINNET_READINESS.md` item 3 — the boost being a period-wide `BOOL_OR` rather than bound
   to what it proves — is no longer a scoring detail. It is a hole in a foundational
   primitive, and should move up the blocker list accordingly.
3. **Portability becomes a first-class question.** `CCIPReputationBridge` deliberately never
   bridges the ZK boost (it must be re-earned per chain). Under a six-item framing that is an
   implementation choice; under a three-primitive framing where reputation is foundational,
   "what exactly is portable, and what must be re-earned" deserves a spec answer rather than
   a code comment.
4. **It is a spec revision, not a docs edit.** §4 changes shape, §3 gains a property, and §2
   needs the AIS-vs-reputation sentence. That is a v0.4, and the wiki should not be updated to
   describe three primitives while the normative document still says six.

## Recommendation

Adopt it, with the AIS-vs-reputation distinction stated explicitly in §2 and each absorbed
mechanism keeping its own status line. The framing is stronger than the six-item list and
costs nothing but a spec revision — and it names the thing the protocol is actually selling.
