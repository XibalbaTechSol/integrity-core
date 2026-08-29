# `xibalba.integrity` as a protocol-native software developer — design

**Status: design only.** Nothing in the "Proposed" sections below is built. The
"Shipped today" section is the honest inventory of what already runs, including what is
wired but unverified. Written against *Integrity Protocol — Comprehensive Design &
Specification v0.3*.

## Goal

`xibalba.integrity` already exists as an Economic Sovereign: it owns its contracts, holds
its own keys, and emits signed telemetry. The goal is for it to operate as a senior
software developer *on this protocol* such that its development work is itself
protocol-evidenced — commitments before it acts, telemetry that reflects real engineering
outcomes, and an AIS that moves for reasons a counterparty could check.

The point is not autonomy for its own sake. It is that a dev agent is the most demanding
honest test of the protocol: if `sacrifice` can't be earned truthfully by an agent doing
real work, the primitive is decorative.

## Shipped today (verified 2026-07-29)

| Component | State |
|---|---|
| Identity | **Real.** `did:integrity:68fed133…2a14a861`, bridged from the Hermes Ed25519 key so `did:xibalba:` and `did:integrity:` signatures interoperate. Stable, idempotent, works offline. |
| On-chain registration | **Real.** 7 primitives in `XibalbaAgentRegistry` on Base Sepolia; `SovereignAgent 0x360E2a56…`, agent wallet `0x14bB099e…` holding `DEFAULT_ADMIN_ROLE`. |
| XNS handle | **Real.** `xibalba.integrity`, self-claimed via `SovereignAgent.execute` (tx `0x827883ad…`, block 44769074). |
| Oracle registration + telemetry | **Real.** Session-start/end hooks flush signed telemetry; `/v1/agent/{did}/telemetry` shows genuine events. |
| BCC intent gating | **Live and enforcing.** `pretool_gate.py` runs on `Bash\|Write\|Edit\|MultiEdit\|NotebookEdit`; with `bcc_middleware` + OPA up, `session.log` shows 271 of 348 gate decisions as `enforced=True` — the real allow path against the real OPA engine, not a simulation. Still fails **open** when middleware is down, and no real DENY has been observed yet, so the *deny* half remains unexercised. |
| ITK liquidity | **Real.** Holds `MINTER_ROLE` on `IntegrityToken`; mints route `SovereignAgent.execute → mint` signed by its own controller. Proven live: minted 500 ITK to its treasury (10,500 ITK held). Registration does not yet draw from it — see `PRODUCTION_GAPS.md` §20. |
| Cognition / traces | **Real, minimal.** Session hooks now export OTel spans (path B) as well as signed telemetry (path A); `claude_session_start` is queryable via `/v1/agent/{id}/otel/traces`. Only session-boundary spans exist so far — no per-tool-call reasoning spans yet. |
| Persistent memory | **Not conformant.** `StateAnchor 0x09DCBBd0…` reports `latestRoot == 0`. Memory today is local markdown under `~/.claude/.../memory/` — real, useful, and cryptographically worthless. |
| AIS | 800.0 — entropy 1000, grounding 1000, compliance 1000, **sacrifice 0**, `zk_proof_verified: false`. Telemetry grew 2 → 6 events over one working session, which is what filled the radar in the dashboard. |

That AIS is the honest problem statement. Three components sit at maximum off two
heartbeat events, and the one component meant to measure costly effort is zero. The score
is not wrong — it is correctly reporting that almost nothing has been measured.

## Proposed

### 1. Memory first (spec §4.1, §7)

Everything else depends on it, and it is the one primitive the agent currently fails.

- Anchor the genesis root (one controller-signed tx; §4.4a's `GENESIS_VAULT_ROOT`).
- Define what a **dev-work vault leaf** is. Candidate: one leaf per completed unit of work
  — `keccak256(task_id ‖ commit_sha ‖ test_result_hash ‖ timestamp)`. Content stays local;
  only the commitment is anchored.
- Re-anchor on a cadence, per the §4.4a/`merkle-batching` tradeoff. Per-task anchoring is
  too expensive; per-session is probably right, and leaves a bounded uncommitted window
  that should be stated rather than hidden.

The property this buys: the agent can prove *what it knew and when* without revealing the
work — and cannot quietly rewrite its own history afterward.

### 2. Make the BCC gate real (spec §4.4, §11)

The gate exists; what's missing is evidence it ever denied anything.

- The allow path is now real (271 enforced decisions this session). What remains is a real
  DENY end-to-end — construct an intent OPA must refuse and confirm the tool call is blocked.
- Decide fail-open vs fail-closed **per intent class**, not globally. Reading a file
  failing open is fine. `git push`, a deploy, or a contract write failing open is not.
- Per §4.4, commitment outcomes SHOULD become vault leaves — which is what ties this
  section to the one above.

### 3. Earn `sacrifice` honestly (spec §8.2, §9.3)

`sacrifice` is currently a token-count proxy (`Σtokens / 50,000` hours). For a dev agent
the temptation is to inflate it by being verbose, which is exactly the wrong incentive.

Open question, not a resolved design: what is the *real* costly signal for engineering
work? Wall-clock on green CI? Tests added that fail before a change and pass after?
Neither is spoof-proof. This needs to be answered before wiring anything, because a
sacrifice signal that rewards the wrong thing is worse than one that stays at zero.

**Constraint:** `integrity-oracle/scoring-core` is the sole computer of AIS and its four
weights are fixed (§8.1). No new component. Any change here is to what feeds
`derive.rs`, not to the formula.

### 4. Scope of autonomy

Deliberately excluded from this design: an autonomous loop that picks up work and opens
PRs unattended. The primitives that would make that safe — enforced BCC on write paths (now real for
allow, unproven for deny), anchored memory (gate built; this agent's own root still zero),
and minimum bonded stake (Appendix A gap 3) so misbehavior is *costly* — are variously
unbuilt, unverified, or unsatisfied by this very agent. Staking an agent's own capital against its commits is the
mechanism that makes autonomy accountable rather than merely permitted; until that exists,
autonomy would be unstaked action wearing a trust layer.

## Open questions

1. **Which vault leaves matter?** Every tool call is too granular to anchor and too noisy
   to be evidence. Per-task is a guess, not a conclusion.
2. **Does dev work belong in AIS at all,** or is it a separate attestation? A high AIS
   currently means "behaves predictably under telemetry," not "writes good software."
   Conflating them would quietly redefine the score.
3. **What is this agent's blast radius?** It has `DEFAULT_ADMIN_ROLE` on its own
   `SovereignAgent` and a funded wallet. Any autonomy proposal has to state what it may
   spend and sign without a human.
4. **Silence-as-signal (Appendix A gap 8)** matters more for a dev agent than most: an
   agent that stops reporting while still acting is the failure mode observability is
   supposed to catch.

Related: [Persistent Memory, Genesis Root & Lineage](../wiki/concepts/agent-memory.md) ·
[BCC](../wiki/concepts/bcc.md) · [AIS](../wiki/concepts/ais.md) ·
[`PRODUCTION_GAPS.md` §19](../../PRODUCTION_GAPS.md)
