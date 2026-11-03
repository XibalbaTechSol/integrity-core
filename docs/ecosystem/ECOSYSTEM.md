# Xibalba Ecosystem Authority

This document defines the product and authority boundaries for the four active repositories. The execution sequence is defined in `INTEGRITY_ECOSYSTEM_PLAN.md`; current gaps are defined in `STATUS.md`; data handling is defined in `DATA.md`; individual architectural decisions are defined in ADRs.

## Products

- **Integrity/kernel:** identity, signed packs, receipts, verification, anchoring, and on-chain value enforcement.
- **Shield:** on-device policy enforcement, device control, evidence generation, and compliance exports.
- **Cortex:** tenant-scoped memory/content, provenance, retention, retrieval, and memory proofs.
- **Console:** operator UI and user-facing API for the products; it does not become an authority over Shield, Cortex, or Integrity.

Shield and Cortex remain independently deployable and monetizable. They depend on Integrity-compatible identity, pack, receipt, and verification contracts, but do not require public-chain or Oracle availability for local enforcement or retrieval.

## Authority map

| Claim | Authority |
|---|---|
| Whether an action is allowed | Shield/BCC policy receipt |
| Whether a receipt is authentic and chained | SDK receipt verifier |
| Whether content was stored | Cortex content/provenance store |
| Whether memory was available at spot-check time | Cortex retrieval proof |
| Whether a root was anchored | StateAnchor |
| Authoritative AIS | Oracle/scoring-core; local AIS is self-reported feedback |
| Optional Jev recommendation | Jev annotation only; never policy authority |

## Evidence boundary

Source inspection, build/test evidence, local runtime evidence, live service evidence, Oracle/BCC evidence, public-chain evidence, and production evidence are separate classes. A missing external service is reported as unavailable or unverified, not as zero or absent.

## Extensibility

Pure pack adapters are deterministic and offline. Network-facing integrations are connectors with separate credentials, egress policy, and redacted records. Neither can override deny, sign enforcement receipts, anchor evidence, or bypass tenant boundaries. There is no on-chain adapter registry in v1.
