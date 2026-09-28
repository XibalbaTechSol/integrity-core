# ADR-0002: Mainnet readiness boundary

- **Status:** Accepted current summary
- **Date:** 2026-09-28
- **Decision owner:** Integrity protocol maintainers

## Decision

Mainnet readiness is a gated deployment decision, not a consequence of local source,
testnet, or simulated evidence. This ADR is the current bounded summary of that decision.
The detailed consequence-ordered register is preserved at
[`docs/archive/2026-09/MAINNET_READINESS.md`](../archive/2026-09/MAINNET_READINESS.md).

The normative protocol remains [`docs/SPEC.md`](../SPEC.md), and sequencing remains owned by
[`docs/EXECUTION_PLAN.md`](../EXECUTION_PLAN.md). `STATUS.md` may summarize these boundaries
but does not replace them.

## Current boundary

| Gate area | Current state | Boundary for a mainnet claim |
|---|---|---|
| Deployment and adoption | Source-complete in places; deployment-open | Base Sepolia artifacts, existing agents, and migration paths require independent deployment and adoption verification. Local or testnet proof is not deployed proof. |
| Signer custody and role separation | Open | Protocol roles and privileged keys require separated ownership, custody, rotation, and recovery controls. |
| Verifier, proof, and coverage adoption | Open | The deployed verifier and proof-submission path must be verified against real supported proofs, with negative controls and coverage evidence. |
| Operational controls | Open | External security review, CI/E2E coverage, monitoring, incident response, legal/PHI review, and key-custody evidence remain required. |
| Local-first operation | Required invariant | Shield, Cortex, and Integrity must remain usable during Oracle, public-chain, vendor, or hosted-service outages; queued receipts are not mainnet settlement proof. |

## Consequence

No mainnet broadcast, production registration, or readiness claim is authorized by this ADR.
Closing a row requires fresh evidence at the relevant deployment, custody, verifier, or
operational boundary and must be reflected in the execution plan and status summary.

## References

- [`STATUS.md`](../../STATUS.md) — bounded current-state summary
- [`PRODUCTION_GAPS.md`](../../PRODUCTION_GAPS.md) — detailed open gaps
- [`docs/SPEC.md`](../SPEC.md) — normative protocol authority
- [`docs/EXECUTION_PLAN.md`](../EXECUTION_PLAN.md) — execution authority
- [`docs/archive/2026-09/MAINNET_READINESS.md`](../archive/2026-09/MAINNET_READINESS.md) — historical detailed register
