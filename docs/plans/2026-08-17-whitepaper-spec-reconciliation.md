# Whitepaper and Normative Specification Reconciliation Plan

> **Status:** Executing

**Goal:** Separate the explanatory Integrity Protocol Whitepaper v3.1 from the normative specification while preserving traceable proposed changes and honest implementation status.

**Architecture:** `spec/integrity-protocol-v0.4.md` remains the current normative baseline. A new `spec/integrity-protocol-v0.5-proposed.md` records the v3.1 changes as a proposed normative amendment, with explicit acceptance and implementation-status boundaries. The whitepaper remains non-normative and links to the proposal.

## Tasks

1. Create the proposed v0.5 normative amendment from Appendix D of the v3.1 draft.
2. Add a relationship and authority section to the whitepaper.
3. Replace language that presents whitepaper changes as already normative with proposed-change language.
4. Update `spec/README.md` with the document hierarchy and proposal status.
5. Regenerate and verify the designed PDF.
6. Append evidence to the canonical wiki log.

## Acceptance criteria

- No whitepaper section is treated as authoritative over the normative specification.
- Proposed changes are individually traceable to v3.1 sections and marked `[PROPOSED]` where not accepted or implemented.
- Current implementation gaps remain visible.
- The PDF has no browser-generated header and preserves the designed logo/equation treatment.
