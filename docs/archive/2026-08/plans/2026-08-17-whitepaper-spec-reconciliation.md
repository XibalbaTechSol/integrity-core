# Whitepaper and Normative Specification Reconciliation Plan

> **Status:** Complete locally; proposed clauses still require separate acceptance

**Goal:** Separate the explanatory Integrity Protocol Whitepaper v3.2 from the accepted normative specification while preserving traceable proposed changes and honest implementation status.

**Architecture:** `spec/integrity-protocol-v0.4.md` remains the current normative baseline. The new `spec/integrity-protocol-v0.5-proposed.md` records the v3.2 proposal set as a proposed normative amendment, with explicit acceptance and implementation-status boundaries. `spec/integrity-protocol-v3.2.md` remains non-normative and links to the proposal; its PDF is generated publication output.

## Tasks

1. [x] Create the proposed v0.5 normative amendment and map it to the v3.2 source.
2. [x] Add a relationship and authority section to the whitepaper.
3. [x] Replace language that presents whitepaper changes as already normative with proposed-change language.
4. [x] Update `spec/README.md` with the four-layer document hierarchy and proposal status.
5. [x] Reconcile implementation status, including AIS fail-closed defaults and the Phase 0 identity read profile.
6. [x] Regenerate and verify the v3.2 PDF after the final source reconciliation.
7. [x] Append final generation and verification evidence to the canonical wiki log.

## Acceptance criteria

- [x] No whitepaper section is treated as authoritative over the normative specification.
- [x] Proposed changes are individually traceable to v3.2 sections and marked `[PROPOSED]` where not accepted or implemented.
- [x] Current implementation gaps remain visible.
- [x] The PDF has no browser-generated header and preserves readable diagram/equation treatment.
