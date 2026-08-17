---
title: Test-Status Tree Binding and Vault Evidence
acronyms: []
created: 2026-08-13
updated: 2026-08-13
type: concept
tags: [provenance, compliance, infrastructure]
confidence: high
source_files:
  - scripts/tree_hash.py
  - scripts/record_test_status.py
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

At leaf creation, a missing status is recorded as `unverified`; a status for a different tree is
recorded as `unverified:stale`; only a matching status file is hashed into the leaf as test-result
evidence.

## Verification and limits

The deterministic self-test on 2026-08-13 passed 4/4:

```text
python3 scripts/tree_hash.py --self-test
4/4 passed
```

The test covers commit-boundary stability, untracked-file exclusion, tracked-content sensitivity,
and stability across a second commit. This verifies the local fingerprint algorithm only. It does
not establish external anchoring, successful remote delivery, or that every historical leaf was
created from a matching test status.
