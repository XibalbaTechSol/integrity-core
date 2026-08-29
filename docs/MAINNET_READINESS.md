# Mainnet readiness — what must be done first

Status reconciled 2026-08-17. Scope: what stands between the current Base Sepolia deployment
and a mainnet launch that the protocol's own claims would survive. Every item below is
either verified against code/chain in this repo or cites where it is recorded.

The accepted normative baseline remains `docs/archive/2026-08/integrity-protocol-v0.4.md`.
`docs/archive/2026-08/integrity-protocol-v0.5-proposed.md` and explanatory Whitepaper v3.2 describe proposed
changes and do not relax any blocker in this document. Phase 0's local
`IntegrityIdentityReadV1` singleton and the generated local ZK verifier both postdate the
declared Base Sepolia deployment; source capability is not deployed capability.

Ordering is by consequence-if-ignored, not by effort.

---

## P0 — Blockers. Launching without these makes a protocol claim false.

### 1. Key separation: six protocol roles are one EOA

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
roles back from chain post-deploy, not from the deploy script.

### 2. The deployed ZK verifier is older placeholder bytecode that always reverts

The current local `contracts/src/oracle/UltraPlonkVerifier.sol` is generated verifier source
and has local proof-path coverage. The verifier address in the existing Base Sepolia deployment,
however, still contains the earlier fail-closed placeholder bytecode. That deployment cannot
execute the ZK reputation-boost path. A local source replacement does not update deployed code.

**Done when:** the generated verifier is independently reviewed, deployed through an approved
incremental migration, a real proof and an invalid proof are exercised against the deployed
address, and deployment records plus direct bytecode/behavior readback agree. Local generation
and tests satisfy only the source/test layers of that requirement.

### 3. ZK boost is period-wide, not bound to what it proves

> **Note:** if the three-primitive consolidation is adopted
> ([`three-foundational-primitives.md`](archive/2026-08/three-foundational-primitives.md)),
> this stops being a scoring detail and becomes a hole in a *foundational* primitive —
> reputation — and should move up this list accordingly.

Spec v0.3 §9.4, confirmed in `scoring-core`: the boost is a `BOOL_OR` over the reporting
window. One verified proof anywhere in ~30 days multiplies the entire period's score by
1.15. The proof is real; the *binding* between proof and the behavior being scored is not.

**Done when:** the boost derives from proof-bearing events (or the proof's public inputs
commit to the scoring window), and a test demonstrates that a proof for event A cannot
boost unrelated event B. Appendix A gap 4.

### 4. Two cross-language canonicalization divergences in signed payloads

Both are recorded in `PRODUCTION_GAPS.md` §17 and `bcc.py`'s canonicalization docstring:

- **Floats:** Python and Rust disagree on shortest-representation for some values, so a
  caller-supplied float in telemetry metadata can produce different canonical bytes on each
  side and be rejected (~20% rejection was observed and partially fixed for SDK-generated
  floats only).
- **Non-ASCII:** Python's `ensure_ascii=True` escapes; Rust's `serde_json` does not by
  default. The oracle carries a custom `AsciiEscapingFormatter` for its own path, but this
  is two independent implementations of "canonical JSON," not one specification.

On testnet this is an annoyance. On mainnet, a signature that verifies on one side and not
the other is a correctness failure in the trust chain itself.

**Done when:** both sides implement one specified standard — RFC 8785 (JCS) mandates
ECMAScript `Number::toString`, which is deterministic — with a shared cross-language
conformance vector set in CI. This is an `INTERFACE_CONTRACT.md` §4.2 change across SDK,
CLI, middleware, and oracle.

### 5. Persistent memory: enforcement is half-built and existing agents don't conform

Recorded in `PRODUCTION_GAPS.md` §19. The registration gate is live (`400
MemoryNotInitialized`), but:

- `StateAnchor.anchorRoot` is `onlyRole(ANCHOR_ROLE)` at *every* epoch, and registration
  grants that role to the oracle signer — so the protocol can anchor an agent's genesis
  root, which spec §7.2 forbids. The agent-authorized path works; it just isn't *exclusive*.
- All 7 Sepolia agents, including `xibalba.integrity`, report `latestRoot == 0`.

**Done when:** genesis anchoring is contract-enforced as agent-only (see §6 below — this is
the one that must be right *before* first mainnet deploy, because it cannot be patched
afterwards), and no registered agent has a zero root.

### 6. Upgradeability — decided, then reopened the same day; see comparison before building

`SovereignAgent` and `StateAnchor` are deployed **directly per agent**, not cloned from an
upgradeable implementation. Every agent's copy is frozen at whatever bytecode shipped that
day. This is already biting on testnet: the §7.2 fix in item 5 cannot reach the 7 existing
agents at all.

On mainnet this means **any bug in those two contracts is permanent for every agent
registered before the fix**, with no migration path short of re-registering under a new DID
and losing the reputation history the protocol exists to preserve.

**Decision:** beacon proxy with a per-agent pin; beacon owned by a multisig at launch and
transferred to `IntegrityGovernance` once ITK supply is constrained (governance votes are
locked ITK, and ITK is mintable today, so the handover is meaningless until then). Full
rationale, contract shape, and accepted consequences:
[`docs/design/upgradeability-decision.md`](design/upgradeability-decision.md).

Registry rotation was considered and rejected: stake, ITK balance, market positions, and
`isRegisteredAgent` all key on the *address*, so rotation is a value migration plus a
laundering vector, where a proxy simply keeps the address stable.

**Reopened:** a third option — frozen contracts with swappable *policy* behind designed-in
hooks (the pattern `VerifierRegistry` already uses) — was under-weighted. It fixes §7.2,
avoids permanently adopting the storage-collision vulnerability class in the contracts
holding agent funds, and bounds a compromised authority key to denial-of-service rather
than theft. [`docs/design/upgradeability-comparison.md`](design/upgradeability-comparison.md)
currently recommends switching to it. **Settle this before writing any proxy code.**

**Done when:** beacons are deployed by `Deploy.s.sol`, the SDK deploys proxies rather than
raw contracts, storage-layout discipline (reserved gaps, append-only) is in place on both
implementations, and the oracle reports each agent's implementation address so pinned or
stale agents are visible.

### 7. Bonded stake is not enforced at registration

Spec §4.5's "internalization of consequences" is the mechanism that makes slashing mean
anything. `Slasher` and the dispute path exist, but no uniform minimum stake is required to
register (Appendix A gap 3), so an agent can hold a score while risking nothing.

**Done when:** registration enforces a minimum bond, and tier elevation requires more.

### 8. `covered_entity_address` is client-supplied (Integrity Health / HIPAA)

Spec §9.4 names this as a spoof residual. In the healthcare vertical, the field asserting
which covered entity an action falls under is taken from the caller. Under HIPAA this is
the highest-consequence field in the payload.

**Done when:** the covered-entity binding is verified on-chain (`CoveredEntityRegistry` /
`SmartBAA`) rather than trusted from the request, and a test proves a forged
`covered_entity_address` is rejected.

> This is the same hole as the missing **authority** clause: the field is client-supplied
> precisely because there is no delegation lookup. Formalized (invariants A1–A5) in
> [`thesis-extensions-formal.md`](archive/2026-08/thesis-extensions-formal.md) — enforcing
> A1/A2 turns the field from an assertion into a resolution and closes this item.

---

## P1 — Required for the system to behave as documented

9. **Identity-ceiling clamp is not applied** (Appendix A gap 5). `docs` and spec §12
   advertise tier ceilings of 600/850/1000; scoring does not clamp, so a Tier-1 agent can
   report a score its tier is supposed to forbid. Either enforce `AIS_final = min(AIS,
   ceiling)` or stop publishing the ladder as if it binds.
10. **Silence-as-signal** (gap 8). An agent that stops reporting while still acting is
    currently indistinguishable from an idle one — the exact failure observability exists to
    catch.
11. **Lineage attestation** (gap 6). No fork/migration/recovery path, which interacts
    directly with item 6.
12. **Remove or hard-gate every testnet convenience.** Each is correct for testnet and
    dangerous on mainnet:
    - registration auto-mints ITK and auto-funds wallets from the funder
    - `integrity-dashboard/vite.config.ts` exposes a dev-server middleware that executes
      `make demo` on POST — dev-only, but confirm it cannot ship in a built asset
    - `VITE_DEV_AUTO_LOGIN_*` auto-session
    - `scripts/seed_mock_data.py`
13. **BCC gate fails open per-process, not per-intent-class.** Reads failing open is fine;
    a contract write or deploy failing open is not. Needs per-class policy, plus a real
    observed DENY (the allow path is exercised; the deny path never has been).
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
