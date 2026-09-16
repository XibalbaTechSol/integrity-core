# Integrity Dashboard — Product and Interaction Specification

Status: design baseline for the protocol control center

## Product position

Integrity Dashboard is the trusted operational surface for the Integrity Protocol. It has four responsibilities:

1. expose authoritative protocol and cryptographic provenance;
2. bind human-readable views to one verified ERC-8004 agent identity;
3. present the agent treasury without exposing secrets;
4. expose only contract administration that the current identity, signer, network, and authority can prove.

The dashboard is not a generic business analytics suite, a chat surface, a key-export tool, or an authorization oracle. AIS is evidence, not permission.

## Information architecture and sitemap

```text
Integrity Dashboard
├── Overview
│   ├── Current agent identity and ERC-8004 binding
│   ├── ETH / ITK treasury summary
│   ├── Verification summary and security warnings
│   ├── Recent transactions and signed intents
│   ├── Recent roots, hashes, proofs, and receipts
│   └── Owned-contract summary
├── Agent Identity
│   ├── ERC-8004 registration and identifier
│   ├── DID / protocol identity reference
│   ├── SovereignAgent and controller relationship
│   ├── Verification tier and registration evidence
│   └── Recent signed actions
├── Integrity Records
│   ├── Schema records and payload hashes
│   ├── BCC intents and signatures
│   ├── Merkle leaves, roots, and inclusion paths
│   ├── Anchors, attestations, receipts, and provenance links
│   └── Expandable raw schema / canonical JSON
├── Proofs & Verification
│   ├── ZK proof summary and public inputs
│   ├── Merkle inclusion verification
│   ├── Signature and nonce verification
│   ├── Issuer / recipient / verifier chain
│   └── Verification history and failure reasons
├── Wallet
│   ├── ITK and ETH balances
│   ├── Agent treasury address and network
│   ├── Redacted credential / vault status
│   ├── Send and receive flows
│   └── Gas and transaction preflight
├── Transactions
│   ├── Pending, confirmed, failed, rejected
│   ├── Transaction detail and receipt
│   ├── Input / output / gas / nonce
│   └── Block and explorer provenance
├── Contracts
│   ├── Owned / controlled / administered contracts
│   ├── Deployment and verification metadata
│   ├── Roles, permissions, proxies, and implementation
│   ├── Configuration and recent events
│   └── Permission-aware administrative actions
├── Security & Keys
│   ├── Controller, device, signer, and agent relationship
│   ├── Key fingerprint and vault status
│   ├── Rotation / recovery / backup status
│   ├── Connected signer and network checks
│   └── Security alerts and denied actions
└── Activity Log
    ├── Identity changes
    ├── Signed intents and verification transitions
    ├── Wallet and contract actions
    └── Security and permission events
```

Legacy aliases `/agents` → `/identity` and `/evidence` → `/records` are redirects, not separate product surfaces.

## Overview wireframe

```text
┌──────────────────────────────────────────────────────────────────────────┐
│ Integrity  Protocol Core        [selected agent] [refresh] [signer state] │
├───────────────┬──────────────────────────────────────────────────────────┤
│ Overview       │ Protocol state: network | ERC-8004 | proofs | live data  │
│ Agent Identity │                                                          │
│ Records        │ Selected identity                 Treasury               │
│ Proofs         │ DID / agent / controller          ETH / ITK              │
│ Wallet         │ registration + verification       vault state             │
│ Transactions   │                                                          │
│ Contracts      │ Evidence chain: intent → hash → root → proof → receipt   │
│ Security       │                                                          │
│ Activity       │ Owned contracts and recent activity                       │
└───────────────┴──────────────────────────────────────────────────────────┘
```

The default view is summary-first. Every technical value has an expandable raw detail or provenance link. A value is never shortened without retaining copy and inspect actions.

## Visual direction

- Background: true dark graphite/navy, not black and not neon.
- Surfaces: flat blue-black panels with one-pixel structural borders.
- Accent: restrained protocol blue for links and focus; green only for confirmed state; amber for pending; red for failed/revoked; gray for unavailable.
- Typography: strong sans-serif hierarchy for meaning, compact monospace for hashes, addresses, signatures, blocks, nonces, and JSON.
- Geometry: mostly square or lightly rounded 3–4px controls; no ornamental crypto imagery, glows, gradients, or decorative motifs.
- Density: desktop-first technical console; tables and evidence chains are primary; cards are reserved for identity, treasury, and state summaries.
- Responsive rule: desktop uses a persistent rail; tablet collapses the rail to a labeled menu; narrow screens stack panels and preserve horizontal scrolling for technical tables.
- Focus: every interactive control has a visible focus ring and a text label or accessible name.

Accepted visual concept: `/home/xibalba/.codex/generated_images/01a0a41a-5a75-7170-9757-421c3a13b5ee/exec-b9fc13df-c322-48dd-a2b2-b8074c9a7209.png`.

## Reusable component system

### Identity and provenance

| Component | Required behavior |
|---|---|
| `IdentityHeader` | Shows agent name, avatar, ERC-8004 ID, network, registration state, and current selection. |
| `AuthorityPath` | Separates agent, SovereignAgent, controller, device, signer, and vault; never merges addresses by resemblance. |
| `ProvenanceValue` | Label, redacted value, source tier, timestamp, copy, inspect, and source link. |
| `SchemaDisclosure` | Human summary first; expandable canonical JSON/schema, hash algorithm, version, and raw fields second. |
| `StatusState` | One of confirmed, pending, failed, rejected, revoked, expired, unavailable, or permission denied. Includes text, not color alone. |

### Cryptographic evidence

| Component | Required behavior |
|---|---|
| `EvidenceChain` | BCC intent → signature → payload/content hash → Merkle leaf/root → inclusion proof → ZK proof → receipt/anchor. |
| `HashValue` | Algorithm, exact hash, truncation, copy, and full-value disclosure. |
| `SignatureRecord` | Issuer, recipient, key reference, algorithm, nonce, timestamp, domain, and verification result. |
| `MerkleProofPanel` | Root, leaf, index, sibling path, tree version, generated-at, verifier source, and independent result. |
| `ZkProofPanel` | Circuit/version, verifier, public inputs, proof reference, verification time, and on-chain/off-chain distinction. |
| `VerificationTimeline` | State transitions with actor, timestamp, source, and failure reason. |

### Wallet and contracts

| Component | Required behavior |
|---|---|
| `BalanceRow` | Asset, exact balance, reliable price source or “price unavailable,” block freshness, and source. |
| `AddressBlock` | Address, role, network, checksum, copy, QR action, and verified relationship. |
| `CredentialStatus` | Redacted fingerprint, vault/provider, last rotation, backup/recovery state; never a secret. |
| `TransactionRow` | Hash, asset, amount, state, nonce, time, signer, and explorer link. |
| `TransactionReview` | Exact target, function/value/data, asset/amount, gas estimate, signer, chain ID, warnings, and confirmation. |
| `ContractRecord` | Address, type, deployment, source verification, owner/controller, roles, proxy implementation, events, and capabilities. |
| `PermissionGate` | Read-only, authorized write, unresolved authority, wrong network, missing signer, and blocked states. |

## State language and data provenance

Every record carries a source label: `on-chain`, `Oracle`, `Cortex`, `local vault`, `external verifier`, `pending`, or `unavailable`.

| State | Meaning | Allowed action |
|---|---|---|
| Confirmed | Independently verified by the authoritative source | Show normal inspect/write actions if authority also passes |
| Pending | Submitted or resolving, but not final | View progress; do not describe as valid/final |
| Failed | Verification or execution failed | Show reason and recovery path; no retry loop by default |
| Rejected | User, signer, policy, or chain rejected it | Preserve reason; allow deliberate re-review |
| Revoked | Previously valid relationship is no longer valid | Disable dependent actions |
| Expired | Validity window ended | Show historical record; require new proof/intent |
| Unavailable | Source could not be reached or identity cannot resolve | Read-only empty state; never infer |
| Permission denied | Source resolved but current actor lacks authority | Hide or disable writes; explain required authority |

## Key user flows

### Review agent identity

Select agent → resolve ERC-8004 registration → resolve DID and SovereignAgent → verify controller/device relationship → show source and freshness → inspect signed actions and alerts. Any missing relationship is `unavailable` or `not confirmed`, never “owned.”

### Verify Merkle or ZK proof

Open record → inspect root/leaf or circuit/public inputs → select independent verification → show exact verifier, version, inputs, timestamp, and result → preserve failed result and reason. Off-chain Oracle verification and on-chain attestation are separate evidence paths.

### Inspect BCC intent

Open intent → show canonical intent fields → show nonce, domain, issuer, recipient, intended-state hash, signature, and BCC leaf → verify signature and replay status → link to resulting transaction/receipt if independently correlated.

### Send ITK or ETH

Choose asset → validate recipient checksum and network → enter amount → estimate gas → simulate/preflight → show exact signer and agent treasury → confirmation screen → explicit irreversible warning → request external/hardware/vault signature → submit → show pending receipt → independently verify confirmed/failure state.

### Receive ETH

Open Wallet → select agent treasury address → verify network and role → copy or show QR → warn that the address is a contract treasury if applicable → show incoming transaction only after chain confirmation.

### Review failed transaction

Open transaction → show hash/status/receipt → decode revert or rejection reason → show signer, nonce, chain, target, and gas → distinguish user rejection, simulation failure, RPC failure, and on-chain revert → never silently retry.

### Inspect and administer a contract

Open Contracts → filter by owned/controlled/administered → verify owner/controller/role from authoritative chain reads → show read-only or write capability → for writes, run permission and network preflight → confirmation screen with exact function and parameters → sign externally → display receipt and post-state verification.

### Review wallet/key status

Open Security & Keys → show redacted fingerprint, vault/provider, signer availability, last rotation, backup/recovery state, device binding, and alerts → never show seed/private key material → actions are rotate, revoke, or recover only when the configured secure provider exposes an approved flow.

## Transaction and contract security specification

Before any write, all gates must pass:

1. selected agent identity is resolved;
2. agent treasury address is authoritative and checksum-valid;
3. controller/signer relationship is independently verified;
4. connected chain ID equals the selected network;
5. target contract and function are known and ABI-compatible;
6. caller has the required owner/controller/role permission;
7. parameters pass schema and address/amount validation;
8. simulation or preflight succeeds, or the UI explicitly says it is unavailable;
9. gas estimate and fee source are fresh;
10. user confirms exact transaction details and irreversible consequences;
11. external signer/vault approves and signs;
12. receipt and resulting state are independently read back.

If any gate is unknown, the action is read-only or blocked. AIS, similar-looking addresses, a cached role, or a client-side flag can never authorize a write.

## Responsive and accessibility contract

- Desktop: 220px rail, two-column overview, full evidence chain, dense tables.
- Tablet: 72px icon rail with accessible labels, one-column detail panels, tables retain horizontal scroll.
- Narrow: stacked identity/treasury/evidence/contract regions, controls wrap, hashes remain monospace and copyable, no horizontal page overflow.
- Keyboard: logical tab order, visible focus, Escape closes disclosures/modals, Enter activates links/buttons.
- Screen readers: status is text plus icon, tables have headers, every copy/inspect control has an accessible label, and loading/failed updates use live regions.
- Reduced motion: disable spinner and transition animation while preserving state changes.

## Implementation boundary

The current dashboard can safely render read-side protocol data and external signer connection state. ETH/ITK transfers, vault-backed key management, QR generation, transaction simulation, role-aware writes, and receipt verification require authoritative backend/provider contracts before their controls are enabled. Until those contracts exist, the UI must show unavailable or permission-denied states rather than simulate success.
