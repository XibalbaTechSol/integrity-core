---
title: integrity-sdk
created: 2026-07-07
updated: 2026-07-29
type: entity
tags: [sdk, identity, metrics]
confidence: high
source_files:
  - integrity-sdk/integrity_sdk/registration.py
  - integrity-sdk/integrity_sdk/wallet.py
  - integrity-sdk/integrity_sdk/chain.py
  - integrity-sdk/integrity_sdk/bcc.py
  - integrity-sdk/integrity_sdk/markets.py
  - integrity-sdk/integrity_sdk/client.py
  - integrity-sdk/integrity_sdk/batcher.py
  - integrity-sdk/integrity_sdk/telemetry/mlflow_tracing.py
  - integrity-sdk/integrity_sdk/telemetry/derive.py
  - integrity-sdk/integrity_sdk/telemetry/tracing.py
  - integrity-sdk/integrity_sdk/telemetry/intent.py
  - integrity-sdk/integrity_sdk/telemetry/metrics.py
  - integrity-sdk/integrity_sdk/integrations/openai_integrity.py
  - integrity-sdk/integrity_sdk/integrations/langchain_callback.py
  - integrity-sdk/integrity_sdk/integrations/auto_hook.py
  - integrity-sdk/integrity_sdk/security/redactor.py
  - integrity-sdk/integrity_sdk/mcp_server.py
  - integrity-sdk/integrity_sdk/memory.py
---


The agent-facing Python library. It gives an AI agent everything it needs to
become a self-sovereign, on-chain, reputation-bearing participant.

## Two keypairs

- **DID key** (`did.py`) — Ed25519, `did:integrity:<sha256(pubkey)>`, signs
  [BCC commitments](../concepts/bcc.md) and telemetry.
- **EVM wallet** (`wallet.py`) — secp256k1, encrypted V3 keystore, signs on-chain
  deploys. Bound to the DID via a CAIP-10 `blockchainAccountId` verification
  method (`attach_evm_account`).

## Self-sovereign registration

`registration.register_agent(...)` runs the full on-chain
[primitive-deploy sequence](../concepts/agent-primitives.md) — fund → mint ITK →
deploy `SovereignAgent` + `StateAnchor` → grant anchor role via `execute` →
`registerPrimitives` → POST to the [oracle](integrity-oracle.md) for independent
on-chain re-verification. Proven against a live anvil chain running the real
`Deploy.s.sol` (`tests/test_registration.py`, `skip_oracle_registration=True`,
on-chain steps only).

**Fixed 2026-07-09**: the final oracle POST (step 11) used to send
`{"agent_id": ..., "did_document": ..., "primitives": registration.to_dict()}`,
which 422'd against the oracle's real `RegisterAgentRequest` struct
(`integrity-oracle/backend/src/handlers.rs`) — that struct requires a `did`
field (not `agent_id`) and at least one of `ed25519_pubkey_hex` /
`eth_address_hex` (400 if both absent). Never caught before because every
existing test passed `skip_oracle_registration=True`. Now sends
`{"did", "did_document", "primitives": {the 7 PrimitiveSetDto fields only},
"ed25519_pubkey_hex", "eth_address_hex"}`, matching the oracle's struct
field-for-field (documented in `docs/INTERFACE_CONTRACT.md` §6.3). Proven
end-to-end (register without `skip_oracle_registration` → agent visible via a
real `GET /v1/agents`) by the new opt-in `tests/test_registration_oracle_e2e.py`
(`ORACLE_E2E=1`, spins up a real `cargo run` oracle + ephemeral Postgres/Redis
via Docker against the same real anvil chain).

## Telemetry: OpenTelemetry + MLflow, unified

`telemetry/mlflow_tracing.py` configures MLflow GenAI tracing (`@mlflow.trace`,
`openai`/`langchain` autolog) to export **through** OpenTelemetry, so one OTLP
collector sees both the SDK's own spans and MLflow's auto-captured GenAI spans.
`telemetry/derive.py` extracts the four [AIS](../concepts/ais.md) input signals
(real Shannon entropy, grounding, log-scaled token "sacrifice", compliance) from
those spans; the oracle owns the final formula. See
[local metrology](../concepts/local-metrology.md) for the exact derivations.
`client.py` batches and POSTs to the oracle.

## Pre-execution intent capture (`telemetry/intent.py`, added 2026-07-11)

`invoke_intent` (also `client.invoke_intent(...)`, pre-bound) is the OTel
counterpart to `bcc.build_bcc_commitment`: builds and signs the real BCC
commitment (unchanged, single source of truth), opens a real
`integrity.invoke_intent` span *before* the caller's execution code runs
(temporally prior, not retrofitted after the fact — the whole point of a
pre-execution gate), and records a `trace_run`-shaped entry that rides the
same `flush_telemetry` pipeline `traceable` already uses. `intent_id` reuses
the commitment's own `intended_state_hash` rather than minting a second ID
space. `IntentInvocation.record_outcome(actual_action)` runs a tier-1
(deterministic, structural tool-name+args diff — see
`compare_planned_to_actual`) plan-adherence check and records it via the
newly-wired `record_metric` escape hatch (see below). Tiers 2/3 (semantic
similarity, sampled LLM-judge) are explicitly NOT built — deferred, not
silently dropped; see the module's own docstring.

## Two dangling-reference gaps, closed 2026-07-11

`telemetry/metrics.py`'s `MetricsRegistry` was fully built (an open-ended
named-metric recording API, documented as attaching to the outgoing
telemetry envelope) but never actually instantiated by `IntegrityClient` —
the exact same "referenced but the referencing code was never written"
pattern `client.py`'s own docstring already describes fixing for
`tracing.py`/`bcc.py`/`derive.py`, just missed for this one module. Now
wired: `client.record_metric`/`define_metric`, drained into `otel_spans` on
every `flush_telemetry`.

**A more severe version of the same pattern, also closed 2026-07-11:**
`flush_telemetry` was sending a request the real oracle could never accept —
confirmed via `integrity-oracle`'s own real-HTTP e2e test, which hand-builds
its request in the *correct* shape. Two independent breaks: `otel_spans`
was sent as a JSON object (`{"telemetry": [...], "trace_runs": [...]}`)
against an oracle schema requiring a JSON array, and `signature` was sent as
`None` against a required, cryptographically-*verified* `String` field (the
in-code comment claiming "the handler currently treats the signature as
optional" was simply wrong). This means **every telemetry flush this SDK
ever sent to a real oracle before this fix would have been rejected before
the handler even ran.** Fixed: `otel_spans` is now one flat, tagged array;
`IntegrityClient` accepts an optional `keypair=`/`bcc_nonce_store=` at
construction and, when present, signs the canonical envelope for real
(matching `integrity-oracle`'s `crypto::canonical_json_bytes` — which
itself needed a matching fix, see [integrity-oracle](integrity-oracle.md),
for non-ASCII content to verify correctly). Without a keypair, flush still
sends a (now honestly-rejected, not silently-malformed) empty signature.

## Telemetry integrations widened + `redact_phi` opt-in default, 2026-07-15

`integrations/openai_integrity.py` and `integrations/langchain_callback.py`
both gained real, previously-uncaptured operational metadata the
underlying provider already returns: `model_requested`/`model_actual`,
`system_fingerprint`, `service_tier`, `tool_calls` (names only —
`function.arguments`/tool `args` are never captured, since they can carry
unredacted caller-supplied content), `conversation_length`, and a
previously-nonexistent error path for the OpenAI wrapper (`error_taxonomy`
= `type(exception).__name__`, a real provider-native taxonomy; LangChain's
`on_llm_error` already existed). Neither integration had any test coverage
before this — both now do (`tests/unit/test_openai_integrity.py`,
`tests/unit/test_langchain_callback.py`, 13 new tests).

**Real behavior change**: both integrations' `redact_phi` constructor
parameter now defaults to `False` (previously redaction ran
unconditionally — see next section for what that means and its risk).
Full writeup: [Telemetry Ingestion Pipeline](../concepts/telemetry-ingestion.md).

## PHI/PII redaction

`security/redactor.py` — targeted, client-side masking (SSNs, emails,
phone numbers, credit cards, API keys/private keys, medical record
numbers). `integrations/openai_integrity.py`/`langchain_callback.py` both
call it before a span attribute/telemetry field is set, but **only when
constructed with `redact_phi=True`** (default `False` as of 2026-07-15 —
see above). Any Integrity Health / healthcare-vertical agent must pass that
flag explicitly; neither wrapper can infer an agent's `compliance_vertical`
on its own. `telemetry/tracing.py`'s `trace_run`/`traceable` API is
unaffected by this flag and always redacts.

**Real gap closed 2026-07-11**: the SDK's own documented, *recommended*
general-purpose tracing API — `telemetry/tracing.py`'s `trace_run`/
`traceable`/`client.traceable(...)` — captured a wrapped function's raw
arguments and return value with **no redaction at all**, contradicting
[Observability & PHI Safety](../concepts/observability-vtl.md)'s prior claim
that redaction was "wired into both instrumentation paths" (that page only
ever covered the two *integrations* above, not this lower-level, more
general API). Any consumer decorating their own LLM-calling function with
`@client.traceable(...)` was forwarding raw, unredacted prompt/completion
content toward the oracle. Fixed: a new `_redact_value` helper recursively
applies `redact_text` to every string leaf in `TraceRun.set_outputs`'s
value and `_capture_inputs`'s captured arguments, however deeply nested in
dicts/lists. See [Observability & PHI Safety](../concepts/observability-vtl.md)
for the still-open half (oracle-side defense in depth, LLM-as-judge — both
`[PLANNED]`).

## Markets

`markets.py` — `enter_prediction`, `enter_binary_option`, `allocate_capital`:
builds a real [BCC commitment](../concepts/bcc.md), routes through
[bcc_middleware](bcc_middleware.md), calls the relevant
[Integrity Market](../concepts/integrity-market.md) contract via
execute-routing. `registration.py`'s `_VERTICALS` extended with
`prediction_market`/`trading`/`capital_allocation` compliance verticals.

## Also

- `bcc.py` — signed [BCC commitment](../concepts/bcc.md) construction (7 signed
  fields incl. the self-certifying `agent_public_key`).
- `prover.py` — real `nargo`/`bb` [ZK proof](../concepts/zkp.md) generation.
- `security/attestation.py` — real AWS Nitro attestation *verification* (gen
  needs enclave hardware — honest, documented gap).

**135 tests, 1 skipped** (`pytest tests/`, confirmed via a real run — up
from 97: the 2026-07-15 additions are `test_openai_integrity.py` (7),
`test_langchain_callback.py` (6), plus attestation/health/wallet-race
coverage added earlier the same session): unit + real-anvil integration,
always run. Plus **1 opt-in test** (`test_registration_oracle_e2e.py`,
`ORACLE_E2E=1`) covering the real oracle-POST path skipped by every
always-run test above.

Related: [Telemetry Ingestion Pipeline](../concepts/telemetry-ingestion.md),
[agent primitives](../concepts/agent-primitives.md),
[BCC](../concepts/bcc.md), [AIS](../concepts/ais.md),
[integrity-cli](integrity-cli.md), [AIS API — Versioned Wire Spec](../concepts/ais-api-spec.md).

## MCP server (`mcp_server.py`, added 2026-07-29)

`integrity_sdk.mcp_server` exposes the SDK's core capabilities as
[Model Context Protocol](https://modelcontextprotocol.io) tools so any
MCP-capable agent harness (Claude Desktop, Cursor, Antigravity CLI, custom
harnesses) can discover and call them over JSON-RPC without a
framework-specific adapter.

Five tools registered:

| Tool | Description |
|---|---|
| `integrity_log_telemetry` | Append one telemetry entry (CoT, tool call, tokens) to the in-memory batch |
| `integrity_flush_telemetry` | Flush the batch to Oracle `/v1/telemetry/ingest` with Ed25519 signature |
| `integrity_invoke_intent` | BCC-commit + OPA-gate an intent before execution |
| `integrity_agent_info` | Read back canonical DID, nonce, keypair status, pending batch size |
| `integrity_resolve_did` | Look up any DID's on-chain registration record via Oracle |
| `integrity_register_agent` | [PLANNED partial] Full on-chain registration via `registration.register_agent` |
| `integrity_commit_memory` | Commit session facts to the TrustVault backend (JSONL by default) and compute/anchor the cryptographic StateRoot |

The server loads the agent's Ed25519 keypair from the standard identity store
(`~/.integrity-cli/identity/<agent-id>/`) so every flush and intent call is
correctly signed. If no keypair is found, the server still starts and provides
logging, but flushes will receive a 401 from the oracle (documented in
`client.py`'s `flush_telemetry` docstring).

Run standalone:

```
uv run --with mcp python -m integrity_sdk.mcp_server \
    --agent-id xibalba \
    --oracle-url http://localhost:8080
```

Or add to any MCP-capable harness config under `mcpServers.integrity`.

For example, to configure the Antigravity CLI (`agy`) harness to run all sessions in the context of the `xibalba.integrity` agent, add the following to `~/.gemini/antigravity-cli/settings.json` (under `"mcpServers"`):

```json
    "integrity": {
      "command": "/home/xibalba/.local/bin/uv",
      "args": [
        "run",
        "--directory",
        "/home/xibalba/Projects/INTEGRITY-LATEST/integrity-sdk",
        "python",
        "-m",
        "integrity_sdk.mcp_server",
        "--agent-id",
        "xibalba.integrity",
        "--oracle-url",
        "http://localhost:8080"
      ]
    }
```

Requires `mcp>=1.0.0` (`pip install integrity-sdk[mcp]` — optional dep).

## Persistent Memory Bridge (`memory.py`, added 2026-07-30)

`memory.py` introduces a primitive-level persistent memory architecture based on the `TrustVault` class and a `MemoryBackend` adapter pattern (strategy pattern).
Instead of treating memory sync as an ad-hoc cron job, agents use the SDK to explicitly commit and cryptographically anchor their state to the `StateAnchor` primitive at the end of a session.

**MemoryBackends**:
- `JSONLBackend`: The default backend (append-only log).
- `RAGBackend`: [Stub] For vector databases.
- `GraphBackend`: [Stub] For relational graph memory.

**Pre-Flight Verification**:
When `vault.session(platform=...)` begins, the SDK invokes `verify_preflight()`. This queries the `integrity-oracle` for the agent's `StateAnchor` address, reads the `currentRoot()` directly from the EVM (via `web3.py`), and compares it against the local backend's derived `state_root`. If they mismatch, the session panics, protecting the agent from acting on tampered or out-of-sync local memory.


