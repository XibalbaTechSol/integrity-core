# Integrity Protocol — Proposed Normative Amendment v0.5

**Status:** `[PROPOSED]` — not yet accepted as the active normative specification

**Source proposal:** [Integrity Protocol Whitepaper v3.2](integrity-protocol-v3.2.md) (superseded v3.1's copy of the same clauses at §3.1–§3.1.5; the AIS gate/floor definitions this document tracks did not change between the two revisions)

**Current normative baseline:** [Integrity Protocol v0.4](integrity-protocol-v0.4.md)

**Date:** 2026-08-17 (implementation-evidence addendum to §4.1/§4.3 added same day, below)

---

## 1. Authority and status

This document is a proposed normative amendment to `integrity-protocol-v0.4.md`. It does not replace v0.4 until the proposal is explicitly accepted through repository review and the implementation, interface-contract, production-gap, and wiki records are reconciled.

The Whitepaper v3.1 is explanatory and non-normative. It may motivate, summarize, or illustrate the proposal, but it cannot amend the protocol by itself. If this proposal is rejected or revised, the whitepaper must be updated to match the accepted decision.

The following status vocabulary is mandatory in this document:

- `[PROPOSED]` — described as a candidate requirement; not yet accepted as the active protocol rule.
- `[PARTIAL]` — some supporting behavior exists, but the full requirement is not implemented or verified.
- `[PLANNED]` — no implementation claim is made.
- `[ACCEPTED]` — approved as a normative rule and incorporated into the active specification.

All clauses below are `[PROPOSED]` unless a later acceptance record changes their status.

## 2. Scope of the amendment

This proposal covers the v3.1 changes that affect protocol semantics:

1. Identity is an interface obligation; native ERC-8004 registry deployment is not mandatory when an ERC-8004-shaped adapter exposes equivalent durable identity properties.
2. Agent Integrity Score (AIS) reputation input is derived from admissible evidence, fails closed when evidence is absent, and uses declared component floors with a conjunctive gate.
3. The constraint input uses the normalised pre-boost AIS base score; the display score and constraint score are separate objects.
4. Memory commitments use injective canonical encoding and typed evidence classes.
5. Memory payload storage is governed by an availability obligation rather than a mandatory storage technology.
6. Append-only memory supports redact-before-commit and supersession, not post-commit erasure.
7. Memory continuity is an enforceable constraint on licensed consumption.
8. Host-side observability is explicitly untrusted and cannot be part of the on-chain containment guarantee.
9. Ungated legacy execution paths are non-compliant with complete mediation, not partially compliant.

Economic, deployment, and roadmap statements in the whitepaper remain non-normative unless separately accepted through a future specification change.

## 3. Proposed identity interface obligation

### 3.1 Required properties

An identity substrate MUST provide:

- portability across supported key-rotation events;
- verifiable resolution within the execution-gate resource budget;
- a stable subject identifier to which constraints, evidence, and history bind;
- an unambiguous mapping between the resolved subject and the mediated account.

### 3.2 ERC-8004 compatibility

An implementation MAY satisfy the identity interface through either:

- native registration in the relevant ERC-8004 registries; or
- a durable implementation-owned registry with an ERC-8004-shaped read adapter.

An adapter MUST NOT expose a second independently computed reputation value. The protocol MUST maintain one authoritative reputation source for the identity subject.

**Implementation status:** `[PARTIAL]` — the existing durable registry and adapter direction require verification against this proposed interface; native ERC-8004 convergence is not claimed.

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

### 4.3 Component evidence classes

| Component | Required admissible evidence | Missing evidence |
|---|---|---|
| Entropy | Server-side recomputation from raw span content | Score `0` |
| Grounding | Server-side recomputation from raw span content | Score `0` |
| Sacrifice | Validator or TEE attestation of compute | Score `0` |
| Compliance | Independent gate reads, validator attestation, or trusted signed decision record | Score `0` |

The distinction between absent evidence and evidence showing failure MUST be preserved in evidence-class and margin telemetry even though both resolve to zero for the score.

**Implementation status:** `[PARTIAL]` — the current implementation requires the v3.1 implementation delta to enforce all admissibility and floor rules.

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

## 9. Acceptance and implementation gates

This proposal MUST NOT be marked `[ACCEPTED]` until all of the following are recorded:

1. reviewer decision accepting, rejecting, or modifying each clause;
2. update to the active normative specification and interface contract;
3. implementation status in `PRODUCTION_GAPS.md`;
4. focused regression tests for changed formulas, canonical encoding, evidence admissibility, memory continuity, and complete-mediation boundaries;
5. canonical wiki page and append-only wiki-log update;
6. regenerated whitepaper language that matches the accepted decision;
7. independent verification of the exact source and generated PDF artifacts.

Until then, v0.4 remains the active normative baseline, and this document remains a traceable proposal.

## 10. Change mapping

| Proposed clause | Whitepaper source | Current status |
|---|---|---|
| Identity interface obligation | §3.1, §3.1.4 | `[PROPOSED]` / `[PARTIAL]` |
| AIS admissibility and gate | §3.1.1–§3.1.4 | `[PROPOSED]` / `[PARTIAL]` |
| Injective memory encoding | §3.2 | `[PROPOSED]` / `[PARTIAL]` |
| Typed evidence classes | §3.2 | `[PROPOSED]` / `[PARTIAL]` |
| Memory availability | §3.2.1 | `[PROPOSED]` / `[PARTIAL]` |
| Retraction/supersession | §3.2.2 | `[PROPOSED]` / `[PARTIAL]` |
| Memory-continuity constraint | §5.4 | `[PROPOSED]` / `[PLANNED]` |
| Complete mediation | §2.4 and §4.5 | `[PROPOSED]` / `[PLANNED]` |
| Host-observability boundary | §9.4 | `[PROPOSED]` / `[PARTIAL]` |
