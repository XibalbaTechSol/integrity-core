# Cross-repository validation matrix — 2026-09-16

This matrix is the current production/live validation boundary for
`integrity-core`, `xibalba-cortex`, and `xibalba-shield`. A passing local test is
reported as test evidence only; it is not promoted to deployment, tenant, or
on-chain evidence.

## Executed checks

| Boundary | Command or probe | Result | Evidence class |
|---|---|---:|---|
| SDK hook contract | `uv run pytest -q tests/unit/test_harness_hooks.py tests/unit/test_cross_system_adapters.py tests/unit/test_readiness.py` | 13 passed | SDK test-confirmed |
| Harness binaries | `claude --version`, `codex --version`, `agy --version`, `hermes --version` | Claude 2.1.273; Codex 0.154.0; Agy 1.2.3; Hermes 0.20.0 | installed-host evidence; version checks only |
| Cortex runtime adapters | `uv run pytest -q tests/test_runtime_adapters.py tests/test_runtime_bridge_contract.py tests/test_agy_hook_bridge.py tests/test_hermes_bridge.py tests/test_hermes_observer.py tests/test_telemetry_outbox.py` | 65 passed | Cortex test-confirmed |
| Cortex full test suite | `uv run pytest -q` | completed with exit code 0; temporary-store tests only, with deprecation warnings | Cortex full-suite evidence |
| Claude/Codex SDK normalization | `uv run pytest -q tests/test_runtime_adapters.py` | 25 passed; `xibalba-cortex` `498e67f` | adapter test-confirmed; live native hook delivery not claimed |
| Shield binding/redaction/outbox | `./.venv/bin/pytest -q tests/test_agent_binding_and_redaction.py tests/test_e2e_validate.py` | 11 passed; includes worker count-skip regression from `xibalba-shield` `bcfaa9f` | Shield test-confirmed |
| Shield live containment | `scripts/validate_local_containment.sh` | `CONFIRMED_SIGSTOP` | privileged live-device evidence |
| Shield device correlation | device-authenticated `POST /api/shield/exporter-status` plus admin `verify_live_shield_admin_correlation.sh` readback | device POST HTTP 200 `{"ok":true}`; admin readback HTTP 200 with 3 exporter-status rows | privileged live device correlation confirmed |
| Shield live cgroup limits | `verify_live_cortex_outbox_limits.sh` plus `systemctl show` | installed and active; provider caps and aggregate-count bypass verified live; 256 MiB RAM/swap, 25% CPU, 64 tasks, 1024 FDs | live host evidence |
| Cortex fast liveness | authenticated `GET /api/status` on `127.0.0.1:8420` | 200; WAL, FTS5, backup ready; exact count deferred | live local service evidence |
| Integrity directory | `GET /v1/agents/snapshot` on `127.0.0.1:8080` | finalized Base Sepolia snapshot, chain 84532, five agents | live Oracle evidence |
| Independent chain finality | read-only `eth_getBlockByNumber` against `https://sepolia.base.org` | finalized block 46891468, latest block 46892134, finalized hash present and not ahead of latest | public RPC evidence; no transaction submitted |
| Finality helper gate | `./scripts/enable_finality_after_evidence.sh` with default dry-run mode | RPC finalized block 46891468 and latest block 46892161; dry run preserved the approval bit | executable readiness evidence; no mutation |
| Target harness Oracle readback | bounded `GET /v1/agent/{did}` for the existing Claude, Codex, and Agy DID documents | HTTP 404 for all three; no local Oracle registration evidence; this is not an on-chain absence claim | live Oracle negative evidence |
| Target harness chain readback | `uv run --project integrity-sdk python scripts/audit_harness_registry_readback.py` | `chain_id=84532`; `onchain_registered=false` for Claude, Codex, and Agy; no wallet or transaction path invoked | live public-chain negative evidence |
| Resource containment | bounded worker verifier plus 15-second `/proc` I/O/socket sample | live worker stable under 256 MiB/25% cgroup; read delta ~209 KiB and port-8420 TCP entries fell 54→44 | live host evidence |
| Bounded disposable benchmark | `uv run python scripts/benchmark_bounded.py --memories 100 --iterations 20` | ingest 271.080 ms; search p50/p95/max 2.018/3.620/3.643 ms; fast-status p50/p95/max 0.043/0.117/0.683 ms | reproducible local performance evidence |
| Clean Cortex artifact | `uv build --sdist --wheel --no-sources` plus archive inspection | 7.4 MiB sdist and 275 KiB wheel; generated viewer dependencies/test artifacts excluded; wheel metadata carries immutable SDK Git pin | packaging test-confirmed |

## Performance observations

| Scenario | Observation | Interpretation |
|---|---:|---|
| Shield outbox before containment | eight workers, batch 100, 179 FDs; Cortex ~43.8% CPU | confirmed retry/connection storm |
| Shield outbox after containment | one live worker, batch 10, 30-second cadence; no renewed high-volume scan after count bypass | permanent bounded containment effective; delivery health still depends on valid Cortex authorization |
| Cortex fast status on large store | `memory_count_deferred=true` | liveness no longer performs an exact full-table count |
| Shield full suite excluding release installer | 331 passed, 12 skipped in 112.18s | broad local regression evidence; installer remains separate |

No sustained throughput, latency percentile, or burn-in SLO is claimed. Those
measurements require a bounded disposable fixture and an agreed workload; the
multi-gigabyte live graph store must not be used for an unbounded benchmark.
The benchmark harness is `xibalba-cortex/scripts/benchmark_bounded.py`; it
always creates a temporary store and hard-caps fixture size and iterations.

## Unverified production gates

| Gate | Required evidence | Current state |
|---|---|---|
| Authenticated real tenant | account session plus read/write/retrieval journey against a deployed tenant | not available; current bearer credential is not an account session |
| Rendered UI | Browser DOM, console, network, interaction, and screenshots | in-app Browser reports zero connections |
| Controller/role/ownership readiness | exact controller, primitive-role, wallet-control, and ownership readbacks for required identities | finality is independently verified, but no on-chain records exist yet for the three new harnesses, so their controller/role/ownership evidence is absent |
| New harness registrations | finalized registry records and accepted transaction receipts for Claude, Codex, Agy | broadcast not attempted; wallet/control authorization absent after read-only preflight |
| Full matrix | repeated performance, failure, recovery, and cross-repository canaries | partial; rows above are the safe current baseline |

## Gate 5 independent cross-product UI evidence — 2026-09-25

**Result: DEFERRED/BLOCKED — rendered evidence could not be collected from the
current host state.** This is an availability boundary, not evidence that any
agent, event, namespace, or external acceptance is absent.

| Surface | Canonical local URL | Probe result | Evidence boundary |
|---|---|---|---|
| Shield UI | `http://127.0.0.1:4176` | connection refused; no UI route, DOM, accessibility tree, console, network, or screenshot evidence | unverified |
| Cortex UI | `http://127.0.0.1:5190` | not reached after the first Browser navigation was refused; shell probe also returned connection failure | unverified |
| Integrity Dashboard | `http://127.0.0.1:5189` | shell probe returned connection failure; no rendered evidence | unverified |

The documented backend listeners (`8420`, `8435`, `8765`, and `8421`) also
returned connection failures, and no relevant UI/service process was visible.
The user-service query itself was unavailable because the session could not
connect to the system bus, so unit state is **unverified**. The in-app Browser
navigation to the first canonical URL independently reported
`net::ERR_CONNECTION_REFUSED`. No dev server was started because Cortex's dev
configuration can issue/write a local operator token on first boot, and this
Gate 5 pass did not authorize credential or identity mutation.

Read-only persisted-state observations: the Cortex graph store contained 3,184
memories, 237 sessions, 3,202 inference tasks (3,117 pending and 17 failed),
and 2,309 OTel events; the Shield Cortex outbox contained 3,108 sent and 2
dead-lettered rows. The Shield decision log existed but was not readable by the
current user, so `evt-79568b9aed44`'s exact DID, invocation, device, content
hash, and evidence class/status remain **unverified**. These counts are not
rendered UI proof and do not establish cross-product namespace continuity.

The three repositories were clean at probe time. Source inspection confirms
distinct UI projects/routes and scoped-namespace code paths, but source intent
does not satisfy this gate's rendered screenshot verdict. Gate 5 therefore
remains open pending live, independently captured desktop and narrow-view
evidence for all three products, including route, accessibility, console,
network, HTTP accessibility, selector/workflow, and ownership checks. The Gate
4 exception boundary remains in force: no replay or diagnostic receipt is
reclassified as original-event acceptance.

### Gate 5 rendered continuation — 2026-09-25

The frontend-only validation pass reached all three canonical browser URLs
without entering credentials. It provides desktop screenshots and
accessibility-tree evidence, but it does **not** satisfy the full gate because
the scoped APIs do not agree and the narrow viewport pass was not available in
the connected browser surface.

| Product | Rendered route/workflow | Observed evidence | Gate result |
|---|---|---|---|
| Shield | `/` → `Open console` → local operator sign-in | Distinct Shield landing/architecture shell; auth boundary rendered with `HttpOnly session cookie` language and no credential submission. The form showed a local `502 Bad Gateway` state; no protected event workspace was reached. Read-only backend SQLite corroborates the target decision: `evt-79568b9aed44`, invocation `94d4fb7c-3ede-4e13-883a-0712b7447bf7`, device `xibalba-HP-Desktop-M01-F0xxx`, class `process_activity`, action `contain`, policy hash `sha256:117eea18bd22a026bd2fa46dd36d33b4f6ecdfd54f1e33eac451c8d76515dcf2`, `export_ok=0`, `synthetic=0`; the decision has `agent_id=null` and `intended_state_hash=null`. The read-only outbox adds scoped source DID `did:integrity:2ea17967f7a65589d570ca7e800844701fb36e6aa7374243e8766de8651f6bc4`, `evidence_class=observed_event`, `status=candidate`, `attempts=7`, and `last_error=HTTP Error 403: Forbidden`. No explicit signed `content_hash` field exists; SHA-256 of the exact stored `content` string is `df3ea908ade3b005bcd068adf13e580b71a3ccfe619bd696ae1239bf65c5ebb1`, derived only and not an acceptance receipt. | partial; exact scoped payload verified read-only, UI display and signed content hash unverified |
| Cortex | `/` → `Open workspace` | Distinct Cortex workspace loaded at a URL carrying exact `agent_id=did:integrity:68fed1331613937555a59398223e8e87520a87dd0305aac4fd7ecdc32a14a861` and `store_id=store-0688613ab599cbb5`. The active selector exposed only `xibalba`, `pseudonym:2e93…736daa15`, and `xibalba.agent`, all under `default`; required Codex, Shield, AGY, Claude, and Quant labels were not present in this authorized selector state. The UI reported 18 memories and 4 sessions, which does not match the separately sampled persisted graph store (3,184 memories and 237 sessions). | blocked for namespace continuity and scope agreement |
| Integrity Dashboard | `/financials` → `/treasury` | Distinct protocol navigation and Treasury workflow rendered with Wallet/Staking/Credit/Markets/Stability tabs. The page honestly showed `Wallet offline`, `Operator — Sign-in required`, and `No agent selected`; however, zero financial metrics and `No agents registered` are not independently API-confirmed in this unauthenticated state. | partial; financial and namespace proof unverified |

The three desktop screenshots and AX snapshots are independent browser evidence
for the states above. Browser console capture also contained repeated
`Access to storage is not allowed from this context` errors for the local app
origins; extension-origin listener warnings were present separately. These
errors are recorded rather than silently treated as clean console health.

No Shield UI readback or three-way scoped API comparison was obtained. The
event’s backend and outbox payload are verified read-only; the explicit signed
content hash remains absent and the computed SHA-256 is derived only. The
same event ID has no matching row in the read-only Cortex `sources`, `memories`,
`memory_events`, or `otel_events` tables, so the outbox `sent` state is delivery
telemetry only, not Cortex acceptance.
The read-only namespace stores also disagree: Cortex `agent_devices` reports
`did:integrity:68fed1331613937555a59398223e8e87520a87dd0305aac4fd7ecdc32a14a861`,
while Shield’s registered device and outbox source report
`did:integrity:2ea17967f7a65589d570ca7e800844701fb36e6aa7374243e8766de8651f6bc4`.
This is an identity-continuity failure, not a duplicate to silently merge.
The implementation boundaries corroborate the finding: Cortex populates its
selector from the scoped `/api/agents` response keyed by `{store_id, agent_id}`;
the Dashboard populates its selector from its separate registry response, while
Shield’s canonical selector/workspace is behind the unauthenticated sign-in
boundary. No source-level fallback authorizes substituting one product’s list
for another’s.
Gate 4 exception boundary is unchanged: no replay, diagnostic, or unavailable
receipt is promoted to original-event acceptance. Gate 5 remains
**DEFERRED/BLOCKED**, not PASS.

Narrow viewport screenshots were subsequently captured in temporary files:
`/tmp/gate5-shield-mobile.png`, `/tmp/gate5-cortex-mobile.png`, and
`/tmp/gate5-dashboard-mobile.png`. Visual review found Shield and Cortex
readable at 390×844; the Dashboard landing view clips its horizontal
navigation and breaks the word “mathematically” across lines, so its narrow
responsive evidence is a finding rather than a pass.

Screenshot artifact recheck: all three narrow PNGs remain present at `390×844`:
`gate5-shield-mobile.png` SHA-256
`81c9ee428fc5d413bf1dc2e95ccd0251e4e5dd088bd1deabc4aa16e6c299ed09`,
`gate5-cortex-mobile.png` SHA-256
`3709eee159adfbc28d4862044eae3281e1cbef917e06110396960777dabedcf2`, and
`gate5-dashboard-mobile.png` SHA-256
`e09c1032ee5f72cc03a208017a6145a10b8f42e1b9b1268cf8cda968b800bf9d`.
The retained connected Chrome tab currently shows `ERR_CONNECTION_REFUSED` for
`http://localhost:5173/`; no target live-service tab is available for a fresh
readback. Build output did not add tracked repository changes: Shield and
Cortex remain clean, and only the documented integrity-core handoff matrix is
dirty.

Static ownership/build recheck: Shield UI, Cortex viewer, and Integrity
Dashboard each completed their package build successfully. The source route
surfaces remain distinct: Shield owns its console views and `Event stream` /
`Shield agent` tabs; Cortex owns its landing/auth/workspace and scoped memory
tabs; Dashboard owns `/dashboard`, `/agents`, `/evidence`, `/treasury`, and
`/system`, with `/financials` redirecting to `/treasury` and `/shield`
redirecting to `/dashboard`. Build output contained only existing size/chunking
warnings, including Dashboard’s ineffective dynamic import of `WikiPage`; no
build failure or duplicate cross-product route was found. This is source/build
evidence only and does not replace unavailable live API agreement.

Earlier read-only runtime/state sample (superseded by the live-origin recheck
below): no listener was present on the target UI/API ports and no Shield,
Cortex, Vite, or Uvicorn process was present at that sample time. The
checked-in service declarations specify backend port `8435`
with `MemoryMax=512M`, `CPUQuota=50%`, `TasksMax=128`; the Shield agent uses
`MemoryMax=128M`, `CPUQuota=25%`, `TasksMax=64`; and the Cortex outbox uses
`MemoryMax=256M`, `CPUQuota=25%`, `TasksMax=64`. The read-only Cortex store
sampled 3,184 memories, 390 sessions, 3,174 sources, one `agent_devices` row,
and 3,761 OTel events. The read-only outbox contained 1,648 `sent` rows and
two `dead_letter` rows, with maximum attempts seven for sent rows; cumulative
metrics reported `delivered_total=3108`, `dead_letter_total=2`, and
`capacity_dropped_total=6424`. The target event remains `sent`, attempts `7`,
with `HTTP Error 403: Forbidden`. These are current samples, not acceptance
receipts; the changing session/telemetry totals are not silently reconciled
with the earlier UI counts.

Live-origin recheck: `https://localhost:9443/` served the canonical Cortex
landing UI in the connected browser, with the same distinct navigation and
provenance-first workflow; its `/api/agents` endpoint returned `401
authentication required`, and no credentials were entered. `https://localhost:9444/`
served the canonical Shield landing UI and its sign-in form; its `/api/health`
request returned `502` because the Caddy route targets `127.0.0.1:8421`, where
no listener exists. The checked-in Shield backend unit instead declares port
`8435`, so the active Caddy route and declared backend port are themselves
inconsistent. The Shield sensor process and Cortex outbox worker are active,
but this does not provide a writable authenticated Shield workspace or event
readback. The Dashboard Vite process is active on `127.0.0.1:4173` and its
route shells return HTTP 200, but connected-browser access to that port was
denied by browser permission policy; no workaround or credential entry was
attempted. Current live screenshots/AX evidence therefore proves the two
canonical origins independently, while Dashboard visual evidence remains the
previous captured sample rather than a fresh live-origin verdict.
The live Shield browser console also recorded four repeated local-origin
`Access to storage is not allowed from this context` errors; separate
extension-origin `MaxListenersExceededWarning` and `ObjectMultiplex` warnings
were attributed to the browser extension and not the app. Process samples at
the same recheck showed Shield sensor RSS about 74 MiB (14 threads), Shield
outbox about 22 MiB, Cortex API about 30 MiB, and Dashboard Vite about 46 MiB;
these observations remain below the declared service caps but do not prove
systemd ownership or healthy API agreement.

## Gate 5 remediation continuation — 2026-09-25

The Caddy/backend port mismatch was corrected in the tracked local-auth Caddyfile:
Shield now proxies `/api/*` to `127.0.0.1:8435`, matching the checked-in backend
declaration. The in-scope user Caddy service was restarted and is active
(`MainPID=1340305`); direct `http://127.0.0.1:8435/api/shield/health` and
canonical `https://localhost:9444/api/shield/health` both return HTTP 200. The
installed root-owned `xibalba-shield-backend.service` remains inactive and stale
at 8421; it could not be edited without root authorization at the time of this
entry. The later service-ownership continuation below records the current
user-level ownership state for the healthy 8435 listener.

The persisted DID finding is now scoped precisely rather than merged or rewritten:
Shield’s device and outbox DID `did:integrity:2ea17967f7a65589d570ca7e800844701fb36e6aa7374243e8766de8651f6bc4`
matches the read-only Cortex profile `xibalba-cortex-shield`; Cortex’s root
profile DID `did:integrity:68fed1331613937555a59398223e8e87520a87dd0305aac4fd7ecdc32a14a861`
belongs to a separate default profile. No identity, database, WAL, queue, or
historical event was rewritten. Full authenticated selector/workspace continuity
remains unverified.

Cortex remains truthfully auth-gated: canonical `/api/agents` returns HTTP 401,
and no credentials were entered or created. Dashboard route shells continue to
return HTTP 200 on port 4173, but connected-browser visual access remains denied
by browser permission policy; no workaround was attempted.

The Shield producer now includes an explicit `content_hash` (`sha256:<digest>`)
for future deliveries and validates Cortex’s returned memory ID and matching
`content_hash` before marking an outbox row `sent`. The historical target row
`evt-79568b9aed44` remains unchanged (`sent`, seven attempts, prior HTTP 403),
has no persisted Cortex memory/acceptance receipt, and was not requeued or
resubmitted. Therefore the target’s historical hash/receipt blocker remains an
honest limitation rather than a retroactive claim.

Gate 4 replay/diagnostic boundaries remain preserved: no replay, diagnostic
response, unavailable receipt, or manually launched local backend is promoted
to original-event acceptance. Gate 5 remains **DEFERRED/BLOCKED** pending
authorized Cortex credentials, Dashboard browser access, privileged backend
service ownership, and a future authenticated event with a retained acceptance
receipt.

UserAPI ownership remediation: UserAPI was healthy on port 8090, but its CORS
allowlist omitted the active Dashboard preview origin `http://127.0.0.1:4173`.
Both localhost and loopback 4173 origins were added and the UserAPI image was
rebuilt/restarted; health and browser-origin preflight now return HTTP 200.
The existing `jacob.v.universe@gmail.com` account had no `user_agents` rows.
Per operator authorization, the five persisted local DIDs were associated with
that account: the root Cortex DID, Shield DID, AGY DID, Claude DID, and Quant
DID. Profile stores and DID material were not merged or rewritten.

Playwright fallback validation was authorized after connected-browser access was
blocked. It reached the Dashboard at `http://127.0.0.1:4173/` on desktop and
390x844 mobile viewports, rendered the auth page, and exercised the Dashboard
link to `/auth`. The first run exposed a separate live defect: Cortex 8420
returned wildcard CORS while Dashboard sent credentialed requests, causing
browser CORS failures for `/api/agents` and `/api/auth/me`. The user Cortex
service allowlist now explicitly includes both `http://localhost:4173` and
`http://127.0.0.1:4173`; preflight returns the exact origin with credentials
enabled. The rerun had no failed requests or CORS errors; remaining HTTP 401s
from Cortex/UserAPI are the honest unauthenticated boundary.

Service-ownership continuation: the stale root-owned system unit remains an
unmodified installation artifact at 8421. The healthy 8435 backend was moved
from the manual process into an enabled user-level
`xibalba-shield-backend.service` with `MemoryMax=512M`, `CPUQuota=50%`, and
`TasksMax=128`; its current main PID is `1388295`. The read-only boundary
verifier reports `PASS backend service owns port 8435`; canonical Shield health
remains HTTP 200. The separate Integrity SDK outbox unit is inactive and
disabled; it is not being conflated with the active Shield outbox worker
(`PID=516225`), whose live queue remains capacity-constrained and untouched.

Equivalent-condition validation: without replaying or rewriting the historical
target, one new explicitly synthetic Shield validation event was submitted
through the authorized local Shield-to-Cortex path. Event
`evt-equivalent-validation-67c53a2401a6` used the same process-activity/contain
condition, device, and policy hash as the target, with fresh invocation
`3e2b5482-afea-4337-bd21-b26bb9425be3`. Its explicit content hash is
`sha256:7d89f3714c9ee4cf717b85bdb5c561cfad55c647bc67df1664539f26d322a835`;
the temporary validation outbox recorded `sent`, and Cortex profile
`xibalba-cortex-shield` stored memory
`a19a54ff-c0f2-4088-b36e-ba90e02346ad` with the exact same hash and Shield DID.
No real containment was performed. The original `evt-79568b9aed44` remains
unchanged and is not represented as accepted by this equivalent event.
Three preliminary development-fixture decisions (`evt-360ee082c789`,
`evt-b7074fae5096`, and `evt-b1521522bdae`) were local-only attempts before
the temporary outbox was used; they produced no Cortex receipt and performed
no real containment. They remain retained as synthetic local evidence.

Current rendered-evidence continuation: connected-browser access remains denied
by the saved browser permission policy, so it is still unavailable evidence.
With the operator-authorized Playwright fallback, fresh desktop (1440x900) and
narrow (390x844) screenshots were captured for each independent product:
`/tmp/gate5-shield-desktop-fresh.png`,
`/tmp/gate5-shield-narrow-fresh.png`,
`/tmp/gate5-cortex-desktop-fresh.png`,
`/tmp/gate5-cortex-narrow-fresh.png`,
`/tmp/gate5-dashboard-desktop-fresh.png`, and
`/tmp/gate5-dashboard-narrow-fresh.png`. Shield, Cortex, and Dashboard each
rendered distinct navigation and accessibility structures. Shield and Cortex
reached their honest unauthenticated sign-in boundaries without failed network
requests; Dashboard reached `/auth` without CORS failures, with only expected
401 responses from the protected Cortex and UserAPI endpoints. This verifies
the fallback rendering path, but does not satisfy authenticated namespace
readback or connected-browser evidence.

The equivalent synthetic event above satisfies the new-condition hash/receipt
check only for that new event. It does not clear the historical target’s lack
of an explicit signed content hash or Cortex acceptance receipt, and it does
not authorize credentials or change the Gate 4 replay/diagnostic boundary.
Therefore the overall Gate 5 result remains **DEFERRED/BLOCKED**, with the
remaining blockers limited to authorized authenticated namespace continuity,
the historical target receipt/hash, and unavailable connected-browser proof.

Read-only revalidation after that entry confirmed the same boundaries without
creating fixtures or changing live state. Current Playwright captures are
`/tmp/gate5-current-shield-desktop.png`,
`/tmp/gate5-current-shield-narrow.png`,
`/tmp/gate5-current-cortex-desktop.png`,
`/tmp/gate5-current-cortex-narrow.png`,
`/tmp/gate5-current-dashboard-desktop.png`, and
`/tmp/gate5-current-dashboard-narrow.png`. Shield's `Open console`, Cortex's
`Open workspace`, and Dashboard's `Launch MVP Dashboard` each lead to that
product's own sign-in boundary; they do not merge into a shared console.
Shield and Cortex had no failed requests or console errors. Dashboard's only
errors were the expected 401 responses from protected Cortex/UserAPI calls.
The current outbox remains `sent=1`, `dead_letter=2`, with
`capacity_dropped_total=6427`, `delivered_total=3108`,
`dead_letter_total=2`, and a 4,618,552-byte WAL; these records were inspected
read-only and left untouched.

Resumed-audit recheck on 2026-09-26: canonical Cortex `/api/agents` and
Shield `/api/shield/auth/me` still return HTTP 401 without authorized
credentials. Playwright freshly re-rendered all three public surfaces at
desktop and narrow viewports with the following captures:
`/tmp/gate5-resume-shield-desktop.png`,
`/tmp/gate5-resume-shield-narrow.png`,
`/tmp/gate5-resume-cortex-desktop.png`,
`/tmp/gate5-resume-cortex-narrow.png`,
`/tmp/gate5-resume-dashboard-desktop.png`, and
`/tmp/gate5-resume-dashboard-narrow.png`. Shield and Cortex had no failed or
error responses; Dashboard's only non-2xx responses were the expected 401s
from protected Cortex/UserAPI calls. No fixture, resubmission, database/WAL/
log/identity mutation, unrelated restart, commit, or push occurred during
this resumed audit.

Second resumed-audit auth check: UserAPI is reachable and healthy on port 8090
(`GET /health` HTTP 200), but `/me` returns the truthful unauthenticated
boundary HTTP 401 (`missing bearer token or api key`). Cortex `/api/agents`
and Shield `/api/shield/auth/me` likewise remain HTTP 401. This distinguishes
an available authentication service from an authorized session; namespace and
scoped-event readback therefore remain unverified without operator-authorized
credentials.

Shield authenticated-session evidence on 2026-09-26: the connected browser
session rendered the protected `tenant-a` console for `Jacob V. Universe`.
Fleet and identity showed the enrolled device
`xibalba-HP-Desktop-M01-F0xxx`, Shield DID
`did:integrity:2ea17967f7a65589d570ca7e800844701fb36e6aa7374243e8766de8651f6bc4`,
pair ID `3c63eb90bcd67c33a6146f00`, local authority `Shield · active`, and
Cortex memory namespace `shield:did:integrity:2ea17967f7a65589d570ca7e800844701fb36e6aa7374243e8766de8651f6bc4`.
The UI truthfully reported Cortex delivery as 1 sent, 2 dead-letter, 3108
delivered, and evidence `Unverified`; it also showed no authenticated agent
events. The shared-agent namespace selector contained only `Select agent` and
no agent labels.

The authenticated Shield command center listed the historical target
`evt-79568b9aed44`; opening its detail displayed a completed `freeze` outcome,
the exact device ID, event ID, timestamp, and `received_at`, but no invocation
ID, signed content hash, or Cortex acceptance receipt. The UI therefore
provides stronger scoped visibility while confirming that the target’s missing
hash/receipt and cross-product namespace blockers are not resolved.

Cortex authenticated-session evidence on 2026-09-26: the connected browser
rendered the root workspace at
`agent_id=did:integrity:68fed1331613937555a59398223e8e87520a87dd0305aac4fd7ecdc32a14a861`
and `store_id=store-0688613ab599cbb5`, with profile `default · writable`.
Its active-agent selector exposed only `xibalba`,
`pseudonym:2e93…736daa15`, and `xibalba.agent`; Codex, Shield, AGY, Claude,
and Quant labels were not present. Searching this root scope for
`evt-79568b9aed44` returned `No memories in this view`. A direct authenticated
route using the Shield DID resolved to `Profile unavailable · store scope
unavailable` with a disabled `No registered agents` selector. This is direct
rendered evidence that Cortex authentication works but the required Shield
profile/store continuity is not currently exposed by the root workspace.

Root-cause trace (read-only): the Cortex account database records Jacob’s
`agent_ids_json` as only the root DID, `pseudonym:2e93…736daa15`, and
`xibalba.agent`; the finalized registration for the root DID is revoked. The
Cortex local API intentionally filters its mounted read-only profile stores by
the authenticated principal’s `agent_ids`, so the Shield, AGY, Claude, and
Quant stores are omitted before the UI selector is built. UserAPI ownership
rows do not automatically update Cortex account authorization. Correcting
this requires an explicit Cortex account/authorization mutation; it was not
performed because Gate 5 requirement 7 prohibits identity/database mutation.

Authorized identity-binding repair on 2026-09-26: after explicit operator
authorization, the supported Cortex service-layer function
`set_account_agent_ids` updated Jacob’s active Cortex account
`395a2ffd-d8ad-48b0-9032-935afbc4b0c0`. It preserved the existing root DID,
pseudonym, and `xibalba.agent`, and added the Shield, AGY, Claude, and Quant
DIDs plus local `codex`. No graph-memory database, event, identity key, or
WAL was changed. The current browser session token predates this binding and
must be renewed by signing out and back in before selector/API verification.

Post-renewal Cortex verification on 2026-09-26: the authenticated selector now
exposes the mounted namespace set, including
`xibalba-shield · xibalba-cortex-shield · read only`,
`xibalba-quant · xibalba-cortex-quant · read only`,
`codex · xibalba-cortex-codex · read only`,
`claude · xibalba-cortex-claude · read only`, and
`agy · xibalba-cortex-agy · read only`, alongside the default writable
workspaces. Selecting the Shield read-only option rendered profile
`xibalba-cortex-shield`, exact Shield DID
`did:integrity:2ea17967f7a65589d570ca7e800844701fb36e6aa7374243e8766de8651f6bc4`,
and read-only controls. Searching `evt-79568b9aed44` in that scope returned
exactly two observed-event records: the historical target and the separately
identified synthetic equivalent. Searching the root scope previously returned
no match, proving scoped visibility at the current UI/API boundary.

The selector still displays same-label entries in both default and read-only
stores (for example `xibalba-shield`, `codex`, `xibalba-quant`, `agy`, and
`claude`), so the requirement for duplicate-free canonical labels is not yet
proven. The historical target’s detail is now fully readable in Cortex and
shows status `candidate`, evidence class `observed_event`, invocation
`94d4fb7c-3ede-4e13-883a-0712b7447bf7`, device
`xibalba-HP-Desktop-M01-F0xxx`, derived content hash
`sha256:df3ea908ade3b005bcd068adf13e580b71a3ccfe619bd696ae1239bf65c5ebb1`,
and no session, locator, observed timestamp, or Cortex acceptance receipt.
The hash is a Cortex memory content hash, not an explicit signed hash on the
historical Shield event.

Repository-state note: `xibalba-cortex` remained clean. `xibalba-shield` has
the tracked Caddy-alignment scripts and future-delivery hash/receipt validation
changes described above. `integrity-core` is dirty because this matrix entry
was added during the validation/remediation handoff.

## Reproduction constraints

- Do not disable the installed Shield limits. The current provider has been
  installed into `/opt/xibalba-shield` and independently verified with
  `xibalba-shield/scripts/verify_live_cortex_outbox_limits.sh`; repeat the
  updater and verifier after any future package change.
- Do not unlock or regenerate identity material during validation.
- Do not run broad retrieval, compaction, or deletion against the live graph
  database.
- Do not use standalone browser automation as a substitute for the unavailable
  in-app Browser without explicit operator approval.
