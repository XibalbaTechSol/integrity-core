# Integrity ecosystem

**Status:** current architecture summary
**Authority:** repository boundaries and product relationships; implementation sequencing remains
in [`docs/EXECUTION_PLAN.md`](docs/EXECUTION_PLAN.md).

Integrity is the trust substrate. Shield and Cortex are independent products that consume
stable SDK contracts and remain useful when Oracle, public-chain, vendor, or hosted services are
unavailable.

## Boundaries

| Surface | Responsibility | Must not become |
|---|---|---|
| Integrity core | SDK, identity, packs, receipts, verification, anchoring, AIS | A runtime availability bottleneck for products |
| Shield | On-device policy enforcement, device control, signed evidence, exports | The Cortex memory authority |
| Cortex | Governed memory, content, provenance, retention, retrieval | The AIS or receipt authority |
| Console | Operator UI and user-facing API | A merged product authority |
| Lab | Frozen mirror for removed, historical, or deferred material | A runtime dependency |

## Local-first operating rule

Shield continues local enforcement during external outages. Cortex continues local storage and
retrieval while anchoring is unavailable. Receipts and evidence may queue for later anchoring;
external registration and hosted integrations enhance evidence but do not define local operation.

## Shared contracts

The SDK owns the shared trust-bearing contracts:

- JCS canonical bytes for newly migrated hashes and signatures;
- DID-file identity, separate from device and agent signing keys;
- signed packs whose signatures cover every evaluated file;
- fail-closed decision resolution and signed, chained receipts;
- local verification and queued anchoring;
- memory-provider and data-boundary interfaces.

Shield and Cortex may add product behavior around these contracts, but may not create a second
authority for identity, packs, receipts, verification, anchoring, AIS, or canonicalization.

## Extension boundary

Third-party adapters and packs are deterministic, versioned, and off-chain. They declare
capabilities, data requirements, supported versions, control citations, and decision vectors.
They cannot override deny, sign or anchor evidence, change kernel parameters outside the pack
contract, or bypass tenant boundaries.

For sequencing and evidence, use the execution plan and the package source/tests rather than
this summary.
