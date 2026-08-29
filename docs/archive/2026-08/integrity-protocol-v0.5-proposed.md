# Integrity Protocol — Proposed Normative Amendment v0.5

**Status:** `[PROPOSED]` — not yet accepted as the active normative specification

**Source proposal:** [Integrity Protocol Whitepaper v3.2](integrity-protocol-v3.2.md), including the v3.1 foundation and the v3.2 amendment register in Appendix D

**Current normative baseline:** [Integrity Protocol v0.4](integrity-protocol-v0.4.md)

**Date:** 2026-08-17 (implementation-evidence addendum to §4.1/§4.3 added same day, below)

---

## 1. Authority and status

This document is a proposed normative amendment to `integrity-protocol-v0.4.md`. It does not replace v0.4 until the proposal is explicitly accepted through repository review and the implementation, interface-contract, production-gap, and wiki records are reconciled.

The Whitepaper v3.2 is explanatory and non-normative. It may motivate, summarize, or illustrate the proposal, but it cannot amend the protocol by itself. If this proposal is rejected or revised, the whitepaper must be updated to match the accepted decision.

The following status vocabulary is mandatory in this document:

- `[PROPOSED]` — described as a candidate requirement; not yet accepted as the active protocol rule.
- `[PARTIAL]` — some supporting behavior exists, but the full requirement is not implemented or verified.
- `[PLANNED]` — no implementation claim is made.
- `[ACCEPTED]` — approved as a normative rule and incorporated into the active specification.

All clauses below are `[PROPOSED]` unless a later acceptance record changes their status.

## 2. Scope of the amendment

This proposal covers the v3.1 foundation and v3.2 amendments that affect protocol semantics:

1. Identity is an Integrity interface obligation. Native ERC-8004 deployment is optional, and a custom Integrity read profile MUST NOT be described as ERC-8004-compatible unless it implements the standard's selector semantics exactly.
2. Agent Integrity Score (AIS) reputation input is derived from admissible evidence, fails closed when evidence is absent, and uses declared component floors with a conjunctive gate.
3. The constraint input uses the normalised pre-boost AIS base score; the display score and constraint score are separate objects.
4. Memory commitments use injective canonical encoding and typed evidence classes.
5. Memory payload storage is governed by an availability obligation rather than a mandatory storage technology.
6. Append-only memory supports redact-before-commit and supersession, not post-commit erasure.
7. Memory continuity is an enforceable constraint on licensed consumption.
8. Host-side observability is explicitly untrusted and cannot be part of the on-chain containment guarantee.
9. Ungated legacy execution paths are non-compliant with complete mediation, not partially compliant.
10. The trusted single-operator AIS oracle may migrate only through a versioned, threshold-signed telemetry-prover profile; ZK telemetry remains a research horizon.
11. Memory availability requires challenge economics and deterministic consequences, not only an unenforced promise to produce data.
12. Liveness degradation may contract soft bounds but MUST NOT bypass hard invariants, AIS floors, or settlement-time checks.
13. High-frequency execution may use state channels and compiled declarative adapters only with injective commitments, mediated settlement, and an explicit compiler trust boundary.
14. Attested host containment complements on-chain mediation but MUST NOT be described as extending the on-chain complete-mediation proof to plaintext or host egress.

Whitepaper §1.5's comparative architecture and §10.4's enabler framing are explanatory arguments,
not independently testable protocol clauses. Economic, deployment, and roadmap statements remain
non-normative unless separately accepted through a future specification change.

## 3. Proposed identity interface obligation

### 3.1 Required properties

An identity substrate MUST provide:

- portability across supported key-rotation events;
- verifiable resolution within the execution-gate resource budget;
- a stable subject identifier to which constraints, evidence, and history bind;
- an unambiguous mapping between the resolved subject and the mediated account.

### 3.2 Identity profiles and ERC-8004 compatibility

An implementation MAY satisfy the identity interface through either:

- native registration in the relevant ERC-8004 registries; or
- a durable implementation-owned registry with a versioned Integrity read profile.

The second route satisfies this proposal's Integrity identity properties only. It
MUST NOT be advertised as ERC-8004 or ERC-721 compatible unless the required
selectors, token identity, ownership, transfer, wallet-proof, metadata, event, and
interface-detection semantics are implemented and verified selector by selector.

An adapter MUST NOT expose a second independently computed reputation value. The protocol MUST maintain one authoritative reputation source for the identity subject.

**Implementation status:** `[PARTIAL — LOCAL, NOT DEPLOYED]` — `contracts/src/kernel/IntegrityIdentityReadV1.sol` provides a tested read-only discovery facade over `XibalbaAgentRegistry`, keyed by DID hash and `SovereignAgent` address. It fails closed on non-bijective or declaration-mismatched mappings, exposes live candidate-controller checks, and requires no migration of existing agents. It is informed by a pinned ERC-8004 draft revision but explicitly non-conformant: no token identifier, ERC-721 ownership or transfer, wallet proof, metadata write, reputation feedback, validation, event, or ERC-165 surface is claimed. Native ERC-8004 convergence and Base Sepolia deployment remain deferred. This implementation evidence does not make this proposed amendment authoritative.

## 4. Proposed AIS evidence and gating rules

### 4.1 Evidence admissibility

A scored component MUST be computed only from evidence independently verifiable by at least one of:

- server-side recomputation from signed raw span content;
- chain-state observation;
- an attestation from a configured staked validator or trusted execution environment (TEE);
- a third-party signed decision record accepted under configured trust roots.

An agent's own assertion about a component MUST NOT be sufficient evidence for that component. A component with no admissible evidence MUST evaluate to zero, not to a neutral or maximum default.

### 4.2 Gated weighted geometric mean

Let each component satisfy $S_\bullet \in [0,1000]$, with weights
$w_E=0.30$, $w_G=0.30$, $w_S=0.20$, and $w_C=0.20$, and declared floors $S_\bullet^{\mathrm{floor}}$.

The proposed base score is:

$$
\mathrm{AIS}_{\mathrm{base}} =
\left[\prod_{\bullet}\Theta\left(S_\bullet-S_\bullet^{\mathrm{floor}}\right)\right]
\cdot \prod_{\bullet}S_\bullet^{w_\bullet}.
$$

The reputation input used by constraint schedules MUST be:

$$
r(\iota)=\frac{\mathrm{AIS}_{\mathrm{base}}}{1000}\in[0,1].
$$

The assurance multiplier MUST remain outside this reputation input. A display score MAY report a boosted value, but integrations MUST NOT normalise the boosted display score into a constraint schedule.

Holding the admissibility classification, component floors, weights, and other component values fixed, increasing any one admissible component MUST NOT decrease $\mathrm{AIS}_{\mathrm{base}}$ or $r(\iota)$. Conformance vectors MUST exercise this monotonicity requirement above and below every declared floor.

### 4.3 Component evidence classes

| Component | Required admissible evidence | Missing evidence |
|---|---|---|
| Entropy | Server-side recomputation from raw span content | Score `0` |
| Grounding | Server-side recomputation from raw span content | Score `0` |
| Sacrifice | Validator or TEE attestation of compute | Score `0` |
| Compliance | Independent gate reads, validator attestation, or trusted signed decision record | Score `0` |

The distinction between absent evidence and evidence showing failure MUST be preserved in evidence-class and margin telemetry even though both resolve to zero for the score.

**Implementation status:** `[PARTIAL]` — fail-closed AIS defaults and zero-component admissibility are implemented locally, while the remaining v3.2 profile, evidence-admissibility, floor, and migration requirements still require clause-level acceptance and implementation evidence.

**Implementation evidence (2026-08-17), landed against clause 4.1's "no admissible evidence MUST evaluate to zero" only — clause 4.2's gate/floors are not yet implemented, see below:**

| Clause 4.1 requirement | Code path | Test |
|---|---|---|
| Entropy: no admissible evidence ⇒ 0 | `integrity-oracle/backend/src/derive.rs::derive_entropy` | `derive::tests::empty_batch_entropy_and_grounding_fail_closed_to_zero` |
| Grounding: no admissible evidence ⇒ 0 | `integrity-oracle/backend/src/derive.rs::derive_grounding` | `derive::tests::empty_batch_entropy_and_grounding_fail_closed_to_zero` |
| Self-reported compliance signal: no admissible evidence ⇒ 0 | `integrity-oracle/backend/src/derive.rs::self_reported_compliance` | `derive::tests::self_reported_compliance_empty_batch_fails_closed_to_zero` |
| Same three, client-side mirror | `integrity_sdk/telemetry/derive.py::derive_entropy`, `derive_grounding`, `derive_compliance` | `integrity-sdk/tests/unit/test_derive.py::test_derive_entropy_empty_batch_fails_closed_to_zero` and siblings |
| Attack-scenario regression (content-bearing token count, no analysable text) | both of the above modules | `derive::tests::content_free_submission_with_token_counts_fails_closed_on_entropy_and_grounding` (Rust); `test_content_free_submission_with_token_counts_fails_closed_on_entropy_and_grounding` (Python) |

**Not yet evidenced — do not read the table above as clause 4 being implemented:** compliance still admits the scored agent's own self-report as sole evidence for non-healthcare agents (violates 4.1's "an agent's own assertion... MUST NOT be sufficient"); sacrifice still has no validator/TEE attestation requirement; clause 4.2's declared floors and conjunctive Θ gate do not exist in `scoring-core`; and the pre-boost, clamped `r(ι)` accessor clause 4.2 requires as the constraint input is not exposed — `scoring-core::AisBreakdown::ais` remains the only reported value, post-boost and unclamped. Full detail: `PRODUCTION_GAPS.md` §27.

### 4.4 Versioned AIS profile and migration

The proposed algorithm MUST be identified by an explicit profile identifier, for example `ais/v0.5-gated-geometric-1`. A consumer MUST NOT reinterpret a historical v0.4 `ais` value as a v0.5 `AIS_base` or `r(\iota)` value.

A score record MUST carry its profile identifier, component evidence references, pre-boost base score when available, assurance multiplier, and display score as separate fields. Historical v0.4 scores remain verifiable under the v0.4 profile but are not automatically comparable with v0.5-proposed scores. Consumers making authorization decisions across profiles MUST define a migration policy or fail closed.

Conformance requires published vectors covering zero/missing evidence, floor failure, geometric aggregation, assurance boost separation, tier ceilings, and profile mismatch.

**Status:** `[PLANNED]` — profile identifiers, migration policy, and conformance vectors are not yet accepted or implemented.

## 5. Proposed memory commitment rules

### 5.1 Canonical injective encoding

Memory commitments MUST use a canonical injective encoding. The encoding MUST bind at least:

- schema identifier;
- subject identifier;
- sequence number;
- evidence class;
- increment payload;
- prior commitment.

The encoding MUST reject ambiguous field tuples and non-finite numeric values. A length-prefixed or canonical sorted-key encoding is conforming only when its injectivity is defined and testable.

### 5.2 Typed evidence classes

Each increment MUST carry an evidence class from a closed, versioned set. At minimum, implementations SHOULD distinguish:

`declared_intent`, `observed_event`, `extracted_proposition`, `inference`, `summary`, and `policy`.

Relying parties MUST be able to filter evidence by class. An inference MUST NOT be silently treated as an observed event or a signed declared intent.

### 5.3 Availability obligation

A memory-chain holder MUST be able to produce the genesis state and increments needed to verify the anchored head within a declared challenge window. Failure to produce the required payload within that window MUST be an adverse evidence event under the applicable dispute rules.

The protocol does not mandate IPFS, Arweave, Filecoin, or another particular storage technology. Storage technology is an implementation choice; production availability and challenge handling are the protocol obligation.

### 5.4 Retraction and supersession

Sensitive material MUST be redacted before it is committed. A committed increment MUST NOT be post-hoc edited while preserving the original chain as though no edit occurred.

A later increment MAY supersede an earlier increment. Supersession preserves chain verifiability and records that the earlier material is no longer relied upon. A deployment MUST define how relying parties interpret superseded increments.

**Implementation status:** `[PARTIAL]` — the reference memory implementation provides relevant canonical commitment and redact-before-commit behavior; challenge-window enforcement and complete supersession semantics remain open unless separately verified.

### 5.5 Versioned memory commitment profile and migration

The proposed encoding MUST use an explicit profile identifier and domain separator, for example `memory/v0.5-injective-1`. Existing v0.4 roots remain verifiable under their legacy profile and MUST NOT be reinterpreted as roots produced by the new profile.

A migration MAY append a new-profile checkpoint that references the verified legacy head. It MUST NOT rewrite historical legacy roots or claim that a new-profile checkpoint proves an unverified legacy history. Cross-domain readers MUST identify the profile before validating or comparing roots.

Conformance requires vectors for both legacy and proposed encodings, including ambiguous field tuples, field-length boundaries, schema/subject binding, evidence-class binding, and profile mismatch.

**Status:** `[PLANNED]` — profile identifiers, migration behavior, and conformance vectors are not yet accepted or implemented.

## 6. Proposed complete-mediation rule

A deployment claiming the containment guarantee MUST route every state-changing execution path through the verification kernel, including direct execution, executor modules, fallback handlers, batches, module installation, and module removal.

An account retaining an ungated state-changing path is non-compliant with the guarantee. It MUST NOT be described as partially covered by the guarantee.

Legacy accounts with an ungated execution path MAY continue to operate outside the guarantee, but their deployment and documentation MUST identify that boundary explicitly.

**Implementation status:** `[PLANNED]` for the v3 execution-firewall architecture.

## 7. Proposed memory-continuity constraint

Where a licensed action carries a memory head, the submitted head MUST extend the anchored head for the relevant subject and license context. A divergent or forked head MUST cause the mediated action to revert before the licensed state transition commits.

The extension check MUST bind the relevant subject, license identifier, chain/domain context, and anchored head. A declaration that memory is continuous without an enforceable pre-check is insufficient.

**Implementation status:** `[PLANNED]` for the v3 kernel and metered-IP architecture.

## 8. Proposed host-observability boundary

Host-side sensors, process monitors, file monitors, network monitors, and host-side policy agents are untrusted inputs to the on-chain containment proof unless they independently satisfy a future attestation profile.

Host-side systems MAY:

- produce signed evidence for forensics;
- provide local best-effort containment;
- provide informational signals to an adapter.

Host-side systems MUST NOT be described as completing on-chain mediation, as the licence meter, or as an assurance tier solely because they attest to themselves.

A future attested-host profile requires, at minimum, a hardware root of trust, remote code-integrity attestation, freshness with expiry, and complete published sensor coverage for the claimed control boundary.

**Implementation status:** `[PARTIAL]` — the boundary is specified here; the future attested-host profile is `[PLANNED]`.

## 9. Proposed telemetry-prover decentralization

The current single-operator AIS oracle MUST remain classified as a Trusted component. Server-side
recomputation reduces client self-report risk but does not make the operator decentralized or
attested.

A future federated telemetry-prover profile MUST define:

- the validator set and threshold $M$-of-$N$;
- the exact typed score/evidence payload each validator signs;
- profile/version and replay-domain binding;
- aggregation, disagreement, timeout, rotation, and revocation behavior;
- stake or other accountable consequence for objectively invalid attestations; and
- conformance vectors for threshold success, equivocation, stale signatures, and insufficient quorum.

ZK telemetry for general LLM adherence is a research horizon, not an accepted roadmap phase or
current assurance claim.

**Implementation status:** `[PLANNED]` — the current oracle remains a single-operator Trusted
boundary; no federated threshold profile or general ZK-telemetry prover is implemented.

## 10. Proposed stake-secured memory availability

An availability obligation used for forensic redress MUST bind a declared availability stake,
challenge identifier, subject, commitment profile, anchored head, deadline, and expected payload
digest. A response succeeds only when canonical recomputation of the produced payload matches the
challenged commitment.

The availability stake MUST satisfy $S_{DA} \ge \alpha_{DA}\max_i(\mathrm{ValueAtRisk}(a_i))$ under the active constraint schedule, with the coverage ratio, exposure valuation, and update rules declared by profile. A challenger MUST post a declared anti-grief deposit bound to the challenge; the profile MUST define its return or forfeiture on every resolution path.

Failure to produce, malformed production, or digest mismatch after the deadline MUST deterministically set the authoritative AIS/reputation input for the subject to zero (thereby forcing soft bounds to their floors), pay the challenger its deposit plus the declared liquidated-damages fraction of $S_{DA}$, and burn the remaining stake. The recipient, amount, timing, appeal/finality rule, and interaction with the protocol's capital-cost constraints MUST be specified before acceptance; implementations MUST NOT replace these transitions with operator discretion.

**Implementation status:** `[PLANNED]` — canonical commitments exist in related memory work, but
no accepted availability-stake instrument, challenge contract, or deterministic slashing path is
implemented in integrity-core.

## 11. Proposed circuit-breaker grace modes

Constraints MUST be partitioned into hard invariants and soft operational bounds. Missing or stale
telemetry MUST NOT relax a hard invariant. A grace mode MAY only contract the action set available
under the last valid soft bound; it MUST NOT expand authority.

Every balance delta, token transfer, and withdrawal MUST be classified as a hard invariant; an adapter MUST NOT downgrade a value-moving operation into the soft partition.

AIS floors govern before grace. Grace MUST NOT move a bound below its declared minimum or above the
bound authorized by the last valid AIS profile. Any staging buffer MUST evaluate hard invariants at
settlement and cap release at the bound in force when the action was staged.

Each adapter MUST publish its hard/soft classification, contraction function, freshness window,
recovery rule, and tests proving stale input cannot expand the reachable action set.
Entering grace mode or tripping a breaker MUST emit a typed, indexed degradation event that binds at least the adapter/profile identifier, resulting mode, and telemetry age so monitoring can distinguish and order the transition.

**Implementation status:** `[PLANNED]` — no execution kernel or grace-mode adapter exists.

## 12. Proposed high-frequency execution profile

A high-frequency profile MAY batch actions in a state channel only against a locked on-chain budget ceiling. Each transition MUST advance an injective, domain-separated commitment binding channel, subject, sequence, prior head, action, applicable policy version, cumulative value, and remaining budget. The accepted state MUST be the highest-sequence state mutually signed by the required channel parties. Verification MUST prove monotone budget depletion and value conservation. Channel settlement MUST pass through the same mediated account boundary as a direct action, MUST reject stale, forked, or out-of-order heads, and MUST permit unilateral settlement of the highest valid mutually signed state after the declared challenge window.

A declarative adapter compiler is a Trusted component until reproducible builds, versioned source
semantics, compiler identity, generated-artifact hashes, and conformance vectors establish a
stronger profile. Generated adapters MUST NOT claim more authority than the reviewed source policy.

**Implementation status:** `[PLANNED]` — no ATCP/IP state-channel profile or `integrity-dsl`
compiler exists in this repository.

## 13. Proposed hybrid attested-host boundary

An attested enclave MAY complement the on-chain kernel only when the attestation is bound to the
specific transaction, freshness expires, and the relevant egress control is inside the measured
boundary. The attestation MUST identify the measured code/profile and the verifier trust roots.

This joint deployment covers two distinct attack surfaces. It does not extend the on-chain proof of
complete account-state mediation to plaintext handling, host software, external peripherals, or
egress outside the measured enclave. Documentation MUST preserve that distinction.
The profile MUST explicitly disclose residual trusted-execution-environment limitations, including side-channel, rollback, and microarchitectural risk; attestation MUST NOT be represented as an unconditional confidentiality guarantee.

**Implementation status:** `[PLANNED]` — no production attested-host profile satisfying these
conditions is implemented or deployed.

## 14. Acceptance and implementation gates

This proposal MUST NOT be marked `[ACCEPTED]` until all of the following are recorded:

1. reviewer decision accepting, rejecting, or modifying each clause;
2. update to the active normative specification and interface contract;
3. implementation status in `PRODUCTION_GAPS.md`;
4. focused regression tests for changed formulas, canonical encoding, evidence admissibility, memory continuity, and complete-mediation boundaries;
5. canonical wiki page and append-only wiki-log update;
6. regenerated whitepaper language that matches the accepted decision;
7. independent verification of the exact source and generated PDF artifacts.

Until then, v0.4 remains the active normative baseline, and this document remains a traceable proposal.

## 15. Change mapping

| Proposed clause | Whitepaper source | Current status |
|---|---|---|
| Identity interface obligation | §3.1, §3.1.4 | `[PROPOSED]` / `[PARTIAL]` |
| AIS admissibility, gate, and verified-evidence monotonicity | §3.1.1–§3.1.4 | `[PROPOSED]` / `[PARTIAL]` |
| Injective memory encoding | §3.2 | `[PROPOSED]` / `[PARTIAL]` |
| Typed evidence classes | §3.2 | `[PROPOSED]` / `[PARTIAL]` |
| Memory availability | §3.2.1 | `[PROPOSED]` / `[PARTIAL]` |
| Retraction/supersession | §3.2.2 | `[PROPOSED]` / `[PARTIAL]` |
| Memory-continuity constraint | §5.4 | `[PROPOSED]` / `[PLANNED]` |
| Complete mediation | §2.4 and §4.5 | `[PROPOSED]` / `[PLANNED]` |
| Host-observability boundary | §9.4 | `[PROPOSED]` / `[PARTIAL]` |
| Telemetry-prover decentralization | §3.1.5 | `[PROPOSED]` / `[PLANNED]` |
| Stake-secured memory availability, anti-grief deposit, and deterministic redress/burn | §3.2.5 | `[PROPOSED]` / `[PLANNED]` |
| Circuit-breaker grace modes, hard value partition, typed events, and AIS-floor precedence | §4.7–§4.7.5 | `[PROPOSED]` / `[PLANNED]` |
| High-frequency budgeted state channel, unilateral settlement, and compiler trust | §7.5 | `[PROPOSED]` / `[PLANNED]` |
| Per-transaction hybrid attested-host boundary and residual TEE limitations | §9.5 | `[PROPOSED]` / `[PLANNED]` |
| Comparative architecture and enabler framing | §1.5 and §10.4 | Explanatory only; no independent normative clause |
