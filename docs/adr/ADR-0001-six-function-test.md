---
title: Six-function test for ecosystem changes
status: accepted
date: 2026-09-28
---

# ADR-0001: Six-function test

## Decision

Every new component, contract, adapter, document, or product surface must name the function it
advances and the gate it satisfies. The six functions are:

| Function | Current implementation boundary |
|---|---|
| Identity | DID files, IntegrityAccount, registry, and XNS |
| Rules | Signed packs and deterministic adapters |
| Enforcement | Shield/BCC off-chain and the kernel on-chain |
| Evidence | Signed receipts, StateAnchor roots, and offline verification |
| Feedback | Oracle/scoring-core AIS |
| Access | SDK, CLI, and hooks |

## Consequences

This test prevents duplicate authorities and makes scope decisions reviewable. A component that
does not advance one of the six functions is deferred or treated as product/UI support rather
than added to the trust substrate. Naming a function does not prove implementation; the relevant
source, tests, and runtime evidence still define the claim boundary.

## References

- [`docs/EXECUTION_PLAN.md`](../EXECUTION_PLAN.md)
- [`ECOSYSTEM.md`](../../ECOSYSTEM.md)
- [`DATA.md`](../../DATA.md)
