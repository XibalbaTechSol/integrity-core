# Integrity MVP

For the full local Oracle, BCC middleware, and graph-memory workflow, see
[`docs/local-stack.md`](docs/local-stack.md) and run `./scripts/dev-stack.sh`.

Integrity MVP is the React/Vite presentation and operator-workflow layer for the Integrity Protocol product stack. It is not a standalone trust backend. It renders protocol state from INTEGRITY-LATEST, surfaces Xibalba Shield endpoint-security evidence, and publishes the canonical Integrity wiki as a generated read-only browser experience.

## Source-of-truth contract

This README is the repo-level source of truth for what this application is, what it owns, what it consumes, and what is currently built. Deeper product intent lives in [SPECIFICATION.md](SPECIFICATION.md), [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md), and archived historical plans under [docs/archive/2026-08-06](docs/archive/2026-08-06). Protocol schemas, ports, contracts, and backend behavior remain owned by INTEGRITY-LATEST, especially [docs/INTERFACE_CONTRACT.md](https://github.com/XibalbaTechSol/integrity-latest/blob/main/docs/INTERFACE_CONTRACT.md) and the canonical wiki under [INTEGRITY-LATEST/docs/wiki](https://github.com/XibalbaTechSol/integrity-latest/tree/main/docs/wiki).

If this README conflicts with code, fix the README or the code in the same change. Do not document mock behavior as production behavior.

## 2026-08-06 audit status

See [`docs/audits/2026-08-06-status.md`](docs/audits/2026-08-06-status.md), the current [`docs/audits/2026-08-07-gap-closure.md`](docs/audits/2026-08-07-gap-closure.md), and the consolidated cross-repository plan at `/home/xibalba/Documents/INTEGRITY — Cross-Repository Audit and Implementation Plan.md`. The current worktree build, lint gate, and 26-test Playwright suite pass locally. `npm audit` still reports 4 vulnerabilities (1 moderate, 3 high). This repository is a presentation proof of concept, not a standalone production trust backend.

## Ecosystem Role: 👁️ The Human Control Center

This repository is the **conscious observer** in a four-project ecosystem designed as a living organism:

| Repository | Analogy | Role |
|---|---|---|
| `xibalba-graph-memory` | 🧠 The Brain | Local cognitive store — memories, context, reasoning provenance, session Merkle roots |
| `xibalba-shield` | 🛡️ The Immune System | Endpoint enforcement, kernel sensing, policy gating, semantic guardrails |
| `INTEGRITY-LATEST` | 🦴 The Unifying Backend | Protocol backbone — on-chain identity, BCC, Oracle scoring, smart contracts |
| **`integrity-mvp`** | **👁️ The Human Control Center** | Operator dashboard — visualizes health, surfaces evidence, enables human intervention |

**How the Control Center connects:**
- **Inbound (from Backbone):** Reads Oracle APIs for live AIS scores, telemetry, Shield event logs, and audit trails. Reads on-chain state for identity, governance, staking, BAA/compliance, and market data.
- **Inbound (from Brain):** Reads graph-memory local API for memory graph, provenance, session timelines, and integrity verification.
- **Outbound (closes the loop):** Human operators audit agent behavior, update Shield policies, resolve disputes, and direct agent actions — completing the trust cycle.

```mermaid
flowchart LR
    Backbone["🦴 INTEGRITY-LATEST<br/>(Oracle + Chain)"] ==>|"AIS, identity,<br/>governance, evidence"| Eyes["👁️ integrity-mvp<br/>(This repo)"]
    Brain["🧠 xibalba-graph-memory"] -.->|"Memory graph<br/>& provenance"| Eyes
    Immune["🛡️ xibalba-shield"] -->|"Signed telemetry"| Backbone
    Brain -->|"Session Merkle roots"| Backbone
    Eyes ==>|"Operator audits,<br/>policy updates,<br/>interventions"| Agent["🤖 Agent"]
    Agent <-->|"Context & memories"| Brain
    Agent -->|"System calls"| Immune
```

See [`INTEGRITY-LATEST/docs/architecture/ecosystem-dependencies.md`](https://github.com/XibalbaTechSol/integrity-latest/blob/main/docs/architecture/ecosystem-dependencies.md) for the canonical ownership boundaries.

## System relationship

`integrity-mvp` sits at the top of a four-project operator stack:

`integrity-mvp -> xibalba-graph-memory -> INTEGRITY-LATEST`

`integrity-mvp -> xibalba-shield -> INTEGRITY-LATEST`

It also consumes INTEGRITY-LATEST APIs and contracts directly.

| Project | Role | Boundary |
|---|---|---|
| `INTEGRITY-LATEST` | Protocol trust backend: SDK, BCC middleware, Oracle/AIS, user API, contracts, canonical wiki | MVP must not own protocol scoring, anchoring, Merkle conventions, or chain schemas |
| `xibalba-graph-memory` | Local cognitive store: memories, provenance, session roots, graph traversal | MVP may surface memory workflows and evidence; recalled memory remains untrusted content, not protocol truth |
| `xibalba-shield` | Endpoint sensor/enforcer and signed security-evidence producer | MVP may surface Shield workflows and evidence; Shield remains its own repo/product |
| `integrity-mvp` | Web presentation, operator workflows, generated wiki browser | No independent trust backend; no direct wiki authoring database |

The cross-repository dependency boundary is documented in the generated wiki page **Ecosystem Dependencies** and in INTEGRITY-LATEST's [docs/architecture/ecosystem-dependencies.md](https://github.com/XibalbaTechSol/integrity-latest/blob/main/docs/architecture/ecosystem-dependencies.md).

## Definitions

| Term | Meaning in this repo |
|---|---|
| AIS | Agent Integrity Score, computed by INTEGRITY-LATEST's Oracle/scoring core and rendered here |
| BCC | Behavioral Commitment Chain pre-execution policy and signed-intent gate exposed through INTEGRITY-LATEST middleware |
| XNS | Xibalba Name Service, the human-readable agent-domain surface rendered by identity flows |
| Integrity Health | HIPAA/healthcare vertical in INTEGRITY-LATEST; not the same product as Xibalba Shield |
| Xibalba Shield | Separate endpoint-security product whose evidence can be displayed by this app |
| Canonical wiki | `INTEGRITY-LATEST/docs/wiki`; this app only renders a generated snapshot |
| Protocol TOC | Ordered left-rail wiki navigation implemented in `src/pages/WikiPage.tsx` |

## Current status

Built and verified in this repo:

- React/Vite/TypeScript application shell with landing, dashboard, identity, intelligence, health, Shield, financials, developer/docs, memory, settings, privacy, terms, and wiki routes.
- Real service clients for INTEGRITY-LATEST Oracle, user API, and BCC middleware in `src/services/`.
- Generated wiki browser at `/wiki` backed by `src/generated/wiki-data.json`.
- Wiki renderer support for canonical Markdown tables, Mermaid diagrams, relative wiki navigation, repository-source links, right-rail article TOC, and ordered left-rail Protocol TOC.
- Xibalba Solutions logo in the wiki header linked to `/`.
- Playwright regression coverage for wiki table rendering, ordered TOC behavior, logo navigation, and mobile search placement.

Still dependent on running backend services:

- Live agent fleet, AIS, markets, wallet, XNS, BAA, governance, and Shield evidence depend on INTEGRITY-LATEST services/contracts and, for Shield-specific telemetry, a running xibalba-shield deployment exporting evidence into that stack.
- When those services are not running, the frontend must fail visibly and safely rather than inventing live data.

## Application surface

| Area | Primary files | Status |
|---|---|---|
| App shell/routing | `src/App.tsx`, `src/layouts/*`, `src/components/Sidebar.tsx` | Built |
| Landing page | `src/LandingPage.tsx`, `SPECIFICATION.md`, `docs/archive/2026-08-06/landing_page_strategy.md` | Built; strategy doc remains narrative/product guidance |
| Dashboard context | `src/context/DashboardContext.tsx`, `src/services/oracle.ts`, `src/services/userapi.ts` | Built against real backend URLs |
| Identity/XNS | `src/pages/IdentityPage.tsx`, `src/chain/xns.ts`, `src/components/ui/*XNS*` | Built UI/service integration surface |
| Intelligence/telemetry | `src/pages/IntelligencePage.tsx`, `src/components/observability/*`, `src/components/ui/Telemetry*` | Built UI surface |
| Memory graph | `src/pages/MemoryPage.tsx`, `src/components/GraphMemoryView.tsx`, `src/services/graphMemory.ts` | Built UI/service surface |
| Integrity Health | `src/pages/HealthPage.tsx` | Built presentation surface; protocol truth lives in INTEGRITY-LATEST |
| Xibalba Shield | `src/pages/ShieldPage.tsx`, `src/chain/shield.ts` | Built presentation surface; Shield truth lives in xibalba-shield README/spec |
| Financials/markets | `src/pages/FinancialsPage.tsx`, `src/chain/markets.ts` | Built UI/service surface |
| Wiki | `src/pages/WikiPage.tsx`, `src/pages/WikiPage.css`, `scripts/sync-wiki.mjs`, `src/generated/wiki-data.json` | Built and regression-tested |

## Wiki synchronization

`INTEGRITY-LATEST/docs/wiki/` is the sole authoring source of truth. The MVP `/wiki` route is a read-only generated projection, and the GitHub Wiki is another downstream mirror. Direct edits to either rendered surface are not reconciled upstream and may be overwritten.

Run:

```bash
npm run sync-wiki
```

The generator reads canonical concepts, entities, architecture pages, guides, queries, and `docs/wiki/index.md`; writes `src/generated/wiki-data.json`; preserves canonical Git commit metadata when available; and prefers polished labels from `WIKI_INDEX.md` for navigation.

## Development

```bash
npm install
npm run dev -- --port 5189
npm run build
npm run test-e2e -- e2e/wiki.spec.ts
```

The dev server defaults to Vite. Backend URLs are configured through `src/config.ts` and environment variables documented by INTEGRITY-LATEST. A complete local stack requires the INTEGRITY-LATEST Oracle, user API, BCC middleware, database/Redis/OPA dependencies, and optionally xibalba-shield for endpoint-security evidence.

## Testing and validation

| Command | Purpose |
|---|---|
| `npm run build` | TypeScript build plus Vite production bundle |
| `npm run test-e2e -- e2e/wiki.spec.ts` | Focused browser regression for the wiki route |
| `npm run sync-wiki` | Regenerate the read-only wiki snapshot from canonical Markdown |
| `git diff --check` | Whitespace sanity check before handoff |

Known build warning: Vite reports large chunks because the app includes Mermaid, KaTeX, graph, and dashboard dependencies. This is a performance optimization target, not a build failure.

## Current plan

Near-term:

- Keep `/wiki` synchronized with canonical INTEGRITY-LATEST Markdown and regression-tested on desktop/mobile.
- Keep UI labels and product boundaries aligned with the three-repo dependency map.
- Continue replacing static demonstration panels with explicit real-service reads where backend endpoints are available.
- Add broader E2E coverage for Shield, identity, memory, and financial workflows as their backend contracts stabilize.

Longer-term:

- Make the MVP a production operator console for protocol users, Shield security teams, healthcare/Integrity Health buyers, and investor demos.
- Add deployment automation only after backend service availability and environment contracts are stable.
- Split large Vite chunks where it materially improves user-perceived page load.

## Documentation map

| Document | Owner | Purpose |
|---|---|---|
| [README.md](README.md) | This repo | Current application truth, status, commands, boundaries |
| [SPECIFICATION.md](SPECIFICATION.md) | This repo | Current UI/product behavior specification |
| [docs/archive/2026-08-06/landing_page_strategy.md](docs/archive/2026-08-06/landing_page_strategy.md) | This repo | Historical landing narrative |
| [INTEGRITY-LATEST docs/INTERFACE_CONTRACT.md](https://github.com/XibalbaTechSol/integrity-latest/blob/main/docs/INTERFACE_CONTRACT.md) | INTEGRITY-LATEST | Backend schemas, ports, env vars, chain conventions |
| [INTEGRITY-LATEST docs/wiki](https://github.com/XibalbaTechSol/integrity-latest/tree/main/docs/wiki) | INTEGRITY-LATEST | Canonical compiled protocol knowledge |
| [xibalba-shield README.md](https://github.com/XibalbaTechSol/xibalba-shield/blob/main/README.md) | xibalba-shield | Shield implementation status and plan |
