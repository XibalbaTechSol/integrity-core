# Mainnet readiness — what must be done first

Status reconciled 2026-08-17. Scope: what stands between the current Base Sepolia deployment
and a mainnet launch that the protocol's own claims would survive. Every item below is
either verified against code/chain in this repo or cites where it is recorded.

The accepted normative baseline is `docs/SPEC.md` (v1.0.0-draft) — see `docs/DOCUMENT_STATUS.yaml`, the single source of truth for this; `docs/archive/2026-08/integrity-protocol-v0.4.md` is archived, not current (corrected 2026-09-05, see `PRODUCTION_GAPS.md`'s dated pointer-correction entry). The current explanatory whitepaper is `docs/WHITEPAPER.md` (v3.2). The former proposed amendment (`integrity-protocol-v0.5-proposed.md`) is likewise archived and does not relax any blocker in this document. Phase 0's local
`IntegrityIdentityReadV1` singleton and the generated local ZK verifier both postdate the
declared Base Sepolia deployment; source capability is not deployed capability.

Ordering is by consequence-if-ignored, not by effort.

---

## P0 — Blockers. Launching without these makes a protocol claim false.

### 1. [DONE] Key separation: six protocol roles are one EOA

`deployments.baseSepolia.json` → `protocolAddresses`:

```
arbitrator, disputer, funderWallet, governance, oracleSigner, resolverSigner
  → all 0x67bA5D723E1F5517afF7eb980E2f73a9e17aD556
```

That same EOA holds `MINTER_ROLE` on `IntegrityToken` and `DEFAULT_ADMIN_ROLE` across the
singletons. One key compromise means: unlimited token mint, arbitrary score updates,
self-arbitrated disputes, and governance capture — simultaneously. The protocol's pitch is
that an agent's reputation cannot be unilaterally rewritten; today one key rewrites
everything.

**Done when:** each role is a distinct signer; `governance` and `arbitrator` are multisigs
(or the deployed `IntegrityGovernance` timelock); `oracleSigner` is an isolated hot key with
a documented rotation path; no single key can both mint and score. Verify by reading the
roles back from chain post-deploy, not from the deploy script. *(Update: Enforced in `Deploy.s.sol` by transferring `DEFAULT_ADMIN_ROLE` and `MINTER_ROLE` to the governance contract, routing `arbitrator` to governance, and requiring distinct EOAs for operational signers on non-local networks).*

### 2. The recorded ZK verifier is older placeholder bytecode; a linked candidate is now deployed

The current local `contracts/src/oracle/UltraPlonkVerifier.sol` is generated verifier source
and has local proof-path coverage. The verifier address in the existing Base Sepolia deployment,
`0xD6eE9031320382831c8C96627D02aEE573089226`, still contains the earlier fail-closed
placeholder bytecode. A read-only RPC check on 2026-09-09 confirmed chain ID `84532`, block
`46581012`, and only ~233 bytes of runtime code at that address. A linked generated verifier
candidate was subsequently deployed at `0x565184C507CD2c22a0c95f914c9034C8F289818A`
(tx `0xb394ebe6efb7fa09b95b14e6ee522ea67a7a590e9d7cfb21e7eec598175f1547`); its runtime is
23,912 bytes, the known valid fixture returns `true`, and a one-byte-tampered proof reverts.
The old factory was replaced at `0x240F72d7c1fc824BB641e51213ca135Ee5514A5B` in tx
`0x11c5cd8ebe613a87812229a0bb86c207b2e0e510b71b013e04ccf998dcacd033`; its immutable
`initialZkVerifier` now reads the candidate, and the old
factory no longer has `REGISTRAR_ROLE`. Existing agent clones still require controller-routed
version pinning and adoption.

**Done when:** the generated verifier is independently reviewed and adopted by all active
verifier registries through an approved migration. Factory adoption, deployment-record
reconciliation, and direct bytecode/behavior readback are complete; existing registry-clone
adoption remains open.

### 3. ZK boost follows proof-bearing event coverage in source; deployment remains open

> **Note:** if the three-primitive consolidation is adopted
> ([`three-foundational-primitives.md`](archive/2026-08/three-foundational-primitives.md)),
> this stops being a scoring detail and becomes a hole in a *foundational* primitive —
> reputation — and should move up this list accordingly.

The oracle formerly used `BOOL_OR` over the reporting window, so one verified proof
anywhere in ~30 days multiplied the entire period's score by 1.15. Source now computes
`1.0 + 0.15 * verified_event_ratio`, preventing one proof-bearing row from receiving the
full-period multiplier. The source-level public-input gap is now closed:
`ReputationRegistry` checks the pinned identity, strictly increasing nonce, current chain,
its own clone address, and the exact anchored BCC leaf before verification; the circuit
commits that leaf into the intent commitment and the leaf cannot be reused. A proof for
event A therefore cannot be paired with event B. The remaining gap is narrower but still
material source gap is closed: the oracle score-sync path calls
`updateScoreWithCoverage`, and `ReputationRegistry` applies
`1.0 + 0.15 * verifiedEventRatioBps / 10_000` while the event-bound proof is active.
The legacy `updateScore` method remains only for compatibility and does not configure
coverage. The remaining gate is deployment/adoption: existing Base Sepolia bytecode must
be migrated and exercised, and the live signer path must be verified.

**Done when:** the boost derives from proof-bearing events (or the proof's public inputs
commit to the scoring window), and a test demonstrates that a proof for event A cannot
boost unrelated event B. Appendix A gap 4.

### 4. Cross-language signed-payload canonicalization is closed in source

Rust (`serde_jcs`) and Python (`jcs` in SDK, CLI, and middleware) now implement RFC 8785
JCS for the same signed bytes. This removes the former ECMAScript-number and non-ASCII
escaping divergence. Deployment/adoption remains a release concern, not a source gap.

On testnet this is an annoyance. On mainnet, a signature that verifies on one side and not
the other is a correctness failure in the trust chain itself.

**Done when:** both sides implement one specified standard — RFC 8785 (JCS) mandates
ECMAScript `Number::toString`, which is deterministic — with a shared cross-language
conformance vector set in CI. This is an `INTERFACE_CONTRACT.md` §4.2 change across SDK,
CLI, middleware, and oracle.

### 5. [DONE] Persistent memory: enforcement is half-built and existing agents don't conform

Recorded in `PRODUCTION_GAPS.md` §19. The registration gate is live (`400
MemoryNotInitialized`), but:

- `StateAnchor.anchorRoot` is `onlyRole(ANCHOR_ROLE)` at *every* epoch, and registration
  grants that role to the oracle signer — so the protocol can anchor an agent's genesis
  root, which spec §7.2 forbids. The agent-authorized path works; it just isn't *exclusive*.
- All 7 Sepolia agents, including `xibalba.integrity`, report `latestRoot == 0`.

**Done when:** genesis anchoring is contract-enforced as agent-only (see §6 below — this is
the one that must be right *before* first mainnet deploy, because it cannot be patched
afterwards), and no registered agent has a zero root. *(Update: Enforced in `StateAnchor.sol` and `AgentPrimitivesFactory.sol`).*

### 6. [DONE] Upgradeability — Frozen Contracts with Swappable Hooks

`SovereignAgent` and `StateAnchor` are deployed **directly per agent**. Currently, every agent's copy is frozen at whatever bytecode shipped that day without any ability to modify policy, meaning bugs are unfixable (like the §7.2 genesis anchor issue).

**Decision Finalized:** We are explicitly rejecting Beacon Proxies in favor of **Frozen Base Contracts with Swappable Policy Hooks** (pattern matching `VerifierRegistry`).

This prioritizes limiting the blast radius of a compromised governance key (worst case is Denial of Service) over fund recovery, and eliminates the storage-collision vulnerability class permanently.
- The pointers (`IAnchorPolicy` and `IExecutionPolicy`) will be **agent-controlled** (versioned-pin pattern).
- The hooks will **fail closed** (reverting the transaction if the policy throws an error or is unreachable).

**Done when:** `IAnchorPolicy` is injected into `StateAnchor.anchorRoot`, `IExecutionPolicy` is injected into `SovereignAgent.execute`, and the SDK updates its deployment pipeline to wire up these pointers to the protocol's default global policy contracts.

**Completed in source and local deployment tests:** both hosts fail closed on a policy
denial or revert; `Deploy.s.sol` deploys and serializes the default policies and transfers
their administration to governance on non-local networks; and the SDK pins execution policy,
anchors genesis, then pins the oracle-only anchor policy. A real Anvil registration test
asserts both pointers and epoch 1. Existing Base Sepolia agents retain their old frozen
bytecode, so this completion applies to future deployments and is not a migration claim.

### 7. [DONE] Bonded stake is not enforced at registration

Spec §4.5's "internalization of consequences" is the mechanism that makes slashing mean
anything. `Slasher` and the dispute path exist, but no uniform minimum stake is required to
register (Appendix A gap 3), so an agent can hold a score while risking nothing.

**Done when:** registration enforces a minimum bond, and tier elevation requires more.
*(Update: Enforced via `AgentPrimitivesFactory.MIN_REGISTRATION_BOND` and `Slasher.stakeFor` in registration pipeline).*

### 8. [DONE] Covered-entity binding (Integrity Health / HIPAA)

Spec §9.4 names this as a spoof residual. In the healthcare vertical, the field asserting
which covered entity an action falls under is taken from the caller. Under HIPAA this is
the highest-consequence field in the payload.

**Done when:** the covered-entity binding is verified on-chain (`CoveredEntityRegistry` /
`SmartBAA`) rather than trusted from the request, and a test proves a forged
`covered_entity_address` is rejected.

**Completed in source and local tests:** both the BCC middleware and oracle use the
client field only as a lookup key for the exact `(covered entity, SovereignAgent)` pair;
authorization/compliance comes from live `CoveredEntityRegistry` and `SmartBAAFactory`
state. Healthcare oracle scoring now fails closed when the address is missing, malformed,
unbound, or the chain read fails. A contract regression proves that an agent with an active
BAA for hospital A is rejected when it supplies a different registered hospital B. This is
source/local evidence; deployed Base Sepolia behavior was not re-verified in this pass.

> This is the same hole as the missing **authority** clause: the field is client-supplied
> precisely because there is no delegation lookup. Formalized (invariants A1–A5) in
> [`thesis-extensions-formal.md`](archive/2026-08/thesis-extensions-formal.md) — enforcing
> A1/A2 turns the field from an assertion into a resolution and closes this item.

---

## P1 — Required for the system to behave as documented

9. **[DONE] Identity-ceiling clamp** (Appendix A gap 5). The authoritative scoring engine
    now applies `AIS_final = min(AIS, ceiling)` for every tier, including the 1000-point
    maximum after a ZK boost. Unknown/negative tiers fall back to the Tier-0 ceiling, and
    the normalized constraint score is capped by the same ladder. Focused scoring-core
    coverage passes.
10. **Silence-as-signal — source complete; policy is opt-in** (gap 8). The oracle exposes
    `anchor_coverage` (`no_activity`, `current`, or `stale`) with event count and last-anchor
    metadata. Operators may set `AIS_ANCHOR_STALE_PENALTY_BPS` (0 by default) to apply a
    bounded penalty to active agents with stale coverage; no-activity remains neutral and
    the normalized constraint input is unchanged. A dispute trigger still requires a
    separate multi-period operational policy.
11. **Lineage attestation** (gap 6) — **source complete; deployment/adoption open**. The
    append-only `AgentLineageRegistry` records one controller-authorized `forked_from`,
    `migrated_from`, or `recovered_from` edge between registered agents and preserves the
    attestor and timestamp. Local Forge coverage passes; deploy the registry for each
    network and route fork/migration/recovery workflows through it before closing this gate.
12. **[DONE] Remove or hard-gate testnet convenience.** SDK registration rejects non-testnet
    automatic funding/minting and requires explicit `ALLOW_TESTNET_CONVENIENCE=true` on Base
    Sepolia; production callers must pass zero convenience amounts and pre-fund through an
    approved path. A source audit found no `VITE_DEV_AUTO_LOGIN_*`, `scripts/seed_mock_data.py`,
    or dashboard Vite middleware capable of executing `make demo`; `vite.config.ts` contains
    only the Shield development proxy. The production dashboard build completes without any
    of those development-only surfaces.
13. **BCC gate fail-open scope** — **source complete; live production observation open**.
    Quarantine reads now fail closed for configured value-moving, privileged, credential,
    and clinical intent classes, while low-risk reads continue to the authoritative OPA
    decision during an RPC/oracle outage. The class policy is configurable via
    `BCC_QUARANTINE_FAIL_CLOSED_INTENTS`; focused quarantine coverage passes. A live
    deployment still needs an observed deny for an affected class before this gate closes.
14. **Single RPC dependency.** `publicnode` is one endpoint with no failover; the oracle's
    chain reads are the source of truth for registration and scoring.

---

## P2 — Operational, before real users

15. **External security audit** of `contracts/` — mandatory before value is at risk, and it
    should happen *after* items 1–8 land, or it audits the wrong system.
16. **CI covers what matters.** Workflows exist (`ci.yml` + 3 others); confirm they run
    forge/cargo/pytest/vitest on every PR and that the opt-in `ORACLE_E2E` suite runs
    somewhere regularly rather than never.
17. **Monitoring and alerting** on: oracle liveness, RPC failure rate, anchor-submission
    failures, score-update failures, and BCC deny rate.
18. **PHI handling review** for Integrity Health: retention, backups, the redaction backstop's false-negative
    rate, and breach procedure. This is a legal obligation, not an engineering preference.
19. **Key custody and rotation runbook** for every signer from item 1, including what
    happens when the oracle signer is compromised at 3am.

---

## Explicitly not blockers

- The Cognition/dashboard work, the XNS handle surface, and telemetry volume — product
  polish, not trust-chain correctness.
- `integrity-userapi` — an off-chain convenience layer, deliberately outside the trust
  domain.
- The remaining `[PLANNED]` wiki concepts (ZK-ML, A2A negotiation, cross-chain sync) — these
  are roadmap, and are marked as such.

---

## Suggested order

1. Item 6 (upgradeability decision) — gates everything, costs nothing but thought.
2. Items 1, 5, 7 — the on-chain authority model, settled together in one deploy.
3. Items 2, 3, 4, 8 — correctness of the proof and signature paths.
4. Item 15 (audit) — once the above is stable.
5. P1/P2 in parallel with the audit window.
