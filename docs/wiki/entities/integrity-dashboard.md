---
title: integrity-dashboard
created: 2026-07-07
updated: 2026-09-01
type: entity
tags: [infrastructure, sdk]
confidence: high
source_files:
  - integrity-dashboard/src/App.tsx
  - integrity-dashboard/src/Dashboard.tsx
  - integrity-dashboard/src/pages/AuthPage.tsx
  - integrity-dashboard/src/pages/SettingsPage.tsx
  - integrity-dashboard/src/pages/IdentityPage.tsx
  - integrity-dashboard/src/pages/IntelligencePage.tsx
  - integrity-dashboard/src/pages/HealthPage.tsx
  - integrity-dashboard/src/pages/ShieldPage.tsx
  - integrity-dashboard/src/components/shield/ShieldFleetOverview.tsx
  - integrity-dashboard/src/services/shieldBackend.ts
  - integrity-dashboard/src/pages/FinancialsPage.tsx
  - integrity-dashboard/src/pages/CortexPage.tsx
  - integrity-dashboard/src/components/cortex/CortexOperationsTab.tsx
  - integrity-dashboard/src/pages/DeveloperPage.tsx
  - integrity-dashboard/src/pages/WikiPage.tsx
  - integrity-dashboard/src/context/DashboardContext.tsx
  - integrity-dashboard/src/context/SettingsContext.tsx
  - integrity-dashboard/src/services/oracle.ts
  - integrity-dashboard/src/services/userapi.ts
  - integrity-dashboard/src/services/graphMemory.ts
  - integrity-dashboard/src/types/graphMemory.ts
  - integrity-dashboard/src/components/ui/DIDExplorer.tsx
  - integrity-dashboard/src/components/tabs/ActuarialHub.tsx
  - integrity-dashboard/src/components/observability/TraceAnalysisPanel.tsx
  - integrity-dashboard/playwright.config.ts
  - integrity-dashboard/e2e
  - integrity-dashboard/Dockerfile
  - integrity-dashboard/.dockerignore
  - integrity-userapi/app/config.py
  - docker-compose.yml
---

**This page was rewritten on 2026-08-13.** The prior content described an
older, structurally different dashboard (`AgentListPage`, `MarketsPage`,
`WalletPage`, `wagmi`/`viem`, a Notion-style `react-grid-layout` widget
dashboard) that no longer exists on disk — it predates the 2026-08-12
"Reconcile integrity-dashboard with integrity-mvp's current state" commit,
which replaced the tracked snapshot with `integrity-mvp`'s current,
independently-developed state. None of the file paths the old version of
this page cited exist anymore. Per this wiki's "no aspirational content"
rule, the old content is replaced rather than patched.

## Table of contents

- [What this is](#what-this-is)
- [Container packaging](#container-packaging)
- [Routes](#routes)
- [Cortex Operations tab boundary](#cortex-operations-tab-boundary)
- [2026-08-13 full-site Playwright audit](#2026-08-13-full-site-playwright-audit)
- [Real bugs found and fixed this pass](#real-bugs-found-and-fixed-this-pass)
- [Known gaps not fixed this pass](#known-gaps-not-fixed-this-pass)
- [Local e2e stack](#local-e2e-stack)

## What this is

The lint toolchain declares the `globals` package explicitly in
`devDependencies`; this keeps the flat ESLint configuration reproducible in
Continuous Integration (CI) and after a clean `npm ci`.

React 18 + TypeScript + Vite 8 dashboard, `react-router-dom` v7. 22 routes
(`src/App.tsx`), no route-level auth guard — `MainAppLayout`/`PublicLayout`
render `<Outlet/>` unconditionally, and individual pages read auth state
(`getToken()` in `services/userapi.ts`, a JWT in `sessionStorage`) ad hoc.
Most pages are driven by `DashboardContext`'s `selectedAgent` (populated
from a real `oracle.listAgents()` call, no mock filter) and read real data
from three backends: `integrity-oracle` (`services/oracle.ts`),
`integrity-userapi` (`services/userapi.ts`), and, for a few chain-reading
components (`StakingPanel`, `CreditPanel`, `PrivacyPanel`, `TokenWallet`,
`ActuarialHub`, `HealthPage`), direct `ethers.JsonRpcProvider` reads against
addresses hardcoded from the committed `src/deployments.baseSepolia.json` —
**those chain reads always target real Base Sepolia**, never whatever
`RPC_URL` the oracle backend itself is configured with, so an agent
registered only on a local anvil chain (as in local e2e testing) shows real,
honest empty states on those specific panels even though oracle-backed
panels for the same agent show real data. `HealthPage`'s own banner states
this explicitly: "Smart BAA registry, EHR Gates, and Quarantine are all real
(Base Sepolia)."

## Container packaging

The Compose `dashboard` service builds from `integrity-dashboard/` using
`node:22-alpine`. Its Dockerfile installs the exact committed dependency graph with
`npm ci`, then runs the Vite development server on `0.0.0.0`. The build context excludes
host `node_modules`, demo `.venv`/Python caches, `dist`, Playwright/test output, local
environment files, caches, and repository metadata through `.dockerignore`; host dependencies
therefore cannot overwrite the clean in-image install during `COPY . .`.

On 2026-09-01, a cold `docker compose build --no-cache dashboard` completed with a
4.88 MB context and installed 451 packages with 0 reported vulnerabilities. A baseline
build from a checkout without `.dockerignore` had sent 717.42 MB when host dependencies
were present. A container launched from the rebuilt image reached Vite readiness in 713 ms and
served the real application shell over HTTP before it was removed. This is local build/runtime
evidence, not evidence that a persistent or remote dashboard deployment was replaced.

## Routes

| Route | Page component | Backend dependency |
|---|---|---|
| `/` | `LandingPage.tsx` | none — static |
| `/auth` | `pages/AuthPage.tsx` | `userapi` (login/register), `DashboardContext.connectWallet` |
| `/wiki` | `pages/WikiPage.tsx` (lazy) | none — reads build-time `src/generated/wiki-data.json` |
| `/docs`, `/privacy`, `/terms` | `pages/{Docs,Privacy,Terms}Page.tsx` | none — static, under `PublicLayout` |
| `/dashboard` | `Dashboard.tsx` | `oracle` (AIS, stake, history, telemetry, audit log, traces) |
| `/identity` | `pages/IdentityPage.tsx` | `DashboardContext` only, no direct fetches |
| `/financials` | `pages/FinancialsPage.tsx` | `oracle` + chain (`TokenWallet`, `StakingPanel`, `CreditPanel`, `ActuarialHub`) |
| `/intelligence` | `pages/IntelligencePage.tsx` | `DashboardContext`; custom telemetry fields are `localStorage`-only |
| `/prediction-markets` | `components/tabs/ActuarialHub.tsx` (`mode="markets"`) | `oracle.listMarkets()` + chain writes via `SovereignAgent.execute` |
| `/health` | `pages/HealthPage.tsx` | `oracle` (NHI governance) + chain (BAAs/EHR gates/quarantine, real Base Sepolia) |
| `/shield` | `pages/ShieldPage.tsx` | `ShieldFleetOverview` reads the real Shield backend; `Live Attack Demo` is a separate synthetic/local simulator tab |
| `/cortex` | `pages/CortexPage.tsx` | Unified Cortex workspace: timeline, graph, recall, inference, integrity, and operations tabs backed by `xibalba-cortex`'s `local_api.py`, `VITE_GRAPH_MEMORY_URL`, default `:8420` |
| `/memory` | compatibility redirect | Redirects to the canonical `/cortex` workspace so existing bookmarks remain valid |
| `/developer` | `pages/DeveloperPage.tsx` | `oracle` + chain (IDE/contracts tab), `oracle` (Trace Analysis tab) |
| `/settings` | `pages/SettingsPage.tsx` | `userapi` (API keys), `DashboardContext` (theme/layout), chain (`PrivacyPanel`) |

**`/shield`** renders two explicit surfaces: `ShieldFleetOverview` is the default real-backend evidence view, reading dashboard summaries, detection quality, enforcement outcomes, exporter status, device state, integrations, and the 3D evidence graph through `services/shieldBackend.ts`; the `Live Attack Demo` tab is a separate synthetic/local demonstration of the Tier-2 escalation path. Backend data is not replaced by simulator data when the service is unavailable; the fleet view shows an unavailable or partial state. The local integration overlay exposes the backend on `:8765`, but healthy local responses remain development evidence and do not establish production sensor, Oracle, or live-chain proof.

## Cortex Operations tab boundary

The `/cortex` workspace's **Operations** tab is a focused operator surface over the separate
`xibalba-cortex` local API. It does not move canonical memory ownership into
`integrity-core`: Cortex's profile-scoped SQLite store remains authoritative
for Cortex memory, while Integrity protocol packages remain independent of
that external repository.

The page exposes four implemented groups from `services/graphMemory.ts`:

- evidence-backed hybrid retrieval (`POST /api/retrieval/hybrid`) followed by
  persisted trace readback (`GET /api/retrieval/trace/{id}`), including
  channel state, root hash, result signals, the first result's Merkle inclusion
  proof (`GET /api/retrieval/trace/{id}/evidence?rank=1`), and an optional
  projection checkpoint link;
- proposed extraction review (`GET /api/extraction-proposals`) with explicit
  accept/dismiss decisions (`POST /api/extraction-proposals/{id}/decision`);
- pending inference-task and embedding-model visibility
  (`GET /api/inference/tasks`, `GET /api/embedding/models`); and
- checkpoint list/create, reconciliation, and rebuild for the `memories`,
  `entities`, and `relations` projections under `/api/projections/{id}`.

The surface shows a partial-view warning when any operator API is unavailable
and does not synthesize placeholder records. Retrieval can explicitly report
degraded channels. Extraction acceptance and projection rebuild are real
writes to the configured Cortex service; the dashboard currently supplies
`decided_by: "integrity-dashboard"` but adds no user authentication or
operator authorization of its own. The page therefore disables extraction
decisions and projection mutation outside a loopback-hosted dashboard. This
browser-side guard is defense in depth, not authentication: keep the Cortex
API itself local or behind an authenticated operator boundary before exposing
it beyond a trusted development environment.

The workspace's core loader settles statistics, status, integrity links,
sessions, graph data, and the inference manifest independently. A failure in
an optional capability therefore produces a named partial-data warning without
discarding a successful `/api/sessions` response.

## 2026-08-13 full-site Playwright audit

The 2026-08-13 audit covered 16 routes and 140 tests. The current tree has 19
Playwright specs and 137 test declarations, while `src/App.tsx` defines 22 route
entries including redirects and static/legal pages. The historical audit had a
comprehensive Playwright spec under
`e2e/` (one file per page/route, `landing.spec.ts` through `memory.spec.ts`
— 140 tests total), written and run against a real local backend stack, no
mocking, following each spec with a full-page screenshot reviewed before
moving to the next page. This replaced 5 pre-existing specs
(`dashboard.spec.ts`, `health.spec.ts`, `shield.spec.ts`, `wiki.spec.ts`,
plus `memory.spec.ts`) written under a looser discipline, and added 11 new
ones. `smoke.spec.ts` (all 14 non-wiki/non-memory routes, zero-console-error
only) is kept as a fast pre-existing cross-check.

## Real bugs found and fixed this pass

Each was caught by a Playwright assertion failing against real rendered
output, then fixed in the app (never by loosening the assertion):

- **`WikiPage.tsx`** — `inlineMarkup`'s bold-markdown regex matched
  `\*\*[^*]+\*` (one closing asterisk) instead of `\*\*[^*]+\*\*` (two), so
  `**bold**` rendered as literal asterisks on every one of the 38 wiki
  pages. Fixed the regex.
- **`DIDExplorer.tsx`** — the DID-identifier flex child had no
  `min-width: 0`, so its un-truncated intrinsic text width (despite its own
  `text-overflow: ellipsis`) inflated the parent grid's `1fr 1fr` track
  sizing, squeezing the sibling "Sovereign Node" status-badge column down to
  ~103px and mashing its label/value pairs together unreadably.
- **`integrity-userapi/app/config.py`** — `cors_origins` was missing the
  Playwright dev-server origin (`127.0.0.1:5189`, distinct from
  `localhost:5189` for CORS purposes), blocking every real login/register
  test. Added both forms.
- **`AuthPage.tsx` / `DashboardContext.tsx`** — `handleWalletAuth` navigated
  to `/dashboard` unconditionally after `connectWallet()`, even when
  connection failed (no injected wallet) — `connectWallet` swallowed all
  failures internally and never signaled them to the caller. Changed it to
  return a `boolean`, and gated the navigation on it.
- **`IntelligencePage.tsx`** — `FormulaCard`'s formula box used
  `overflow: hidden` with `justify-content: center`, so a formula wider than
  its box was clipped on **both** edges — `"AIS = (...)"` rendered as the
  unreadable `"[S = (...)"`. `overflow-x: auto` alone wasn't sufficient
  either (a centered flex item inside an auto-overflow container starts
  pre-scrolled to the midpoint); fixed with `justify-content: flex-start`
  plus `overflowX: auto`.
- **`Dashboard.tsx`** — the AIS radar chart mapped `ais.components.*`
  (0–1000 scale, matching `integrity-oracle/scoring-core`'s
  `MAX_COMPONENT_SCORE`) with `* 100`, as if it were a 0–1 fraction —
  producing values like 100,000 against a `fullMark: 100` domain, which made
  Recharts render a literal `"NaN"` tick/label. Changed to `/ 10`.
- **`TraceAnalysisPanel.tsx`** — collapsed "genuinely still loading", "no
  agent selected", and "agent has zero traces" into one
  `selectedSession === null` check, permanently showing `"Loading
  session..."` for the common no-telemetry-yet case — indistinguishable
  from a hang. Added explicit `status` state
  (`'loading' | 'no-agent' | 'no-traces' | 'ready'`) with honest, distinct
  copy per case.
- **`ActuarialHub.tsx`** — `resolve_deadline` is a real ISO 8601 string from
  the oracle (`services/oracle.ts`'s `MarketSummaryDto`, confirmed live:
  `"2026-07-09T19:22:04Z"`), but the Live Markets table parsed it with
  `Number(m.resolve_deadline) * 1000` — `NaN` for an ISO string — rendering
  the literal text `"Invalid Date"` in the Deadline column, and silently
  making the derived `past` flag permanently `false` (a `NaN` comparison is
  always false), which broke the creator-resolve button gate for any market
  actually past its real deadline. Changed to `Date.parse(...)`.

Infra fixes made to enable this testing, not application bugs: the root
`docker-compose.yml`'s `mvp` service references `../integrity-mvp`, which no
longer exists on disk (folded into this directory); worked around by
starting only the specific services needed (`postgres redis opa
oracle-backend bcc-middleware userapi-postgres userapi`) rather than the
full `make up`/`make up-local`.

## Known gaps not fixed this pass

Flagged as findings, left alone per scope (test/bugfix pass, not a feature
or redesign pass):

- **`HealthPage.tsx`** declares a `TABS` array (Smart BAAs / EHR Gates /
  Audit & Compliance / Quarantine) and imports `SubTabs`, but never renders
  `SubTabs` or gates any section behind an active-tab check — every section
  is unconditionally stacked on one continuous page. Dead code, not a
  functional bug (nothing crashes or hides content).
- The Shield fleet surface is locally wired to the real backend client, but production registration, sensor coverage, Oracle readback, and burn-in remain external/runtime evidence gates.

## Local e2e stack

`playwright.config.ts`'s `webServer` boots `npm run dev -- --port 5189`
against whatever `ORACLE_URL`/`USERAPI_URL`/`BCC_MIDDLEWARE_URL` `.env`
resolves to — it does **not** stand up a backend itself (no
`e2e/global-setup.ts` exists in this repo, despite `docs/TESTING.md`
historically describing one; see that page's own update). To run the full
suite against real data:

```bash
make chain                    # local anvil + genesis deploy (deployments.local.json)
docker compose up --build postgres redis opa oracle-backend bcc-middleware userapi-postgres userapi
                               # `docker-compose` (hyphenated binary) is not installed in every
                               # environment; `docker compose` (the plugin) is the portable form
cd integrity-dashboard && npx playwright test
```

For `/cortex`, separately run `xibalba-cortex`'s `local_api.py` (a different
repo): `uv run python -m xibalba_cortex.local_api --home <profile-dir>
--allowed-origin http://127.0.0.1:5189`. Point it at a fresh, empty
`--home` directory for testing rather than a real profile — its own
background session-capture means even a fresh store won't reliably stay at
`0` records, so specs should assert real non-fabricated counts, not a
literal zero.

Related: [integrity-oracle](integrity-oracle.md),
[integrity-userapi](integrity-userapi.md),
[AIS API spec](../concepts/ais-api-spec.md) (the field-shape source of
truth `oracle.ts` is checked against).
