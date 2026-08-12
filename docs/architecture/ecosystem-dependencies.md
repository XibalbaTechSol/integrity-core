# Ecosystem Dependencies

This document is the canonical cross-repository dependency map for integrity-core,
Xibalba Cortex, Xibalba Shield, and Integrity MVP.

```text
integrity-mvp (React/Vite presentation and operator workflow layer)
├── xibalba-cortex (local cognitive store, provenance, session roots)
│   └── integrity-core (BCC middleware, StateAnchor, protocol evidence)
├── xibalba-shield (endpoint sensor, local policy enforcement, evidence producer)
│   └── integrity-core (integrity-sdk, BCC middleware, Oracle, contracts)
└── integrity-core (Oracle, user API, BCC middleware, contracts)
```

## Ownership and runtime boundaries

| Project | Owns | Consumes |
|---|---|---|
| `integrity-core` | Integrity SDK, BCC policy and commitment pipeline, Oracle/AIS, user API, protocol contracts and chain conventions | No Shield, Graph Memory, or MVP code |
| `xibalba-cortex` | Local memory store, recall, provenance, session hash/Merkle evidence, graph traversal, local viewer/API | Public integrity-core anchoring interfaces only; no protocol authority |
| `xibalba-shield` | Endpoint discovery, local security policy enforcement, guardrail hooks, endpoint evidence production | `integrity-sdk` plus integrity-core BCC, telemetry, Oracle, and chain interfaces |
| `integrity-mvp` | Web presentation and operator workflows | integrity-core APIs/contracts directly; graph-memory service data; Shield evidence and security workflows |

Xibalba Shield is therefore built on integrity-core. It is a separate product and repository,
not a replacement backend and not the Integrity Health vertical. Shield feeds signed security
decisions into the protocol, where integrity-core verifies, scores, and anchors them.

Xibalba Cortex is the local cognitive store. It can produce session roots and provenance
evidence for anchoring through integrity-core, but recalled memory is not instruction authority
and local memory hashes do not replace protocol verification.

Integrity MVP uses all three backend surfaces. Protocol-wide identity, reputation, telemetry,
BCC, user, and chain data come from integrity-core. Local memory/provenance views originate in
Xibalba Cortex. Endpoint-security discovery, enforcement, and evidence originate in Xibalba
Shield and become visible to the MVP through the shared integrity-core trust pipeline.

## Dependency rules

1. integrity-core must not import, call, or require Xibalba Shield or Integrity MVP.
2. integrity-core must not import, call, or require Xibalba Cortex for protocol
   correctness.
3. Xibalba Cortex may cite or anchor evidence through public integrity-core interfaces,
   but it must not implement a parallel protocol authority or present recalled text as trust.
4. Xibalba Shield must use the same public SDK and protocol interfaces available to any other
   Integrity consumer; it receives no privileged backend path.
5. Integrity MVP may call integrity-core services directly and present Graph Memory and Shield
   workflows, but it does not own protocol scoring, anchoring, endpoint enforcement, or memory
   truth.
6. A Graph Memory, Shield, or MVP failure must not alter integrity-core scoring, BCC
   canonicalization, Merkle conventions, chain schemas, or protocol anchoring.

The normative Shield boundary is defined in
[`../../spec/xibalba-shield-v1.md`](../../spec/xibalba-shield-v1.md). Cross-package wire shapes
inside integrity-core remain governed by
[`../INTERFACE_CONTRACT.md`](../INTERFACE_CONTRACT.md).
