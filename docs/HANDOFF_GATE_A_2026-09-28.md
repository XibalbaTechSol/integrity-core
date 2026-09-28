# Handoff: Gate A after A6

**Date:** 2026-09-28
**Repository:** `integrity-core`
**Authority:** [`docs/EXECUTION_PLAN.md`](EXECUTION_PLAN.md)
**Current status:** A6 complete; Gate A not passed

## Outcome at handoff

The execution plan is at **78/201 checkboxes (38%)**. A0, A1, A2, A3, A4, A5, and A6 are
complete. A6 delivered the eight local-first seams without billing or hosted-service
dependencies:

- tenant/organization identity and tenant-scoped agent/device registration;
- signed pack hash/version pinning;
- durable signed-receipt queueing;
- offline pack and receipt verification;
- Cortex-compatible provider/store identity;
- tenant-scoped entitlement and capability checks;
- aggregate-only usage and audit metrics.

Merged A6 PRs: #118, #119, #120, #121, #122, #123, and #124.

## Next objective: Gate A

Gate A is a local trust-boundary gate, not a production or mainnet claim. It has 2/12 items
complete:

- **Complete:** kernel mediation checks; local signed receipt creation, signing, and verification.
- **Open — Builds:** relevant suites, import hygiene, Shield/Cortex independence CI, console build,
  cut-path manifest, and one SDK JCS implementation across active repositories.
- **Open — Shield:** signed/enforced pack hash equality; tamper/malformed/stale/incompatible-pack
  refusal; per-class no-match defaults; deny on malformed/unknown/evaluator-error decisions; no raw
  command content in exports; distinct device and agent keys.
- **Open — Cortex:** reject unauthenticated OTLP; prove provenance export; bind `content_hash` on
  create events.
- **Open — Identity:** prove no private key exists under any harness root in tests or pilot fixtures.
- **Open — Docs:** every active normative document has one authority; superseded material is in
  `integrity-lab`; no active repository has a competing plan or architecture register.

Do not mark Gate A passed from source-only or mock evidence. Keep local, live-service, Oracle/BCC,
public-chain, and production evidence labeled separately.

## Useful validation commands

From `/home/xibalba/Projects/integrity-core`:

```bash
python3 scripts/plan_progress.py
python3 scripts/check_docs.py
python3 scripts/wiki_toc.py --check
uv run --directory integrity-sdk pytest -q
```

The focused A6 SDK tests have passed through the merged PRs. A full-suite result and the Gate A
cross-repository matrix are still required before claiming the gate.

## Working-tree and runtime safety

- The current checkout may contain a pre-existing user edit in
  `integrity-sdk/integrity_sdk/did.py`; preserve it and do not stage it unless explicitly requested.
- Work from a new branch based on `origin/main`; do not rewrite or force-push merged A6 branches.
- The Shield checkout is a live editable install used by a systemd eBPF enforcement service. Do not
  checkout branches or leave incomplete changes in `/home/xibalba/Projects/xibalba-shield`.
- Keep Gate A validation local-first. Do not restart live services or broadcast transactions as part
  of source/test validation.

## Recommended next sequence

1. Inventory the Gate A build and cross-repository commands from the execution plan.
2. Run the relevant SDK, Shield, Cortex, console, BCC, and Oracle suites independently, recording
   exact commands and results.
3. Add or repair only the missing Gate A evidence/tests, preserving existing dirty work.
4. Validate Shield and Cortex boundaries against local services and clearly label unavailable external
   evidence as unverified.
5. Update `STATUS.md`, `docs/EXECUTION_PLAN.md`, and this handoff only after evidence is fresh.
