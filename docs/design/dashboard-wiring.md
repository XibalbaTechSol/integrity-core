# integrity-dashboard — Wiring Plan (make every widget real, no mocks)

Copying the legacy `integrity-dashboard` UI into INTEGRITY-LATEST (as a **parallel** app
alongside `integrity-mvp`) and wiring every widget to the **real** backend. Where the new oracle
has no matching data source, the decision is to **build the real endpoint / on-chain call** —
not to badge a gap. "Keep all visuals the same."

**Stage 1 (foundation) ✅ done:** legacy tree copied to `integrity-dashboard/`, ~700 cruft files
pruned, `predev/prebuild` wiki-sync hooks removed, `npm install` + `npm run build` green (2972
modules, all 7 pages), visuals intact on the legacy data layer.

## Data-layer strategy

Do **not** hand-rewrite the legacy axios `src/services/api.ts` endpoint-by-endpoint. Port the
UI onto `integrity-mvp`'s already-correct real clients — `integrity-mvp/src/services/oracle.ts`
(DID-keyed routes, SSE, audit-log) and `userapi.ts` (JWT auth in sessionStorage) — as the single
source of truth. Replace the legacy `firebase` auth dependency with `userapi`. On-chain writes go
through `wagmi`/`viem` against `deployments.baseSepolia.json`, mirroring how the protocol's
clone-per-agent model resolves addresses live from `XibalbaAgentRegistry`.

## Endpoint inventory → classification

Legacy calls (`src/services/api.ts`) classified by how they become real. Config: legacy reads
`VITE_API_BASE`; new clients read `VITE_ORACLE_URL` (:8080) + `VITE_USERAPI_URL` (:8090).

### Class A — maps to a real oracle endpoint TODAY (just wire it)
| Legacy call | New real source (`oracle.ts`) |
|---|---|
| `GET /agents` | `GET /v1/agents` (`listAgents`) |
| `POST /agent/register` | `POST /v1/agent/register` (`register`) |
| `GET /agent/{a}/metadata` | `GET /v1/agent/{id}` (`getAgent`) — DID-keyed |
| `GET /agent/{a}/reputation/history` | `GET /v1/agent/{id}/ais/history` |
| agent AIS / compliance / wallet | `getAis` / `getCompliance` / `getWallet` |
| `GET /market/tasks` | `GET /v1/markets` (`listMarkets`) + `getMarket` |
| `GET /metrics/stream` (SSE) | `GET /v1/stream` (`streamUrl`) |
| `GET /contracts/telemetry/stream` (SSE) | `GET /v1/agent/{id}/stream` |
| leaderboard, telemetry, traces, audit-log | `getLeaderboard` / `getTelemetry` / `getTraces` / `getAuditLog` |

### Class B — build a new oracle READ endpoint (oracle already reads chain+DB; aggregate it)
| Legacy call | New endpoint to build | Backing data |
|---|---|---|
| `GET /stats` (protocol stats) | `GET /v1/stats` | agent count, total stake, decision counts (agents + audit_log) |
| `GET /contracts/deployed`, `/contracts/ledger` | `GET /v1/agent/{id}/contracts` | resolve PrimitiveSet via `XibalbaAgentRegistry.resolveDID` |
| `GET /agent/{a}/stake` | `GET /v1/agent/{id}/stake` | on-chain `ReputationRegistry`/`Slasher` read (alloy) |
| `GET /agent/{a}/credit/profile` | `GET /v1/agent/{id}/credit` | on-chain `A2ACapitalPool` read |
| `GET /agent/{a}/provenance` | `GET /v1/agent/{id}/provenance` | **reuse `anchor_events` + `audit_log`** (evidence Phase A) — natural synergy |

### Class C — on-chain WRITE via wagmi/viem (not an oracle endpoint; a wallet tx)
`POST /agent/{a}/identity/claim` + `/challenge` (SovereignAgent/DID) · `/credit/borrow` + `/repay`
(A2ACapitalPool) · `/market/task/{create,bid,fund-with-loan,settle}` (IntegrityMarket) ·
`/contracts/factory/deploy` (AgentPrimitivesFactory `registerPrimitives`) ·
`/governance/proposals/{id}/vote` (governance — **no contract exists yet**; on-chain gap, needs a
contract first). These need `ConnectWalletButton` + signed txs against `deployments.baseSepolia.json`.

### Class D — client-side (SDK/browser), not backend
`POST /agent/{a}/zk/generate-proof` — real Noir/Barretenberg proving happens agent-side
(`integrity-sdk`/`integrity-zkp`), not via the oracle. Dashboard triggers, does not compute.

## Execution stages (each a focused, verifiable slice)
1. **Foundation** ✅ — copy, prune, build green (done).
2. **Data-layer port** ✅ — `oracle.ts`/`userapi.ts`/`config.ts` ported in, `.env` added.
   (Auth is still on firebase — swap to userapi tracked under Class C.)
3. **Class A pages** 🔨 in progress:
   - ✅ `DashboardProvider` — real agents (`listAgents`), per-agent AIS (`getAis`) mapped to the
     legacy `Agent` shape, protocol stats derived from the live set. Feeds every `useDashboard()`
     consumer (Intelligence radar, agent selector, stat tiles).
   - ✅ `CompliancePanel` — real `getCompliance` status + real audit trail (`getAuditLog`,
     including `shadow_deny` would-be-blocks) replacing the hardcoded event list.
   - ✅ `APIKeyPanel` — real `userapi` key CRUD (`listApiKeys`/`createApiKey`/`revokeApiKey`),
     adapted to the real id-keyed / `raw_key`-once / `ais_trust_ceiling` shape.
   - ⬜ remaining panels reading real data: ActuarialHub (`listMarkets`), Diagnostics/OTel,
     ImmutableLedger (audit-log/anchor), Telemetry/Trace panels (`getTelemetry`/`getTraces`).
4. **Class B endpoints** — build `/v1/stats`, `/contracts`, `/stake`, `/credit`, `/provenance`
   in `integrity-oracle` (read-only, alloy), then wire their widgets.
5. **Class C on-chain writes** — wagmi/viem tx wiring for register/identity/market/credit.
   (Governance blocked on a contract that doesn't exist — flag, don't fake.)
6. **Landing page** — update all copy/stats to the real protocol (Base Sepolia addresses, real
   AIS formula, live agent count via `/v1/stats`).
7. **Prove live** — `make up`, drive every page against the real stack; wiring is only real once
   observed rendering oracle/userapi data.

## Honest constraints
- **Governance** has no on-chain contract in `contracts/` — its widgets can't be "made real"
  without first building the contract. Flag as the one true gap, not silently mocked.
- **ZK proof generation** is agent-side by design; the dashboard requests/visualizes, and cannot
  itself produce a real proof without the SDK toolchain in-browser.
