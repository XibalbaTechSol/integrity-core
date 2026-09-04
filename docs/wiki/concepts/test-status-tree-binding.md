---
title: Test-Status Tree Binding and Vault Evidence
acronyms: []
created: 2026-08-13
updated: 2026-09-01
type: concept
tags: [provenance, compliance, infrastructure]
confidence: high
source_files:
  - scripts/tree_hash.py
  - scripts/record_test_status.py
  - scripts/test_status_schema.py
  - scripts/vault_commit_leaf.py
  - PRODUCTION_GAPS.md
---

## Table of contents

- [Purpose](#purpose)
- [Current implementation](#current-implementation)
- [Verification and limits](#verification-and-limits)

## Purpose

A local test result must not be attached to a different source tree. The test-status recorder and
Trust Vault leaf writer therefore share `scripts/tree_hash.py` rather than maintaining separate
fingerprint algorithms.

## Current implementation

`tree_hash(repo)` hashes the path and SHA-256 digest of every tracked file and returns a
Keccak-256 fingerprint. Untracked files are excluded because they are not part of the committed
tree being attested. Both `record_test_status.py` and `vault_commit_leaf.py` import this function.

`make test` starts an explicit schema-v2 run with a unique run identifier and names all eight
expected suites. Each suite result stores the tree hash observed when that suite finishes;
finalization succeeds only when the exact expected suite set exists and every result names the
current tracked tree. Suite failures are recorded without aborting later suites, then finalization
returns a failing exit after the complete result set is persisted. File locking, run-identifier
matching, and atomic replacement prevent concurrent invocations from mixing or exposing partial
JSON. Finalization never re-stamps an older suite result onto a newer tree. Legacy, malformed,
partial, mixed-tree, cross-run, and unknown-tree status documents fail closed rather than being
silently migrated. The leaf consumer accepts only the shared `integrity-core-root-v1` profile and
its exact eight-suite set; internally consistent custom or reduced runs remain unverified.

At leaf creation, the consumer independently revalidates schema version, finalization state,
expected-suite completeness, per-suite tree binding, outcomes, and the derived overall result. A
missing or invalid status is recorded as `unverified`; an explicit status for a different tree is
recorded as `unverified:stale`; only a consistent finalized status file is hashed into the leaf.

## Verification and limits

The deterministic tree-hash self-test recorded on 2026-08-13 passed 4/4:

```text
python3 scripts/tree_hash.py --self-test
4/4 passed
```

The test covers commit-boundary stability, untracked-file exclusion, tracked-content sensitivity,
and stability across a second commit. This verifies the local fingerprint algorithm only. It does
does not establish external anchoring, successful remote delivery, or that every historical leaf was
created from a matching test status. Focused schema-v2 regressions additionally cover mixed-tree
rejection, complete-run finalization, incomplete and legacy documents, invalid outcomes,
post-finalize invalidation, consumer-side consistency checks, and explicit stale classification.
