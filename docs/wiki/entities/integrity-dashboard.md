---
title: integrity-dashboard
created: 2026-07-07
updated: 2026-07-25
type: entity
tags: [infrastructure, sdk]
confidence: medium
source_files:
  - integrity-dashboard/src/App.tsx
  - integrity-dashboard/src/config.ts
  - integrity-dashboard/src/chain/bytecode.ts
  - integrity-dashboard/src/components/ui/RegisterAgentModal.tsx
  - integrity-dashboard/src/services/oracle.ts
  - integrity-dashboard/src/services/userapi.ts
  - integrity-dashboard/src/components/shared/SeededDataBadge.tsx
  - integrity-dashboard/demo/src/integrity_demo/main.py
  - integrity-dashboard/demo/src/integrity_demo/agent_loop.py
  - integrity-dashboard/demo/src/integrity_demo/userapi_bridge.py
  - integrity-dashboard/scripts/seed_mock_data.py
  - integrity-dashboard/.env.example
  - scripts/sync_abis.py
---

**This page was rewritten from scratch on 2026-07-12.** The version of
`integrity-dashboard` it previously described (a mature app with `AgentListPage`/
`AgentDetailPage`/`MarketsPage`/`LeaderboardPage`/`WalletPage`/
`CapitalAllocationPage`, real JWT auth, a Demo/Live data-mode toggle backed
by MSW fixtures, `demo/` as a real Python scenario engine, 129 vitest +
16 Playwright specs) **no longer exists on disk.** `integrity-dashboard/src/`
was independently rewritten into a new 16-page shell (all file mtimes
~2026-07-12 00:00-00:20, well after this page's prior "2026-07-11" content)
by a process outside this wiki's tracking, confirmed by the user as
intentional ("the new dashboard ui") rather than accidental data loss. None of
the file paths this page previously cited under `source_files` exist
anymore. Per this wiki's own "no aspirational content" rule, the old
content has been replaced rather than patched — it described a build that
is simply gone. If you need it for historical reference, it's recoverable
from this file's prior version in your editor's/tool's history, not from
anything in the current tree.

## Page consolidation (2026-07-16) — route count and names below are stale

`App.tsx` now defines **11** routes, not 16: `/`, `/landing`, `/identity`,
`/contracts`, `/settings`, `/finance`, `/traces`, `/diagnostics`, `/shield`,
`/agents`, `/documents`. Six pages named throughout the rest of this
document no longer exist under those names — `AuditPage`,
`ChainOfThoughtPage`, `CompareTracesPage`, `ExchangePage`,
`IntelligencePage`, `SdkTelemetryPage` were deleted and consolidated into
two new pages:
- **`TraceAnalyticsPage.tsx`** (`/traces`) — merges `ChainOfThoughtPage`'s
  Historical Traces DAG view and `CompareTracesPage`'s Gantt/compare view
  into one tabbed page (Live Stream, Historical Traces, Metrics,
  Time-Travel Debugger, Compare Traces). Metrics/Time-Travel Debugger are
  honestly `SeededDataBadge`-marked — no backend endpoint exists for either.
- **`SystemDiagnosticsPage.tsx`** (`/diagnostics`) — merges
  `SdkTelemetryPage`'s real oracle telemetry/OTLP-volume view and
  `AuditPage`'s disclosed-simulated audit-log feed into one tabbed page
  (SDK Telemetry, Audit Logs).

`IntelligencePage`'s real radar-widget work (below) now lives on the
Dashboard (`/`) directly. `ExchangePage`'s real wagmi market-entry flow
was folded into `FinancePage`'s "A2A Markets & Escrow" tab
(`src/components/finance/MarketsEscrowPanel.tsx`).

Re-verified for real after the consolidation, not just by reading code:
brought up a full local anvil + `docker-compose` stack, generated a real
3-span nested OTel trace via the SDK's `traceable()` API against the live
oracle, and confirmed `TraceAnalyticsPage` renders it as a real DAG with
real span attributes over the live SSE stream, and `SystemDiagnosticsPage`'s
telemetry volume chart reflects the same real data — the demo→oracle→
frontend pipeline described in §10 of `PRODUCTION_GAPS.md` survived the
rename intact. Also found and fixed one real bug this pass:
`FinancePage.tsx`'s live ITK balance was off by 10^18 (missing
`formatUnits(..., 18)` on the raw wei-scale `itk_balance` string from
`GET /v1/agent/{id}/wallet`), rendering a nonsense multi-quintillion-dollar
portfolio value — see `PRODUCTION_GAPS.md` §7 for the full writeup.

## What actually exists now (as of 2026-07-12, this session's work — page
names below predate the 2026-07-16 consolidation above)

React 19 + Vite + TypeScript, 16 routed pages (`src/App.tsx`). The
rewritten shell shipped cosmetically complete but has now been fully resolved
with real backend/chain wiring and a Notion-style drag-and-drop widget layout engine.

1. **Notion-style block & widget dashboard.** `DashboardPage.tsx` is a
   drag-and-drop grid (`react-grid-layout`). Toggle "Edit Layout" to drag
   widgets by their grab handle and resize them.
   - `WidgetRegistry.tsx` maps widget types (`gauge`, `throughput`,
     `latency`, `nodes`, `events`, `radar`, `notes`) to real components.
   - `WidgetWrapper.tsx` provides the common panel chrome — drag handle,
     delete/duplicate menu.
   - Layout and widget list persist to `localStorage`, with a "Reset"
     button to restore the defaults.
2. **The build was broken; it isn't anymore.** A missing `return`, two
   imports pointing at nothing, and unused-variable lint errors were
   blocking `npm run build`/`npm run lint`. Fixed, plus two shared
   components (`src/shared/{Panel,StatusBadge}.tsx`) that were imported
   but never written. Verified via Playwright: all 16 routes render with
   zero console errors.
3. **Wallet/data infrastructure.** `wagmi` + `viem` +
   `@tanstack/react-query` power a real `ConnectWalletButton` (injected
   wallets only, no RainbowKit). `src/services/oracle.ts`/`userapi.ts` are
   typed `fetch` clients checked field-for-field against
   `spec/ais-api/v1/openapi.yaml`. Every agent-attributable on-chain write
   goes through one shared helper, `useSovereignAgentWrite`, which wraps
   `SovereignAgent.execute(target, 0, calldata)` — the same pattern
   `integrity_sdk/markets.py`'s `_execute_via_agent` uses. `scripts/
   sync_abis.py` now also emits trimmed ABIs into `src/abis/` and copies
   `deployments.*.json` into `src/deployments/`.
4. **Real reads, verified against a live stack** (real anvil + real
   `cargo run` oracle-backend + real registered test agents — not assumed
   from response shape alone):
   - `AgentContext` — was 3 hardcoded fake agents, now `oracle.listAgents()`
   - `AgentsPage` — real DID/tier/AIS/created_at
   - `IntelligencePage` — real leaderboard via `oracle.getLeaderboard()`
   - `IdentityPage` — real DID + ITK balance/open-positions via `oracle.getWallet()`
   - `ExchangePage` — real `oracle.listMarkets()` for the Active Markets list
   - `FinancePage` — real ITK balance, transaction history, and allowances
   - `DashboardPage` — real AIS distribution + high-integrity %, live-updated over SSE

   Confirmed end-to-end via Playwright: a real agent DID registered
   through `integrity-cli` appears verbatim in the rendered page, sourced
   from a captured real network response — not just "the build compiles."
5. **Honest labeling for what's still simulated.** A new
   `src/shared/SeededDataBadge.tsx` marks every page with no real backing
   yet: `ChainOfThoughtPage`, `SdkTelemetryPage`, `CognitionPage`,
   `CompareTracesPage`, `DocumentsPage`, `ShieldPage`, most of
   `ContractsPage` (the compile/deploy flow is a labeled sandbox, not a
   real compiler), parts of `ExchangePage` (the order-book UI —
   `IntegrityMarket` is a pari-mutuel pool, so there's no honest order
   book to show), `FinancePage`'s treasury stats, `ActuarialHub`, parts of
   `DashboardPage`'s widget grid, and several `SettingsPage` panels.
6. **Mock-data seeding, done right.** `scripts/seed_mock_data.py`
   registers real test agents (and one real market) through
   `integrity_sdk`, the same way a real agent would register — not a
   "write fake rows into Postgres" script. Gated by `MOCK=true`. Runs
   outside the browser, since it needs the funder's private key.
   `VITE_MOCK_MODE` is read-only in the UI — it just reports whether the
   build is pointed at a seeded stack; it can't seed anything itself.
7. **Wallet-interactive writes, for real (2026-07-12).**
   - `ExchangePage`'s "Place Order" does a real two-transaction
     `approve` + `enterPosition` flow, gated on the connected wallet
     matching the agent's on-chain controller.
   - `ShieldPage`'s Smart BAA registry reads real `SmartBAAFactory
     .BAACreated` event logs and wires real `sign()`/`revoke()` writes.
   - `ClaimAgentModal` was rewritten, not patched: the old "claim via
     signature challenge" premise had no on-chain support at all — it
     submitted a transaction using ERC-20 `approve`'s selector as if it
     were a claim call, silently swallowing the failure. The new "Verify
     Agent Control" modal does something real: resolves the on-chain
     controller, compares it to the connected wallet, and has the user
     `personal_sign` a "prove you hold this key" confirmation.

   All three write paths verified against real anvil + oracle: a real
   `enterPosition` transaction moved a market's `outcome_staked` from 0 to
   a real non-zero value.
8. **userapi auth, tests, and docs (2026-07-12).** `SettingsPage`'s
   login/register/API-key management verified end-to-end via Playwright
   against a real running `integrity-userapi` + isolated Postgres. New
   test infrastructure: 9 vitest unit tests (client request shapes, hook
   logic, context behavior) and 18 Playwright e2e tests (all 16 routes,
   zero console errors, a real-network-response assertion), both run
   against a real backend+chain. `README.md` rewritten from the default
   Vite scaffold into real project docs.
9. **UI validation and agent selection (2026-07-14).** Fixed strict
   TypeScript errors in `DashboardPage.tsx`/`FinancePage.tsx` that were
   blocking `npm run build`. Propagated `selectedAgentId` from
   `AgentContext` into `DashboardPage`/`ChainOfThoughtPage`, so the SSE
   hooks correctly filter live OTLP/AIS data to the active agent.
10. **UI layout and legacy aesthetic integration (2026-07-15).**
    - `AgentsPage`: Extracted the `ClaimAgentModal` and `AgentOnboarding` workflows from isolated modals into prominent inline dashboard cards above the agents grid, significantly improving discoverability of the onboarding pipeline.
    - `IdentityPage`: Fundamentally refactored to replicate the core layout and aesthetics of the legacy `integrity-dashboard` codebase. Replaced giant glassmorphism panels with a compact Agent Status Strip (DID, AIS, Tier, TEE), a dedicated Hero Bar, and a sub-navigation tab interface sorting components into `Identity & DID`, `Enclave & Security`, `Economic Capacity`, and `Credentials`. 
    - `XNS`: Fully wired the `XNSSearchService` into the Identity page's UI layout.
    - `ContractsPage`: Expanded the IDE workstation with full features: multi-tab editor for files, interactive build/deploy panel, and a dynamic "Deployed Contracts" inspector that generates interactive ABI buttons via source code regex analysis.
11. **On-chain primitives deployment and XNS registration (2026-07-18).**
    - Decompiled and bundled compiled Foundry bytecodes for `SovereignAgent` and `StateAnchor` into `bytecode.ts`.
    - Built the `RegisterAgentModal` step-by-step deployment wizard, implementing real, mock-free transactions to deploy core contracts, authorize the oracle signer via SovereignAgent proxy execution, deploy proxy clones via the `AgentPrimitivesFactory`, and sync indexing with the Oracle database.
    - Upgraded the `IdentityPage` to support real on-chain reads for active primitive addresses, status indicators, and audit logging feeds.
    - Fully integrated write routing using `SovereignAgent.execute` to delegate `register` calls to the `XibalbaNameService` contract.
    - Re-implemented `XNSSearchService` to perform real read-only contract resolutions mapping handles to identities on-chain.
    - Consolidated DID, XNS management, claim/registration actions, history logs, security credentials, and the 7 primitive contracts onto a single tabless page layout, displaying the primitives in a structured status table.

## Prereq wiring: benchmarks, VCs, custodial wallet, XNS, governance (2026-07-25)

Five backend prereqs were built + wired into the dashboard, each with an honest
degradation path (never a mock):
- **SDK benchmarks** — `oracle.getBenchmarks()` (`GET /v1/benchmarks`) drives the
  model/provider stability panels from real network-wide telemetry aggregates.
- **Verifiable Credentials** — `DIDExplorer` now shows a real Ed25519-signed W3C
  `AgentIntegrityCredential` via `oracle.getAgentVc()` (`GET /v1/agent/{id}/vc`),
  alongside the real DID document.
- **Custodial app-wallet** — `TokenWallet` shows both the real on-chain balance/history
  and the userapi custodial $ITK ledger (`userapi.getWallet()`/`walletTransfer()` — see
  [integrity-userapi](integrity-userapi.md)); verified live (faucet 10000 → 9750 after a
  250 transfer).
- **XNS** — `XNSSearchService` resolves human handles on-chain via `oracle.resolveXns()`
  (falling back to direct `did:`/`0x` lookups), and `DIDExplorer`'s `XNS_RESOLVE` field
  reflects the real primary handle via `oracle.getAgentHandle()`. The register-handle
  *write* flow is deliberately deferred (CLI/SDK).
- **Governance** — `GovernancePanel` + `GuardianPilot` render live `IntegrityGovernance`
  proposals via `oracle.getGovernanceProposals()` (`GET /v1/governance/proposals`). Both
  degrade to their honest "Not Yet Live" state on the `MissingSingleton` (HTTP 400) the
  endpoint returns until the contract is deployed — **never a live-but-empty list**. The
  propose/vote *write* flow is deliberately deferred (CLI/SDK); an inline note says so.
  See [Governance](../concepts/governance.md).

The `MissingSingleton`→**400** contract was verified empirically against the live oracle
(both XNS + governance endpoints returned 400 with a descriptive body; control route
`/v1/agents` still 200). All frontend degradation branches key on that. Full build (tsc +
vite) + 198 forge tests green.

## `TriMetricWidget` fixed 2026-07-15 — was the most severe fake-data surface in the dashboard

The dashboard's "Tri-Metric Risk Analysis" panel badged itself "LIVE MODEL"
while every number was fake: `avgAis` picked from 3 hardcoded magic
constants, `blockedRate`/`riskExposure` literal strings with no
computation, all 3 sparklines fabricated trend arrays — unlike every
sibling in `WidgetRegistry.tsx`, which either fetched real data or
disclosed via `SeededDataBadge`. Two of the three metrics are now real:
**AIS Deficit** and **BCC Intent Violation Rate** fan out `oracle.getAis()`
across every agent in the global `AgentContext` (same pattern the `gauge`
widget already used) and average real `ais`/`components.compliance`. The
third ("Smart BAA Value at Risk") stays honestly marked unavailable — no
probability-of-leak model or network-wide staked-collateral index exists
anywhere in this protocol (same conclusion independently reached for
`ActuarialHub`, below). Two real runtime bugs were only caught by actually
loading the dashboard against the live stack, not by `tsc`/`lint`/`build`:
a KaTeX-remount render-storm that froze the browser tab (the 3 formula
sub-components were redefined as new component types on every render —
fixed by hoisting them to module scope) and a grid-height clipping bug
once real content replaced the old sparkline decoration (`DEFAULT_LAYOUTS`
bumped `h: 2` → `h: 3`). Re-verified via live screenshots against a real
registered agent, not just a passing test suite.

## What is NOT done yet

- `integrity-dashboard/demo/` (the Python scenario-engine directory `make demo`
  references) **now exists on disk** (as of 2026-07-15), **and `make demo`
  itself now works** (as of 2026-07-16 — it was documented in three places
  but had no actual Makefile target until this pass). It's a real scenario
  engine (`integrity_demo` package) that registers 4 persona agents and
  exercises a capital-allocation tool-call loop against a live chain; as of
  2026-07-15 it also has an opt-in completion-callback bridge into
  `integrity-userapi`'s `demo_runs` table (`userapi_bridge.py` — see
  [integrity-userapi](integrity-userapi.md)). **Actually running it
  end-to-end against a real local chain + real oracle (2026-07-16) found
  and fixed several real bugs no amount of code reading had caught**: every OTel
  span it ever exported was silently rejected by the oracle (missing
  `integrity.agent.id`, plus a structural one-shot-global-tracer issue
  given this engine manages 4 different agent identities in one process —
  fixed with real per-agent tracers, verified by querying the oracle's
  `otel_spans` table directly post-run); one LLM call failure used to crash
  the whole process with a raw traceback (now degrades gracefully, matching
  the registration loop's existing per-agent error handling); and there was
  no preflight check that the funder wallet (real Base Sepolia balance:
  ~0.001 ETH, 10x under one agent's default funding) could actually afford
  the run before spending gas on a doomed one.
  
  Additionally, during integration testing on 2026-07-16, we found and fixed two other crucial issues:
  - Added support for Google Gemini OpenAI compatibility in `agent_loop.py` to allow execution using `GEMINI_API_KEY` (using `gemini-2.5-flash` via the OpenAI client compatibility layer).
  - Integrated the SDK's `NonceStore` in the capital allocation tool call flow rather than a hardcoded `nonce=1`, preventing `BCC_NONCE_REPLAY` rejections in sequential runs.
  
  The full closed-loop data path has now been verified successfully locally: agent registration -> oracle registration -> OTel trace ingestion -> reputation sync -> BCC intercept gate authorization -> on-chain capital allocation. Full writeup: `PRODUCTION_GAPS.md` §9. Still genuinely missing: no
  UI trigger anywhere in this dashboard creates a `demo_runs` row or
  launches this CLI process — it remains an operator-run script against
  live Base Sepolia using a funder private key.
- `ExchangePage`'s order-book/candlestick UI and `DashboardPage`'s
  latency/node-fleet/security-event widgets remain honestly seeded
  (`SeededDataBadge`) — no on-chain order book exists for a pari-mutuel
  market, and no WSS/OTLP telemetry-streaming infra exists yet (see root
  `PRODUCTION_GAPS.md`). **`throughput` is no longer in this list** — it
  was wired to real `oracle.getTelemetryVolume`/`getOtelVolume` data
  earlier this session; the claim that it was still seeded was stale.
- `ShieldPage`'s "Propose BAA Contract" (creating a new BAA) is a disabled
  stub — it requires acting as the covered-entity persona, which this
  dashboard's single-connected-wallet model doesn't represent.
- Bundle size: a single ~1.9MB JS chunk (KaTeX, Monaco, and the full wagmi/
  viem/@wagmi/core surface all ship in the main bundle) — noted by Vite's
  own build warning, not yet addressed with code-splitting.
- **Architectural Gaps for Complete Data**: The Dashboard's Hero Metrics (throughput/latency) require an OTel metrics sink in `integrity-oracle` to aggregate tracing data. Security event alerts (blocked interactions) need event-sourcing in the Oracle to capture `bcc_middleware` policy evaluations. Transaction history requires retroactive USD pricing via an external price feed integration in the Oracle.

Related: [integrity-oracle](integrity-oracle.md),
[integrity-userapi](integrity-userapi.md) (the `demo/` scenario engine's
completion-callback bridge target),
[AIS API spec](../concepts/ais-api-spec.md) (the field-shape source of
truth `oracle.ts` was verified against), [Agent Primitives](../concepts/agent-primitives.md)
(the `SovereignAgent.execute` write convention).
