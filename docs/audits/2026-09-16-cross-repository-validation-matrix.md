# Cross-repository validation matrix — 2026-09-16

This matrix is the current production/live validation boundary for
`integrity-core`, `xibalba-cortex`, and `xibalba-shield`. A passing local test is
reported as test evidence only; it is not promoted to deployment, tenant, or
on-chain evidence.

## Executed checks

| Boundary | Command or probe | Result | Evidence class |
|---|---|---:|---|
| SDK hook contract | `uv run pytest -q tests/unit/test_harness_hooks.py tests/unit/test_cross_system_adapters.py tests/unit/test_readiness.py` | 13 passed | SDK test-confirmed |
| Cortex runtime adapters | `uv run pytest -q tests/test_runtime_adapters.py tests/test_runtime_bridge_contract.py tests/test_agy_hook_bridge.py tests/test_hermes_bridge.py tests/test_hermes_observer.py tests/test_telemetry_outbox.py` | 65 passed | Cortex test-confirmed |
| Claude/Codex SDK normalization | `uv run pytest -q tests/test_runtime_adapters.py` | 25 passed; `xibalba-cortex` `498e67f` | adapter test-confirmed; live native hook delivery not claimed |
| Shield binding/redaction/outbox | `./.venv/bin/pytest -q tests/test_agent_binding_and_redaction.py tests/test_e2e_validate.py` | 11 passed; includes worker count-skip regression from `xibalba-shield` `bcfaa9f` | Shield test-confirmed |
| Shield live containment | `scripts/validate_local_containment.sh` | `CONFIRMED_SIGSTOP` | privileged live-device evidence |
| Shield device correlation | one device-authenticated `POST /api/shield/exporter-status` with bounded live-status payload | HTTP 200 `{"ok":true}` | live device credential and backend acceptance; admin readback token reconciliation remains open |
| Shield live cgroup limits | `verify_live_cortex_outbox_limits.sh` plus `systemctl show` | installed and active; provider caps and aggregate-count bypass verified live; 256 MiB RAM/swap, 25% CPU, 64 tasks, 1024 FDs | live host evidence |
| Cortex fast liveness | authenticated `GET /api/status` on `127.0.0.1:8420` | 200; WAL, FTS5, backup ready; exact count deferred | live local service evidence |
| Integrity directory | `GET /v1/agents/snapshot` on `127.0.0.1:8080` | finalized Base Sepolia snapshot, chain 84532, five agents | live Oracle evidence |
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
| New harness registrations | finalized registry records and accepted transaction receipts for Claude, Codex, Agy | not attempted; wallet/control authorization absent |
| Full matrix | repeated performance, failure, recovery, and cross-repository canaries | partial; rows above are the safe current baseline |

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
