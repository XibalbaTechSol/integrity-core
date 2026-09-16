# Integrity SDK and telemetry architecture

Status: implementation baseline, 2026-09-15. Findings preserve evidence
classes; source or API observations are not on-chain claims.

## Boundary map

| Boundary | Owner | Canonical data | Evidence | Failure boundary |
|---|---|---|---|---|
| Logical identity | `integrity-sdk/did.py` | Ed25519 key, DID document, fingerprint | Source and unit tests | Missing/inconsistent key state fails closed |
| Harness runtime | `agent_runtime.py` | harness, profile, device, session attribution | Source and unit tests | Expected-DID/device mismatch refuses attribution |
| Registration | SDK, CORE contracts, Oracle | agent/primitives/controller state | Source/local tests; live state must be reread | No blind transaction retry |
| Signed telemetry | Oracle `/v1/telemetry/ingest` | nonce-protected signed AIS evidence | Source and Oracle e2e tests | Confirmed-unregistered agents are not sent |
| Observability | Oracle OTLP receiver | OTel spans/metrics/logs | Source and Cortex tests | Never canonical AIS evidence |
| Local telemetry | SDK `LocalEventStore` | redacted JSONL or SQLite events | Source and SDK tests | Local acceptance is not remote acknowledgement |
| Memory/provenance | Cortex `GraphStore`/SQLite | agent-scoped memories, sessions, replay | Source and Cortex tests | Projections do not replace SQLite writes |
| Enforcement | Shield | device-bound decisions and evidence | Source and Shield tests | Denials cannot be bypassed |
| Dashboard | nested `integrity-dashboard` | typed operator projection | Source; browser evidence outstanding | Build/API success is not browser proof |

## Identity model

Harness, logical Integrity agent, Cortex principal, Shield device, EVM wallet,
controller, contract owner, funder, Oracle, backend service, and end user are
separate subjects. The SDK loads `INTEGRITY_DID_HOME` or
`~/.integrity/did/<agent>` and creates a key only when both key and document
are absent. Mismatch, missing private key, or expected-DID mismatch is a hard
error. Shield is a Hermes-associated logical agent with stricter device binding,
not the default Hermes identity. Cortex must retain exact agent IDs and
authenticated principals, never timestamp/address similarity.

## Canonical event envelope

`integrity_sdk.telemetry.envelope.TelemetryEnvelope` is schema version 1. It
contains event/provenance IDs, agent/DID/harness/principal/device/session
scope, invocation/trace/span relationships, wall and monotonic time, payload
and developer metadata, privacy/redaction state, content hash, and payload
hash. Unknown event types are rejected. Recursive secret-key and content
redaction occurs before local persistence. Location is absent unless explicitly
added by a future opt-in policy.

The signed Oracle request is a different envelope (currently schema version 2,
with backward compatibility for pre-versioned evidence). The local envelope
must not replace that signing grammar.

`IntegrityAgent.identity_snapshot()` is the non-secret identity registry
projection used by SDK callers. The DID directory and DID document remain the
canonical identity store; the projection contains the slug, harness, DID,
principal, device, key fingerprint, DID-derived controller, wallet references
when already present in the DID document, registration status, and a
DID-directory memory reference. It does not persist or expose private keys and
does not equate the Cortex principal, Shield device, wallet, controller, or
contract owner.

`migrate_identity_store(...)` is the supported copy-only migration path. It
validates that the source document matches the Ed25519 key, refuses an
inconsistent or conflicting destination, preserves the source as recovery
material, and never generates replacement key material.

Runtime loads append non-secret identity observations to
`<DID_HOME>/identity_registry.jsonl`; `history()` and `latest()` expose the
audit projection. Migration merges only matching-agent registry records,
deduplicates exact lines, and leaves unrelated agents and the source root
untouched.

## Developer entry points

```python
from integrity_sdk import integrity
agent = integrity.auto()  # persistent identity + redacted local JSONL boundary
agent.emit("prompt_received", payload={"prompt": "..."})
agent.flush()
agent.close()
```

For explicit integrations, `agent.export_cortex(...)` sends redacted events
through Cortex using a caller-provided bearer token, and
`agent.record_shield_decision(...)` records a pair-bound allow/deny outcome
after Shield has made the decision. The latter never performs enforcement.

Advanced setup uses `integrity.init(agent_id=..., harness=..., memory=...,
telemetry=..., identity="persistent")`. `telemetry="disabled"` disables the
local store. Existing provider integrations remain explicit wrappers/callbacks.

`integrity_sdk.integrations.cortex.CortexTransport` is an explicit authenticated
writer for Cortex's existing `POST /api/otel/batch` boundary. It requires a
bearer token and session ID, maps each envelope to an idempotent OTel event, and
preserves the envelope as event attributes. Cortex still derives write
authority from the authenticated principal. `integrations.shield` provides
pure context and decision-event builders requiring the exact
agent/device/invocation/action tuple; it never evaluates or bypasses Shield
policy.

`telemetry.delivery.deliver_with_retry` provides the bounded transport policy:
the event ID is always passed as the idempotency key, retries are exponential
and finite, and the final failure is explicitly `dead-lettered`. SQLite stores
delivery attempts in a separate durable table; JSONL stores them as typed
`record_type=delivery_attempt` records. A local append or queue operation is
not represented as remote acknowledgement or canonical indexing.

The SDK also exposes `HttpTelemetryTransport`, `OTLPHttpTransport`, and
`MCPTelemetryTransport`. HTTP and OTLP/HTTP send the versioned envelope batch
with authentication and event-ID idempotency headers; MCP requires the host
to provide its installed client's `call_tool` function and passes event IDs in
the tool arguments. These are explicit transports, not automatic claims that
an arbitrary harness supports MCP or OTLP.

## Privacy boundary

The envelope recursively redacts secret-shaped mapping keys and high-confidence
secret/PII patterns in strings before local persistence. This includes private
key blocks, API/Bearer credentials, passwords and client secrets, cookies,
cloud/database/SMTP credentials, recovery phrases, SSNs, cards, email, phone,
and MRN markers. Collection profiles remain the higher-level control:
`development` captures redacted content, `standard` samples it, and
`regulated` withholds content. Location is not collected by the SDK façade;
any future location field must be explicitly opted in and policy-scoped.
Redaction is heuristic, not a legal de-identification guarantee, so destination
backstops remain authoritative.

The façade exposes this policy explicitly through `PrivacyPolicy`: choose
`mode="redacted"` (default), `mode="metadata_only"`, or
`mode="hash_only"`, set a content limit, and opt into location with
`allow_location=True`. Policy application occurs before envelope hashing and
before the local event store, so hashes and persisted records describe the
sanitized representation rather than raw input.

Retention is explicit through `PrivacyPolicy(retention_days=...)`. Retention-
enabled local storage uses SQLite and transactionally removes expired events
and their delivery attempts. JSONL remains append-only and therefore rejects
retention configuration rather than falsely claiming that historical bytes
were erased; operators requiring expiry must select SQLite or an external
retention-managed durable boundary.

## Adapter and verification status

| Harness | Status |
|---|---|
| Generic Python/custom | Baseline façade and explicit emit; source/test confirmed |
| OpenAI/Anthropic/LangChain | Explicit wrappers/callbacks and tests; no universal auto lifecycle |
| Hermes | Local identity mapping/config exists; live canary requires reread |
| Codex | Cortex OTLP/session ingestion and idempotency exist; browser proof outstanding |
| Claude | Explicit/OTLP path exists; live provider canary not claimed |
| Agy/Antigravity | Optional patch detects installed module; absent means unsupported |
| OpenClaw, Perplexity, Spark, Groq, Node/HTTP/MCP/OTLP | No unsupported runtime is claimed instrumented without a stable hook |

Registration readiness must independently report identity/DID/key continuity,
memory/genesis, wallet, controller, ownership/control, roles/primitives, BCC,
telemetry canary, and finality. This baseline performs no registration,
funding, ownership, or finality mutation.

The read-only SDK API `assess_local_readiness(agent_id, preflight=...,`)
returns a structured `RegistrationReadiness` report. Each `ReadinessCheck`
contains status, evidence source, timestamp, agent ID, failure reason,
remediation, and whether the evidence is authoritative. Missing chain preflight
or Oracle state is reported as `unknown`, never as ready.

## Evidence ledger and blockers

- Documentation-confirmed: README, SPEC, INTERFACE_CONTRACT, and
  MAINNET_READINESS define roles, registration, signed telemetry, and blockers.
- Source-confirmed: DID persistence, signed Oracle request, collection/queue,
  Cortex SQLite/OTLP, Shield device/decision schemas, and dashboard projection.
- Test-confirmed: SDK envelope redaction/hash/local idempotency plus existing
  Oracle, Cortex, and Shield suites.
- Inferred: this envelope is the intended developer boundary; it is not yet a
  deployed cross-repository canonical schema.
- Unknown/blocked: current six-agent live validation, authenticated
  Cortex/Shield correlation, dashboard browser journeys, and on-chain
  readiness require current services, credentials, and safe fixtures.

The package is Python-first; no TypeScript SDK was found. Identity snapshots
are derived rather than a second mutable identity database, so `agents.json`
remains a cosmetic label source only. The local store has
no remote receipts or dead-letter queue, and the new envelope is not yet
automatically mapped into Cortex, Shield, or dashboard projections. Next gates
are to freeze the schema in `INTERFACE_CONTRACT.md`, add explicit mapping and
receipt-backed transports, bind authenticated principal/device context, and
run the safe agent/browser/on-chain matrix.
