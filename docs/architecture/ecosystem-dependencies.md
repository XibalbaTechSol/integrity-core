# Ecosystem Dependencies

This document is the canonical cross-repository dependency map for INTEGRITY-LATEST,
Xibalba Shield, and Integrity MVP.

```text
integrity-mvp (React/Vite presentation layer)
├── xibalba-shield (endpoint sensor, local policy enforcement, evidence producer)
│   └── INTEGRITY-LATEST (integrity-sdk, BCC middleware, Oracle, contracts)
└── INTEGRITY-LATEST (Oracle, user API, BCC middleware, contracts)
```

## Ownership and runtime boundaries

| Project | Owns | Consumes |
|---|---|---|
| `INTEGRITY-LATEST` | Integrity SDK, BCC policy and commitment pipeline, Oracle/AIS, user API, protocol contracts and chain conventions | No Shield or MVP code |
| `xibalba-shield` | Endpoint discovery, local security policy enforcement, guardrail hooks, endpoint evidence production | `integrity-sdk` plus INTEGRITY-LATEST BCC, telemetry, Oracle, and chain interfaces |
| `integrity-mvp` | Web presentation and operator workflows | INTEGRITY-LATEST APIs/contracts directly; Shield evidence and security workflows |

Xibalba Shield is therefore built on INTEGRITY-LATEST. It is a separate product and repository,
not a replacement backend and not the Integrity Health vertical. Shield feeds signed security
decisions into the protocol, where INTEGRITY-LATEST verifies, scores, and anchors them.

Integrity MVP uses both layers as its backend surface. Protocol-wide identity, reputation,
telemetry, BCC, user, and chain data come from INTEGRITY-LATEST. Endpoint-security discovery,
enforcement, and evidence originate in Xibalba Shield and become visible to the MVP through the
shared INTEGRITY-LATEST trust pipeline.

## Dependency rules

1. INTEGRITY-LATEST must not import, call, or require Xibalba Shield or Integrity MVP.
2. Xibalba Shield must use the same public SDK and protocol interfaces available to any other
   Integrity consumer; it receives no privileged backend path.
3. Integrity MVP may call INTEGRITY-LATEST services directly and present Shield workflows, but
   it does not own protocol scoring, anchoring, or endpoint enforcement.
4. A Shield failure must not alter INTEGRITY-LATEST scoring or Merkle conventions. An MVP
   failure must not interrupt either backend layer.

The normative Shield boundary is defined in
[`../../spec/xibalba-shield-v1.md`](../../spec/xibalba-shield-v1.md). Cross-package wire shapes
inside INTEGRITY-LATEST remain governed by
[`../INTERFACE_CONTRACT.md`](../INTERFACE_CONTRACT.md).
