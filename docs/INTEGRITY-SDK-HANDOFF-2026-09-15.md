# Integrity SDK Identity and Telemetry Handoff

**Date:** 2026-09-15  
**Repository:** `integrity-core`  
**Branch:** `feat/harness-neutral-agent-runtime`  
**Published commit:** `1cd2ab3` (`docs: reconcile SDK identity and telemetry documentation`)

## Handoff status

Scopes 4–7 of the SDK work are implemented and documented:

1. one-line Python SDK façade and explicit configuration;
2. canonical DID-root identity registry projection and safe migration;
3. versioned telemetry envelope, local/remote transports, retries, and delivery states;
4. privacy, redaction, retention, and secret-protection policy.

This handoff describes the implemented SDK boundary. It does not represent
production completion of the broader Hermes, Shield, Cortex, Dashboard, or
on-chain registration program.

## Canonical boundaries

| Concern | Canonical authority | SDK role | Important distinction |
|---|---|---|---|
| DID and Ed25519 key continuity | `integrity_sdk.did`, `$INTEGRITY_DID_HOME/<agent-id>/` | Load/create only on genuine first run; refuse mismatches | A DID is not a device, wallet, or principal |
| Runtime identity metadata | `<DID_HOME>/identity_registry.jsonl` | Append non-secret observations and expose history/latest reads | This is metadata/provenance, not a second key store |
| Harness attribution | `IntegrityAgent` runtime | Store harness/profile/session context | Harness is not the logical agent |
| Cortex principal | Authenticated Cortex boundary | Carry exact principal/source attribution | Payload `agent_id` is not authorization |
| Shield device | Shield enrollment/binding authority | Carry device and invocation context; record decisions | Device binding is separate from DID continuity |
| Wallet/controller/owner | DID document, Oracle, and on-chain registry reads | Expose references when available; readiness checks remain fail-closed | A funder address does not prove controller authority |
| Signed protocol telemetry | Oracle v2/v3 ingestion grammar | Existing `IntegrityClient` signs and submits protocol telemetry | Developer envelope v1 is not the signed Oracle envelope |
| Agent-scoped memory | Cortex GraphStore/SQLite and existing genesis roots | Readiness detects DID-scoped stores; façade emits memory provenance events | Do not create duplicate stores for quant or Shield |

## Developer API

Minimal integration:

```python
from integrity_sdk import integrity

agent = integrity.auto()
```

Explicit integration:

```python
from integrity_sdk import PrivacyPolicy, integrity

agent = integrity.init(
    agent_id="my-agent",
    harness="custom-openai-compatible",
    memory="required",
    telemetry="sqlite",
    identity="persistent",
    privacy=PrivacyPolicy(mode="redacted", retention_days=30),
)
```

Lifecycle helpers are available through `SDKAgent`:

```python
with agent.session("session-123"):
    agent.prompt("hello", metadata={"channel": "api"})
    agent.model_request(provider="openai", model="gpt-4o-mini")
    agent.response("world")
    agent.token_usage({"input_tokens": 4, "output_tokens": 2})
    agent.tool_call("search", arguments={"query": "integrity"})
    agent.tool_result("search", result={"items": []})
```

The façade preserves the original exception from a session body and emits one
session-start and one session-end event. Unsupported host lifecycle hooks must
be reported by adapters rather than synthesized.

## Identity persistence and migration

`IntegrityAgent.open(...)` uses the existing canonical DID loader. It never
regenerates a key when a persisted key/document pair is incomplete or
inconsistent. `identity_snapshot()` returns non-secret metadata, and runtime
loads append an observation to `identity_registry.jsonl`.

The copy-only migration API is:

```python
from integrity_sdk import migrate_identity_store

migrate_identity_store(
    "my-agent",
    source_home="/old/.integrity/did",
    destination_home="/new/.integrity/did",
)
```

Migration validates the source document against the Ed25519 key, refuses a
conflicting destination, preserves the source, and merges only matching-agent
non-secret registry history. It does not delete the source or unlock a wallet.

Quantitative and Shield evidence already confirmed in the readiness work:

- `xibalba-quant` has a DID-scoped Cortex SQLite store and a non-zero on-chain
  `StateAnchor.latestRoot()`.
- `xibalba-shield` has a DID-scoped Cortex SQLite store and a non-zero on-chain
  `StateAnchor.latestRoot()`.
- Their local memory stores must not be replaced by new SDK-local vaults.

## Telemetry and delivery

`TelemetryEnvelope` schema version 1 carries event/provenance IDs, agent/DID,
harness, principal, device, session/invocation/trace relationships, wall and
monotonic timestamps, payload/metadata, privacy state, content hash, and
payload hash. Unknown event types fail at construction.

Available transports:

- `LocalEventStore`: append-only JSONL or SQLite;
- `CortexTransport`: authenticated `/api/otel/batch` export;
- `HttpTelemetryTransport`: authenticated generic JSON batch;
- `OTLPHttpTransport`: OTLP/HTTP JSON log projection;
- `MCPTelemetryTransport`: host-supplied MCP `call_tool` boundary.

HTTP, OTLP/HTTP, and Cortex retry transient failures with finite exponential
backoff. Event IDs are preserved as idempotency keys. Delivery receipts record
each actual attempt and distinguish `failed`, `retrying`, `acknowledged`, and
`dead-lettered`. Local acceptance is not a claim of remote indexing or
canonical persistence.

## Privacy and retention

`PrivacyPolicy` is applied before envelope hashing and local persistence:

- `mode="redacted"` is the default;
- `mode="metadata_only"` withholds content values;
- `mode="hash_only"` stores deterministic digest/length metadata;
- location is excluded unless `allow_location=True`;
- `max_content_chars` bounds content;
- `retention_days` uses SQLite expiry enforcement.

Append-only JSONL rejects retention configuration because it cannot honestly
erase historical bytes. The redactor covers private keys, seed/recovery
phrases, API/Bearer tokens, passwords, cookies, cloud/database/SMTP
credentials, SSNs, cards, emails, phones, and MRN markers. This is a heuristic
backstop, not a certified legal de-identification system.

## Verification evidence

From `integrity-sdk/`:

```bash
INTEGRITY_COLLECTION_PROFILE=development uv run pytest tests/unit -q --tb=short
# 246 passed, 1 skipped

INTEGRITY_COLLECTION_PROFILE=standard uv run \
  pytest tests/unit/test_collection_profiles.py tests/unit/test_batcher_reliability.py -q
# 18 passed

git diff --check
```

### Continuation verification — 2026-09-15

The first safe continuation gate was re-run from the current checkouts:

```bash
cd /home/xibalba/Projects/integrity-core/integrity-sdk
INTEGRITY_COLLECTION_PROFILE=development uv run pytest tests/unit -q --tb=short
# 246 passed, 1 skipped

cd /home/xibalba/Projects/xibalba-cortex
uv run pytest -q -ra \
  tests/test_auth_middleware.py \
  tests/test_local_api_retrieval_and_projection_routes.py \
  tests/test_server.py \
  tests/test_streamable_http_auth_integration.py
# 42 passed
```

This closes the local fixture-validation portion of the authenticated
Cortex memory/session/retrieval boundary. The cross-repository SDK-to-Cortex
write path was then exercised through a real local HTTP server and disposable
bearer token:

```bash
cd /home/xibalba/Projects/xibalba-cortex
uv run pytest -q tests/test_integrity_sdk_cortex_transport.py
# 2 passed
```

That test verifies authenticated `/api/otel/batch` delivery, session-scoped
persistence, and the required session-id refusal. It does not prove live
production consumption, real tenant data, or on-chain authorization.

Shield’s local device-binding and enforcement-correlation fixtures were also
re-run from the clean sibling checkout:

```bash
cd /home/xibalba/Projects/xibalba-shield
./.venv/bin/pytest -q \
  tests/test_agent_binding_and_redaction.py \
  tests/test_device_assertion.py \
  tests/test_invocation_id.py \
  tests/test_agent_core.py \
  tests/test_backend.py \
  tests/test_integrity_exporter.py -ra
# 69 passed
```

This confirms the local binding, invocation, backend, and exporter fixtures;
it does not prove privileged live-device enforcement or accepted on-chain
evidence. The `uv run` wrapper was not used because it attempted to rewrite a
root-owned virtualenv metadata file and failed before pytest started.

### Harness capability audit — 2026-09-15

The installed harness surfaces were checked without sending prompts or
performing external actions:

| Harness | Current evidence | Honest status |
|---|---|---|
| Claude Code 2.1.273 | User-local settings contain the four Xibalba lifecycle/tool hooks; all four hook scripts passed JSON and Python syntax checks | Local hook wiring verified; running-session automatic enforcement still needs a real Claude journey |
| agy 1.2.3 | `agy-cortex` plugin installed; native pre/post-model, completed-tool, and Stop delivery observed | Live observation validated; blocking enforcement remains unverified |
| Codex 0.154.0 | Effective plugin registry contains active `SessionStart` and `Stop`; the corrected `CodexLauncherProbe` reports `hook_surface: lifecycle` and those event names | Lifecycle hooks measured; plugin effects and PreTool/PostTool parity remain unverified |

Cortex runtime contract and adapter tests passed after this audit. The probe
result is promoted only to measured lifecycle capability, not to tool-hook
parity or production readiness.

### Browser validation gate — 2026-09-15

The in-app Browser was requested for the rendered Dashboard/Cortex proof, but
the current session reported no available browser connections. No DOM,
console, network, interaction, or screenshot evidence was therefore claimed.
Headless fallback remains a separate operator-approved gate.

The focused identity, transport, façade, redaction, and privacy tests passed
after the final implementation changes. The SDK source-binding audit found no
missing files, and wiki TOCs are current.

### Live readiness recheck — 2026-09-15/16

The configured local Oracle container's directory snapshot was reachable at
`http://127.0.0.1:8080/v1/agents/snapshot` and reported:

- chain ID `84532` (Base Sepolia);
- finalized snapshot block `46875829`;
- five registered DIDs;
- exact local-slot matches for `xibalba`, `xibalba-quant`, and
  `xibalba-shield`.

The exact local DID documents for `claude`, `codex`, and `agy` were read
without unlocking or generating wallet material. None of those three DIDs
appeared in the finalized snapshot, so no registration transaction was
attempted. The Cortex core-sync timer is enabled and waiting; its most recent
service run exited `0` and synchronized the Xibalba DID. Controller ownership,
primitive roles, wallet-control proof, and finalized registration logs for the
three unregistered harness slots remain open read-only gates.

### Continuation probe — 2026-09-16

The active Cortex API was rechecked read-only at `127.0.0.1:8420`. The bearer
credential returned HTTP 200 for `/api/status`, with profile `default`, WAL,
FTS5, backup readiness, and `memory_count_deferred=true`; the fast endpoint did
not perform an exact count on the multi-gigabyte store. The same credential is
not an interactive account-session cookie: `/api/auth/me` returned HTTP 401
(`account session not found`). No separate external tenant deployment was
present in the active Cortex service configuration, so live real-tenant
validation remains open.

The in-app Browser runtime was rechecked and reported zero available browser
connections. No rendered DOM, console, network, interaction, or screenshot
claim is made; standalone browser automation remains an operator-approved
fallback gate.

## Current repository state

The pushed `integrity-core` branch is synchronized with its origin. The only
remaining local artifact is the pre-existing untracked file:

```text
integrity-zkp/tools/commitment_calc/Prover_a8b3b22ff91d.toml
```

It is user-owned provenance and must not be removed or included casually in an
SDK documentation commit. `xibalba-shield` was not modified by the
documentation push. The continuation added the disposable SDK-to-Cortex
integration test at
`xibalba-cortex/tests/test_integrity_sdk_cortex_transport.py`.

## Remaining gates

### Agy callback adapter continuation

Cortex now accepts normalized Agy callbacks through `runtime_agy_hook`, protected
by the existing `memory:write` scope. Session start/end, turn observations, tool
outcomes, and tool errors are supported as forwarded observations. Tool inputs
and outputs are hashed, and raw error bodies are omitted. Upstream event IDs
provide retry deduplication with hook phase included in the identity; deliveries
without an upstream ID receive distinct observation IDs.

Validation: `uv run pytest tests/test_runtime_adapters.py
tests/test_runtime_bridge_contract.py tests/test_server.py -o addopts='' -q`
completed with **53 passed**. This includes MCP forwarding into persisted
telemetry, distinct pre/post phases, retry deduplication, and session closure.
The native `agy-cortex` plugin was subsequently installed and live-tested.
See the installation continuation below for automatic-delivery evidence.

### Native installation continuation (2026-09-15 local time)

### Hook ownership correction

The shared hook contract now lives in `integrity-sdk/integrity_sdk/harness_hooks.py`
as the exported `IntegrityHookAdapter`. It owns hook classification, session and
turn correlation, immutable SDK identity attribution, and bounded hashes for tool
inputs/results. Harness integrations should only register their native callbacks,
translate native field names, and pass the normalized payload to this SDK adapter.

The SDK also exports `normalize_hook` for bridges that write to a local
destination. Cortex's Agy adapter now consumes that shared normalizer through its
editable `integrity-sdk` dependency. CamelCase Agy events such as `PostToolUse`
and snake_case Hermes events therefore resolve to the same SDK event family.

The current Cortex Agy/Hermes modules remain compatibility shims for the live
local Cortex store and existing deployments. They are not the canonical home of
hook semantics. The Claude and Codex adapter entry points now also route their
correlation fields through the shared normalizer; the SDK adapter itself remains
the canonical home of hook semantics.

Continuation update: the Hermes production bridge now calls the SDK's
`normalize_hook` directly before constructing its Cortex outbox event
(`xibalba-cortex` commit `0b585cf`). This closes the shared-normalization gap
for Hermes; the Cortex subprocess still owns local-store dispatch and is not yet
a published SDK package consumer. The Agy native adapter and the Claude/Codex
compatibility adapters use the same SDK boundary as of `xibalba-cortex` commit
`498e67f`; Codex remains honestly lifecycle/forwarded-observation only because
native tool hooks were not verified.

The Cortex project now resolves `integrity-sdk` from an immutable Git
subdirectory revision rather than a sibling checkout (`xibalba-cortex` commit
`ead2e67`). Its lockfile and editable build were refreshed, and the focused
Hermes/Agy bridge suite passed 30 tests after the change. This closes the clean
deployment dependency boundary; it does not make live tenant or on-chain
validation complete.

The Cortex sdist was also checked with `--no-sources`: generated frontend
dependencies and test artifacts were excluded, reducing the archive from the
initial 111 MiB to 7.4 MiB (`xibalba-cortex` commit `9bf7729`).

SDK hook adapter validation: focused tests passed. The full SDK unit run remains
**245 passed, 1 skipped, 3 failed** in pre-existing MLflow/OpenAI sampling and
redaction expectations; those failures are outside the hook adapter files.

Agy tool canary `21e39463-92ec-4053-b836-f15051a4b93e` persisted native
`view_file` telemetry. After correcting Stop semantics, canary
`fd19984e-94ec-46ae-aabb-30d2e7b7eec1` persisted PreInvocation,
PostInvocation, and Stop with a successful hook response.

Hermes already had the enabled `xibalba_cortex` plugin with 21 declared hooks.
Research against upstream documentation and installed source identified two
adapter corrections: claim the exact queued event, and treat `on_session_end`
as run-scoped rather than final conversation closure. The installed plugin's
outbox default is 16 MiB after the resource-exhaustion remediation; existing
evidence was preserved and the pre-existing graph-store queue remains
untouched. Sustained retention remains open.

Hermes live canary `20260915_204246_a9a96e` returned its expected response,
persisted API and successful read_file tool events, and produced nine Cortex
delivery acknowledgements. This does not establish Oracle acceptance or policy
enforcement. Detailed evidence and primary sources are recorded in
`xibalba-cortex/docs/architecture/harness-hook-installation.md`.

Focused Hermes/outbox/Agy bridge suite: 36 passed. After the Hermes lifecycle
correction, the Hermes observer/bridge suite passed 24 tests. The live Cortex
API at port 8420 rejected an unauthenticated status request with HTTP 401.

### Resource-exhaustion controls

The 2026-09-15 live incident was traced to two independent unbounded paths:
the Codex watcher repeatedly parsing growing JSONL transcripts and the Cortex
FTS/BM25 query holding a process-wide store lock while ranking a common term.
The watcher now hard-caps each scan at 32 recent files, 128 reconstructed
turns, and 32 MiB per transcript. Its user-service unit enforces 512 MiB RAM,
512 MiB swap, 50% CPU, 128 tasks, and a three-failures-per-five-minutes start
limit. The local Cortex API unit is separately capped at 1 GiB RAM, 1 GiB swap,
100% CPU, 64 tasks, and 1024 open files. FTS ranking uses a read-only WAL
connection and a two-second progress deadline. The Hermes telemetry outbox cap
is explicitly 16 MiB; this is a queue bound and does not resize or prune the
existing graph database.

The read-connection path also invalidates thread-local readers after a backup
restore, preventing stale FTS rows from being dereferenced as deleted memories.
Fast status now defers exact `memories` counts for stores above 256 MiB, so
the liveness endpoint cannot trigger a full-table count on the current
multi-gigabyte profile. After the API restart, the existing local viewer
credential returned HTTP 200 for `/healthz`, `/api/auth/me`, and `/api/status`;
the latter reported WAL, FTS5, backup readiness, and
`memory_count_deferred=true` without exposing the exact count.

The controls were reloaded into the active Codex backfill service and the
regression suite passed 12 tests, including the FTS deadline and 16 MiB
outbox-default assertions. No live graph-store deletion, compaction, or
broad retrieval probe was performed during this remediation.

### Outbox storm recheck — 2026-09-16

The live root-owned Shield outbox unit was rechecked after the bounded Cortex
tests. Its installed configuration still had eight concurrent outbox workers,
batch size 100, a ten-second interval, and `Restart=always`. The worker held
179 file descriptors while the Cortex API reached approximately 43.8% CPU and
accumulated a large `CLOSE-WAIT`/`FIN-WAIT-2` socket population. The worker's
systemd accounting showed a 2.5 GiB memory peak. This is an active retry and
connection storm, not merely historical resource usage.

The worker was stopped and immediately relaunched by `Restart=always`; the
second instance reached approximately 568 MiB RSS within seconds. It was
therefore frozen with `SIGSTOP` as an emergency containment measure, and the
Cortex API was restarted to clear the accumulated connections. Port 8420 then
had no active outbox connections. The permanent packaging fix is pushed in
`xibalba-shield` commit `001a2b5`: one worker, batch size 10, 30-second cadence,
`Restart=on-failure`, start-rate limiting, and the existing 256 MiB / 25% CPU /
64-task / 1024-FD limits. Root installation and unfreezing/replacement of the
live unit remain required; the package commit is not represented as live until
that installation is independently verified.

The provider itself now supplies a second boundary in `xibalba-shield`
commit `58323c8`: it clamps publishing to one worker and ten rows per flush,
rejects payloads over 64 KiB, caps the SQLite outbox (including WAL sidecars)
at 16 MiB, and uses a one-second busy timeout. These controls are now present in
the running `/opt/xibalba-shield` installation; the live verifier reports the
16 MiB/10-row/1-worker caps and the worker's aggregate-count bypass.

The storage-ceiling regression is now explicitly covered by the Shield suite
(`xibalba-shield` commit `b8f0084`; 10 focused tests pass).

For the live root-owned unit, `xibalba-shield` commit `faa42f1` adds
`scripts/install_live_cortex_outbox_limits.sh`. It is an idempotent privileged
installer that writes the drop-in, resumes and stops the frozen worker in the
safe order, reloads systemd, starts the bounded service, and prints the
effective cgroup limits. The operator has now installed those limits successfully;
`systemctl show` confirms 256 MiB RAM/swap, 25% CPU, 64 tasks, and 1024 FDs.
The running `/opt/xibalba-shield` virtualenv was subsequently upgraded with
`scripts/update_live_cortex_outbox_package.sh` from `xibalba-shield` commits
`a7a60bd`, `bcfaa9f`, and `94479e2`. The live worker now uses the count bypass,
and a bounded 15-second sample measured only about 209 KiB of additional reads
(versus about 225 MiB before the bypass), with TCP entries decreasing from 54
to 44. The provider also treats SQLite lock contention as a failed retry
rather than crashing the worker.

The installer now preserves the unit's configured `SHIELD_DEVICE_ID` instead
of embedding this workstation's device identifier (`xibalba-shield` commit
`9626c79`).

These are not silently represented as complete:

The current cross-repository baseline and performance evidence are tabulated
in `docs/audits/2026-09-16-cross-repository-validation-matrix.md`.

The nineteen stale low-severity wiki pages were source-reverified and refreshed
in the 2026-09-15 wiki pass; the current audit reports 35/35 pages current.
The historical-count discrepancy remains recorded in `docs/wiki/WIKI_LOG.md`.

1. automatic production adapters and lifecycle hooks for each named harness;
2. authenticated Cortex memory/session/retrieval end-to-end validation against
   a live deployment and real tenant data;
3. rendered Dashboard/Cortex browser journeys with DOM, console, network, and
   screenshot evidence;
4. strict readiness for controller, roles, ownership/control, and finality;
5. on-chain registration for Claude, Codex, and Agy;
6. full performance and cross-repository integration matrix;
7. TypeScript/Node package support, if the ecosystem later establishes a
   canonical Node package boundary;

## Safe next operator sequence

1. Read each repository's Git status independently before touching it.
2. Preserve the exact DID slots for `xibalba`, `xibalba-quant`, and
   `xibalba-shield`; do not map the separate `quant` slot by label similarity.
3. Use read-only readiness checks and exact on-chain addresses before any
   registration or ownership action.
4. Provision disposable authenticated Cortex/Shield fixtures before testing
   cross-system writes.
5. Use a real browser journey for Dashboard/Cortex validation; source, API, or
   build output alone is insufficient.
6. Treat unavailable Oracle/RPC, unknown finality, missing controller/roles,
   and denied Shield decisions as fail-closed states.

## Evidence classification

| Statement | Classification |
|---|---|
| SDK API, identity loader, registry journal, migration, transports, privacy policy | Source-confirmed and test-confirmed |
| Full development-profile SDK unit suite | Test-confirmed: 246 passed, 1 skipped |
| Quant and Shield DID-scoped memory/genesis stores | Filesystem-confirmed and on-chain-confirmed in readiness evidence |
| Branch `feat/harness-neutral-agent-runtime` contains published documentation commit | Git/API-confirmed |
| Live cross-repository production consumption | Partially verified; not a completion claim |
| Browser-rendered Dashboard/Cortex success | Not verified in this handoff |
| Full registration readiness for all six agents | Not achieved; fail-closed blocks remain |
