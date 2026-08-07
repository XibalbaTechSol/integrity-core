# Xibalba Shield — Technical Specification

**Version 1.0** · Device & Network Security · Agentic Guardrails · Integrity-Backed Evidence
Xibalba Solutions — a Trust Layer consumer, not a trust layer of its own

Companion to [`spec/integrity-protocol-v0.4.md`](integrity-protocol-v0.4.md) §14. That document
is normative for Integrity Protocol; this document is normative for **Xibalba Shield**, a
separate product that consumes Integrity Protocol as its evidence and trust substrate (§14.1 of
the protocol spec explains why they are separate repositories).

> **Specification status:** protocol-facing companion specification. The Shield repository now owns
> the comprehensive product and implementation specification at SPECIFICATION.md; its README is
> the source of truth for built/verified/blocked/planned status. This document records the
> Integrity-facing boundary: what Shield consumes, what evidence it emits, and what it must not
> duplicate from Integrity Protocol.

---

## Table of contents

1. Purpose and Relationship to Integrity Protocol
2. Repository and Package Strategy
3. Device-Side Architecture
4. Core Modules
5. Event Schemas
6. Privacy and HIPAA Posture
7. Policy Rule Format
8. AIS Contribution Mapping
9. Network and Zero-Trust Integration
10. Deployment and Resource Constraints
11. Compliance Reporting Surface
12. Competitive Positioning (brief)
13. What This Product Is Not
14. Status and Roadmap

---

## 1. Purpose and Relationship to Integrity Protocol

Xibalba Shield discovers AI agents and tools running on a device or network, constrains what
they can do, and **produces cryptographic evidence of every consequential decision** by feeding
signed telemetry into Integrity Protocol. Shield is the sensor and enforcer; Integrity is the
scorer and archive. Neither subsumes the other:

- Integrity Protocol answers *"can I trust this agent's history?"* — it never observes a
  device, never enforces anything at the OS level, and never decides what a kernel sensor
  should watch.
- Xibalba Shield answers *"what is this agent doing on this machine, right now, and should it
  be allowed to?"* — it never computes AIS, never anchors a Merkle root itself, and never
  becomes a second source of truth for an agent's reputation. It calls Integrity Protocol's
  existing primitives (§4 of the protocol spec) for all of that, the same way any other
  consumer would.

**The wedge, stated precisely.** Nothing in the current AI-agent-security landscape combines
(a) kernel-level device and network enforcement purpose-built for agents, (b) actuarial,
cryptographically-anchored trust scoring, and (c) frictionless sub-90MB deployment for SMBs and
regulated mid-market buyers, in one stack. Identity-governance vendors (Astrix, CyberArk,
Oasis) and runtime-guardrail vendors (Lakera, Zenity, WitnessAI) are strong at cloud-side
policy; none of them own the endpoint. Enterprise suites (CrowdStrike, SentinelOne, Microsoft)
are strong at the endpoint; none of them produce actuarial, hash-anchored evidence of *why* a
decision was made. Shield's differentiation is the combination, not any single layer of it —
see §12.

---

## 2. Repository and Package Strategy

**Decision (2026-08-01), recorded in [`spec/integrity-protocol-v0.4.md`](integrity-protocol-v0.4.md) §14.1:**
Xibalba Shield lives in the separate `XibalbaTechSol/xibalba-shield` repository, not as a
package inside `integrity-latest`. It is built on INTEGRITY-LATEST's public SDK and service
interfaces, while remaining independently deployable.

**Dependency direction is one-way.** `xibalba-shield` depends on `integrity-sdk` (imported the
same way any third-party agent runtime would use it — no privileged API, no special-cased
access). `integrity-latest` has and must have **zero** dependency on `xibalba-shield`; a change
to kernel-sensor code must never be able to affect AIS computation or
Merkle conventions, which is the entire reason the split exists.

**Reference implementation layout.** The implementation ledger and exact current paths live in
the xibalba-shield README and SPECIFICATION.md:

```
xibalba-shield/
├── shield/agent_core/          # DeviceContext, AgentRegistry, EventRouter, EventLog
├── shield/sensors/
│   ├── dev_generator.py        # synthetic dev/test event source
│   └── ebpf/                   # process/file/TCP eBPF probes and loader
├── shield/policy_engine/       # table-driven rule evaluation (§7)
├── shield/guardrail_hooks/     # six semantic LLM/agent boundary gates (§4.4)
├── shield/integrity_exporter/  # wraps integrity-sdk; BCC signing + telemetry
├── shield/config/              # local config loader + hot reload
├── shield/cli.py               # shield status/events/validate/run
└── shield/schemas/             # event and policy dataclasses (§5, §7)
```

---

## 3. Device-Side Architecture

On each supported endpoint, Shield runs as **one lightweight process** composed of cooperating
modules (§4), not a collection of independently-deployed services — this is a deliberate
simplicity choice for a solo-maintained product, revisited only if a specific enforcement need
requires process isolation (e.g., a kernel-privileged component that must survive user-space
daemon crashes).

**Resource budget, binding on v1 design decisions, not aspirational:** RAM ceiling ≤ 90 MB, CPU
ceiling ≤ 3–5% sustained on a typical desktop, disk footprint minimized. Every module below is
scoped with this budget as a constraint, not an afterthought — e.g., §4.1's choice to push
compact records through a ring buffer rather than richer structures exists because of it.

**Supported platforms, v1:** Linux first (eBPF is the most mature, lowest-overhead sensing
path available); Windows and macOS follow once the Linux agent validates the architecture in
pilots. This is a scope decision, not a technical limitation of the design — see §14.

---

## 4. Core Modules

### 4.1 Kernel / OS sensor

**Purpose.** Capture high-value events with minimal overhead; do the least possible work in
kernel space.

- **Linux:** eBPF programs on `process_exec`/`process_exit` tracepoints, file open/write hooks
  on sensitive paths, and TCP-connect/DNS hooks. Compact records only (process lineage,
  executable path/inode, UID/GID, destination tuple) pushed to user space via a ring buffer —
  no rich payload construction in kernel space.
- **Windows/macOS `[PLANNED]`, post-Linux:** ETW/native API sources mapped to the same
  normalized event classes as Linux (§5), so the rest of the stack is platform-agnostic above
  this module.

Output: raw OS events, normalized into the schemas in §5, nothing else. This module owns no
policy logic and makes no enforcement decisions — that is §4.3's job, kept separate so a kernel
sensor bug can never itself become a false-enforcement bug.

### 4.2 Agent Core (user-space daemon)

**Purpose.** The single long-lived process that owns state, coordinates decisions, and talks to
Integrity Protocol.

Responsibilities:

- Subscribe to the kernel/OS sensor's event stream.
- Maintain `DeviceContext` (tenant, device ID, OS, device role — e.g. "clinical desktop") and
  an **`AgentRegistry`**: every AI agent, tool, and model API observed on the device, its
  owner, and its declared purpose. This registry **is** Shield's shadow-AI-discovery
  mechanism — an agent with no registry entry is, by definition, unregistered.
- Normalize sensor events into the common classes of §5.
- Route each normalized event through the Policy Engine (§4.3) and, for agent/LLM-boundary
  events, through the Guardrail Hooks (§4.4).
- Own the local queue feeding the Integrity Exporter (§4.5) — retries, batching, backpressure.

### 4.3 Policy Engine

**Purpose.** Evaluate normalized events against table-driven rules (§7) and decide an action.

Match strategy: first-match, evaluated in rule-priority order. Actions: `allow`, `deny`,
`contain`, `log_only`, `escalate`. Every evaluation produces a `PolicyDecision` record (§5) —
which rule matched, why, and what was done — regardless of outcome, so `log_only` and `allow`
are as visible in the audit trail as a `deny`. This mirrors `bcc_middleware`'s existing
posture (`docs/INTERFACE_CONTRACT.md` §7's "no assume-success fallback") applied to a local,
offline-capable engine rather than a remote OPA call: Shield's policy engine MUST be able to
enforce with **zero cloud round-trip**, since a device that loses connectivity is exactly when
local enforcement matters most.

### 4.4 Agentic Guardrail Hooks

**Purpose.** Wrap LLM/agent calls with security controls at well-defined boundaries, distinct
from the OS-level sensor (§4.1) because this is a semantic layer, not a syscall layer.

Hook points: ingress (prompt, requesting identity), retrieval/context (data sources touched),
model routing (which model/endpoint), output (content classification — PHI, secrets, risk
level), tool execution (which tools/actions), and post-action verification (did the expected
state change actually occur — the "semantic–physical gap" check that
[`spec/integrity-protocol-v0.4.md`](integrity-protocol-v0.4.md) §22.4 also defines at the
session level; Shield's guardrail hooks are one of the concrete instrumentation points that
feeds that broader session-integrity model when Shield sessions are Integrity-monitored
sessions).

Each guarded action emits a structured `AgentEvent` (§5) and, where policy fires, a
`PolicyDecision` — both flow through §4.5 into Integrity's evidence pipeline unchanged.

### 4.5 Integrity Telemetry & AIS-Feeding Exporter

**Purpose.** Turn local decisions into signed evidence, using Integrity Protocol's existing
primitives with no privileged shortcut.

- Wraps `integrity-sdk`: DID assignment per device/agent, BCC commitment signing
  ([`spec/integrity-protocol-v0.4.md`](integrity-protocol-v0.4.md) §11), Merkle batching over
  the SDK's existing Trust Vault path.
- A `PolicyDecision` becomes a BCC commitment whose `intent_type` is a security-event type
  (§5.6) and whose `intended_state_hash` commits to the decision's structured detail.
- Sends to `bcc_middleware` / `integrity-oracle` over the existing `POST /v1/bcc/intercept`
  and telemetry-ingest paths (`docs/INTERFACE_CONTRACT.md` §2, §4.2) — **no new oracle
  endpoint is required or should be added** for Shield specifically; it is a consumer like any
  other.
- AIS deltas are not computed by Shield. Shield emits evidence; `integrity-oracle`'s existing
  `scoring-core` (protocol spec §9) is the only place that turns evidence into a score, per
  that document's own "sole computer" rule. §8 below documents *what kind* of evidence moves
  the score, not a second scoring implementation.

### 4.6 Configuration & Update Module

**Purpose.** Keep operational friction low for administrators, matching the "frictionless
adoption" requirement that is this product's core go-to-market thesis.

- Policies loadable from local files or a tenant cloud API; safe auto-update for agent code and
  policy bundles; per-tenant feature flags.
- Diagnostics: a `/health` endpoint and a small CLI (`shield status`, `shield events --recent`)
  so an admin or pilot customer can self-inspect what Shield is doing without opening a
  dashboard — this is deliberate: a security product an admin cannot explain in one command is
  a security product they will disable during an incident.

---

## 5. Event Schemas

OCSF-style JSON, chosen for SIEM/SOAR portability. **These are the canonical shapes; a package
implementing them MUST NOT rename fields** — same discipline
[`docs/INTERFACE_CONTRACT.md`](../docs/INTERFACE_CONTRACT.md) already applies to the BCC
commitment shape.

### 5.1 ProcessActivity

```json
{
  "class": "process_activity",
  "time": "2026-08-01T15:35:12Z",
  "device_id": "dev-123",
  "tenant_id": "tenant-xyz",
  "process": {
    "pid": 1234, "name": "python.exe", "exe_path": "...",
    "cmdline": "...", "hash_sha256": "...", "ppid": 1000, "parent_name": "powershell.exe"
  },
  "activity": { "type": "launch", "severity": "medium", "outcome": "success" }
}
```

### 5.2 FileActivity

```json
{
  "class": "file_activity",
  "time": "...", "device_id": "...",
  "process": { "pid": 1234, "name": "python.exe" },
  "file": { "path": "...", "name": "evil.sys", "ext": "sys", "type": "executable" },
  "activity": { "type": "create", "severity": "high", "outcome": "success" }
}
```

### 5.3 NetworkFlow

```json
{
  "class": "network_flow",
  "time": "...", "device_id": "...",
  "process": { "pid": 1234, "name": "python.exe" },
  "flow": { "src_ip": "...", "src_port": 52341, "dst_ip": "...", "dst_port": 443, "protocol": "tcp", "direction": "outbound" },
  "activity": { "type": "connect", "severity": "medium", "outcome": "success" },
  "dns": { "query_name": "...", "resolved_ips": ["..."] }
}
```

### 5.4 AgentEvent

```json
{
  "class": "agent_event",
  "time": "...", "device_id": "...",
  "agent": { "agent_id": "...", "name": "...", "type": "llm_tool", "owner_user_id": "...", "workload_id": "..." },
  "context": { "data_sources": ["..."], "tools_called": ["..."], "model_endpoint": "..." },
  "activity": { "type": "inference", "risk_level": "high", "policy_violation": true }
}
```

### 5.5 PolicyDecision

```json
{
  "class": "policy_decision",
  "time": "...", "device_id": "...",
  "event_ref": { "class": "network_flow", "event_id": "evt-123" },
  "rule": { "rule_id": "net-block-unknown-ai", "name": "...", "version": "1.0.2" },
  "decision": { "action": "deny", "reason": "...", "severity": "high" }
}
```

This record is what the Integrity Exporter (§4.5) turns into a signed BCC commitment. It is
also the record referenced by [`spec/integrity-protocol-v0.4.md`](integrity-protocol-v0.4.md)
§21.4's Action Receipt formalization once anchored — no field renaming happens at that boundary.

### 5.6 Security-event `intent_type` namespace

Extends `BCC Commitment.intent_type` the same way healthcare and financial types do (protocol
spec §21.2):

| `intent_type` | Meaning |
|---|---|
| `shadow_agent_detected` | An unregistered agent/tool was discovered |
| `agent_contained` | An agent process was contained/terminated by policy |
| `connection_blocked` | An outbound connection was denied |
| `guardrail_denied` | An LLM/agent boundary hook denied an inference or tool call |
| `phi_access_attempt` | A PHI-bearing resource was accessed or an access was attempted (§6) |
| `device_posture_change` | A device's risk posture crossed a policy-relevant threshold |

---

## 6. Privacy and HIPAA Posture

**This section is Shield's own design obligation** — Integrity Protocol's PHI backstop
(`spec/integrity-protocol-v0.4.md` §9.6) governs what the *oracle* accepts in a telemetry
payload; it does not and cannot govern what a device agent is permitted to *observe*. Stating
this explicitly matters because conflating the two would itself be a silent-mock claim.

**Governing principle: behavioral telemetry, not content inspection.** Shield's sensors
observe processes, connections, and agent activity — not the content of files, messages, or
model outputs, except where a guardrail hook (§4.4) must classify content risk at the boundary,
and even there the output is a **classification label**, never the raw content, propagated
downstream.

- **At rest:** ePHI on a device remains protected by existing full-disk encryption and
  application-level access control. Shield does not decrypt or index ePHI. When Shield must
  reason about potential PHI exposure, it tags a resource as "PHI-bearing" and tracks *access
  events* against that tag — never the record's contents.
- **In transit:** Shield's network sensor (§9) treats payloads as opaque; it records "this
  process sent data to `https://ehr.example` over TLS," never the encounter content.
- **Guardrail output classification:** an `AgentEvent`'s `context.data_sources` names a
  resource class (`ehr_encounter`), never a patient identifier or record content.
- **Training data (§8, proprietary model):** any future Shield-trained model is trained on
  de-identified, consented behavioral labels ("PHI-bearing resource accessed under role X"),
  never raw clinical text — enforced at the point telemetry is generated, not as a downstream
  filter, matching the same "redact at source" principle
  [`spec/integrity-protocol-v0.4.md`](integrity-protocol-v0.4.md) §9.6 already applies to
  oracle ingest.

**Deployment posture in regulated environments.** Where Shield is deployed against ePHI-bearing
systems, Xibalba Solutions operates as a HIPAA Business Associate for what Shield incidentally
processes — an operational/contractual fact, not a technical control, and out of scope for this
document beyond stating it.

**Status:** `[PLANNED]`. No PHI-tagging mechanism, guardrail classifier, or BAA template exists
yet.

---

## 7. Policy Rule Format

JSON, table-driven, evaluated by the Policy Engine (§4.3):

```json
{
  "rule_id": "proc-restrict-shadow-ai",
  "name": "Restrict shadow AI processes",
  "version": "1.0.0",
  "scope": { "tenants": ["tenant-xyz"], "device_roles": ["clinical_desktop"] },
  "conditions": [
    { "type": "process", "match": { "exe_path": ["*/ai/*.exe"], "user_group": ["non_admin"] } },
    { "type": "agent", "match": { "registered": false, "authority_level": ["high"] } }
  ],
  "actions": [
    { "type": "contain", "message": "Unregistered AI tool blocked.", "log_decision": true }
  ],
  "ais_impact": { "agent_delta": -10, "device_delta": -3 }
}
```

`ais_impact` is a **hint** consumed by §8's mapping layer, not a direct write to AIS — the
oracle's `scoring-core` remains the sole computer of any score
([`spec/integrity-protocol-v0.4.md`](integrity-protocol-v0.4.md) §8.1).

---

## 8. AIS Contribution Mapping

Shield does not compute AIS. This section documents the **evidence-shape convention** Shield
commits to, so that when `integrity-oracle` extends its scoring inputs to consume
security-event evidence (a change that belongs entirely to that repository, tracked separately)
the mapping is unambiguous:

| Event class | Typical signal |
|---|---|
| Trusted behavior (registered agent, policy-compliant) | Small positive contribution to grounding/compliance |
| Minor violation (low-risk shadow AI, blocked with no data exposure) | Small negative contribution to compliance |
| Major violation (PHI exposure attempt, exfiltration, privilege escalation) | Large negative contribution to compliance |

This table is illustrative of the evidence Shield produces, not a scoring formula — the formula
lives in exactly one place per the protocol spec's own rule (§8.1), and this document does not
duplicate or shadow it.

---

## 9. Network and Zero-Trust Integration

Shield's network posture is **host-centric by default**: connection attempts are attributed to
a process via the kernel sensor (§4.1), not observed from a separate network appliance. An
**optional** network sensor (virtual appliance or container on a subnet) is a v2+ consideration
for environments wanting deeper flow inspection — explicitly deferred past v1 (§14) rather than
speculatively designed now.

Shield MAY act as a signal provider to existing identity/access systems (conditional access,
ZTNA), publishing device posture and agent risk so a high-risk endpoint triggers tighter access
controls elsewhere. This is an integration point, not a Shield-owned enforcement mechanism —
Shield does not reimplement ZTNA.

---

## 10. Deployment and Resource Constraints

- **Install:** simple installer/script per OS; RMM/MDM integration where available; minimal
  default policies with per-vertical templates (healthcare, professional services).
- **Control plane:** cloud or on-prem console for policy management, alert triage, and
  Integrity-backed report generation; API-first so larger customers can plug into existing
  SIEM/SOAR.
- **Staged rollout:** start with process-execution visibility only, validate real overhead
  against the §3 budget, then add file and network probes incrementally — never all sensors at
  full fidelity on day one of a pilot.

---

## 11. Compliance Reporting Surface

Shield's evidence, once anchored via §4.5, is exportable through Integrity Protocol's existing
evidence-export path (`docs/design/evidence-export.md`, referenced by
[`docs/ENTERPRISE_ADOPTION.md`](../docs/ENTERPRISE_ADOPTION.md) Lever 4) — **no separate export
mechanism belongs in Shield.** The customer-facing promise this enables: every agent action is
attributable to an identity, a policy version, and verifiable evidence, not a black-box log
line. Building a second, Shield-specific export path would fragment exactly the evidence
guarantee that is the whole point of consuming Integrity Protocol in the first place.

---

## 12. Competitive Positioning (brief)

Not normative — recorded because it shapes scope decisions elsewhere in this document (e.g.
§3's Linux-first choice, §9's host-centric-by-default choice). The market splits into agent
identity/access governance (Astrix, CyberArk, Oasis), runtime prompt/tool guardrails (Lakera,
Zenity, WitnessAI), and enterprise EDR/XDR suites extending to agents (CrowdStrike,
SentinelOne, Microsoft). None combine lean kernel-level enforcement with actuarial,
hash-anchored evidence at sub-90MB overhead — that combination, not any single capability, is
the differentiation. Full competitive and business analysis belongs in a business-plan
document, not this technical specification; see the archived Perplexity research this
specification was drafted from for that material if it is needed later.

---

## 13. What This Product Is Not

- Not a payment rail, a custodial key service, or a trust-scoring engine — those are Integrity
  Protocol's job (§1).
- Not a full replacement for existing EDR/XDR in a v1 scope — a focused wedge (agent discovery,
  constraint, evidence), not "replace CrowdStrike."
- Not a second place AIS is computed, and not a second evidence-anchoring mechanism (§8, §11).
- Not multi-OS at v1 — Linux-first is a scope decision (§3), not a claim of Windows/macOS
  parity that does not exist.
- Not a content-inspection or DLP product — behavioral telemetry only (§6).

---

## 14. Status and Roadmap

Status is maintained in the Shield repository README. As of 2026-08-06, the pure-Python core is real and tested: schemas, policy engine, agent core, all six guardrail hooks, local configuration loading/hot reload, CLI, and Integrity exporter. Linux process-exec and file-write eBPF probes are live-verified; TCP-connect is blocked by a BCC/kernel compatibility issue, and DNS observation is not built. Windows/macOS sensors, tenant cloud policy distribution, safe code auto-update, and Shield-specific compliance report polish remain planned or blocked as documented in the Shield README.

Roadmap phases:

1. Linux enforcement baseline: keep process/file probes verified, unblock TCP-connect, design DNS observation, and add sensitive-path filters.
2. Integrity registration and evidence closure: register the exporter DID with Oracle, verify audit-log/readback visibility, and re-run resource measurements with a clean registered DID.
3. Policy distribution and update safety: signed policy bundles, tenant policy client, and safe code-update design with rollback.
4. Pilot readiness: managed service packaging, default policy packs, operator runbooks, rollback/uninstall, and resource burn-in.
5. Platform expansion: Windows ETW, macOS sensor, optional network appliance/container sensor, and SIEM/SOAR integrations.

Detailed Shield product behavior now lives in XibalbaTechSol/xibalba-shield SPECIFICATION.md. Detailed go-to-market strategy lives in [docs/ENTERPRISE_ADOPTION.md](../docs/ENTERPRISE_ADOPTION.md) Lever 7.


---

*End of specification (v1.0)*
