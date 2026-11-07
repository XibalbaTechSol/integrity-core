# Xibalba Ecosystem Authority

**Status:** Current Architecture & Authority Specification  
**Authority:** Product relationships and operational boundaries across the four active repositories.  
**Related Documents:**
- [`INTEGRITY_ECOSYSTEM_PLAN.md`](INTEGRITY_ECOSYSTEM_PLAN.md) — Implementation sequencing and phase gates
- [`DATA.md`](DATA.md) — Data retention, purge, and evidence boundaries
- [`STATUS.md`](STATUS.md) — Active implementation gaps

---

## Products & Roles

1. **`integrity-core` (The Physics Engine of the Machine Economy):**
   - Implements the Autonomous Integrity Score (AIS) as the native reward function ($R_{\text{total}} = R_{\text{task}} + \lambda \cdot \text{AIS}$).
   - Governs on-chain DIDs (`did:integrity`), signed BCC packs, receipts, verification, Merkle state anchoring, and execution-firewall enforcement.
   - Computes authoritative reputation and processes slashing on invariant violations.

2. **`xibalba-cortex` (The Navigational Engine):**
   - Governed neuro-symbolic knowledge graph and active inference engine.
   - Enforces geometric graph traversal (R-GCN + TKGE/TransE) and dynamic logit masking ($z_{\text{masked}} = z \circ M + (-\infty \times (1 - M))$).
   - Ingests biomedical research, EHR records, and economic indicators; performs temporal event reification.
   - Traverses verified edges; computes session Merkle roots anchored into `integrity-core`.

3. **`xibalba-shield` (Cryptographic Topology & Response Governance):**
   - Enforces topological boundary gating, ensuring zero probability of reaching unauthorized states.
   - Provides vendor-neutral EDR response governance (CrowdStrike, Defender, SentinelOne) and agent execution gating (MCP, SOAR).
   - *"The EDR detects and acts; Shield proves who authorized it."*
   - Produces signed, tamper-evident action receipts and HIPAA compliance assurance.

4. **`integrity-console` (The Universal Verifiable Operator Window):**
   - Independent operator presentation and account layer.
   - Renders live graph navigation trajectories, multi-agent DID verification tiers, AIS distributions, and real-time response approval queues.
   - Holds no protocol authority; verifies all state cryptographically against `integrity-core`.

---

## Authority Map

| Claim | Authority |
|---|---|
| Whether an action is permissible | Shield boundary gate & BCC policy receipt |
| Whether an EDR remediation is authorized | Shield Response Gateway with signed hash-bound intent |
| Whether a receipt is authentic and chained | SDK receipt verifier |
| Whether content was stored | Cortex content and provenance store |
| Whether memory/path existed at spot-check time | Cortex retrieval proof and topological edge trace |
| Whether a root was anchored | `StateAnchor` contract |
| Authoritative AIS | Oracle/scoring-core; local AIS is self-reported feedback |
| Health economic cost friction | Cortex CMS fee schedule weighting |

---

## Evidence Boundary

Source inspection, build/test evidence, local runtime evidence, live service evidence, Oracle/BCC evidence, public-chain evidence, and production evidence are separate classes. A missing external service is reported as unavailable or unverified, not as zero or absent.

## Extensibility

Pure pack adapters are deterministic and offline. Network-facing integrations are connectors with separate credentials, egress policy, and redacted records. Neither can override deny, sign enforcement receipts, anchor evidence, or bypass tenant boundaries.
