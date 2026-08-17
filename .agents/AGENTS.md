# Integrity Protocol — Wiki-as-Memory Loop

> This file governs how any agent (or human) working in this repo reads,
> writes, and maintains `docs/wiki/` — the project's compiled long-term
> memory. It is the **procedural schema**; `docs/wiki/WIKI_SCHEMA.md` is the
> **content schema** (page format, taxonomy); `docs/INTERFACE_CONTRACT.md`
> is the **cross-package contract** (ports, schemas, protocol decisions);
> `docs/TESTING.md` is the **test-pyramid reference** (what `make test` vs
> `make test-e2e` each cover, per-package runner conventions). All four are
> read together.

## 1. The Three-Layer Memory Model

| Layer | Location | Purpose | Mutability |
|---|---|---|---|
| Raw sources | `contracts/`, `integrity-*/`, `bcc_middleware/`, configs | Ground truth — the actual code | Written normally during dev work |
| Interface contract | `docs/INTERFACE_CONTRACT.md` | Cross-package decisions (schemas, ports, protocol choices) | Updated when a cross-package decision changes — every package must then reconcile |
| Compiled wiki | `docs/wiki/` | Synthesized, interlinked knowledge base | Updated on every material code change |

## 2. The Read → Work → Write → Lint Loop

Every session that materially changes code in this repo runs this loop:

**Phase 1 — READ (session start)**
1. Read `docs/wiki/WIKI_SCHEMA.md` for page conventions.
2. Read `docs/wiki/WIKI_INDEX.md` for the current knowledge map.
3. Read `docs/wiki/WIKI_LOG.md` (last ~10 entries) for recent context.
4. If touching a specific package, read its existing wiki page(s) first.

**Phase 2 — WORK**
5. Do the actual task. Track what changed: new files, changed APIs/schemas,
   renamed exports, added/removed endpoints, deleted features.

**Phase 3 — WRITE (memory commit)**
6. Update the wiki page(s) affected. If none exists yet for a new
   component, create one using the frontmatter template in
   `WIKI_SCHEMA.md`.
7. Update `WIKI_INDEX.md` — every page must be listed; remove entries for
   deleted pages; keep the page counter accurate.
8. Append one entry to `WIKI_LOG.md` (append-only — never edit past
   entries, only add new ones).
9. If the change affects a cross-package schema/port/protocol decision,
   update `docs/INTERFACE_CONTRACT.md` too, in the same pass.

**Phase 4 — LINT (dedicated sync passes, e.g. after a batch of package
rebuilds lands, or periodically)**
10. Orphan detection: wiki pages not listed in `WIKI_INDEX.md`.
11. Dead-link detection: index entries pointing at nonexistent pages.
12. Staleness audit: flag pages whose `updated` date is >14 days old.
13. Drift check: for each entity page's `source_files`, confirm those
    files still exist and still match what the page describes; downgrade
    `confidence: high` → `medium` if not reverified.
14. Counter reconciliation: recount actual pages, fix the index counter.

## 3. Content rule (non-negotiable)

**No aspirational content.** Only document what exists in the code right
now. A feature described in a spec but not yet implemented is marked
`[PLANNED]` — never written as if it's real. This project's predecessor
mocked its ZK proving, TEE attestation, and policy evaluation while
documenting them as if real; this rewrite's entire point is not repeating
that, in the code AND in the wiki that describes it.

## 4. Repository structure (canonical — keep this in sync with reality)

| Directory | Description | Wiki entity page |
|---|---|---|
| `contracts/` | Solidity/Foundry on-chain identity, reputation, staking, ZK verification | `entities/contracts.md` aggregate by default; split out `entities/<Contract>.sol.md` only for contracts needing standalone API docs |
| `integrity-zkp/` | Noir/Barretenberg ZK attestation circuit | `entities/integrity-zkp.md` |
| `integrity-oracle/` | Rust/Axum telemetry ingestion + AIS scoring + Merkle anchoring | `entities/integrity-oracle.md` |
| `integrity-sdk/` | Python agent SDK: DID, BCC commitments, ZK proving, OPA check, attestation | `entities/integrity-sdk.md` |
| `integrity-cli/` | Python/Typer developer CLI | `entities/integrity-cli.md` |
| `bcc_middleware/` | FastAPI + OPA pre-execution policy gating (part of the Oracle trust domain, see §6.10) | `entities/bcc_middleware.md` |
| `integrity-userapi/` | FastAPI + Postgres user accounts/auth — strictly non-chain | `entities/integrity-userapi.md` |
| `integrity-dashboard/` | React/Vite/TS — the ONE dashboard/landing app, plus `demo/` (Python closed-loop scenario engine). | `entities/integrity-dashboard.md` |

If this list diverges from what's actually in the repo, fix this table AND
the wiki in the same pass — don't let them drift apart.

## 5. Sync triggers

Run the Write phase (§2 Phase 3) when:
- A new package or module is created.
- A contract/API/CLI interface changes.
- An endpoint is added, changed, or removed.
- A dependency is added or removed.
- A schema in `docs/INTERFACE_CONTRACT.md` changes.
- A previously-mocked component becomes a real implementation (or vice
  versa) — this is the single most important thing to keep truthful here.

## 6. Continuous test-coverage loop

Every session that changes implementation code runs this loop before
finishing (restored from the predecessor project's fuller version — the
prior port of this file had trimmed it down to a single inline step,
losing the parallel-subagent mechanism that made it actually scale):

**Phase 1 — COVERAGE DISCOVERY**
1. Run that package's real validation (`forge test`, `nargo test`,
   `cargo test`, `pytest`, or the dashboard's `npm run build && npm run lint`)
   — not just typecheck. The dashboard currently has no unit/component test
   script. If the change touches a dashboard page, also run `make test-e2e`
   (Playwright, real browser against a separately prepared backend stack — see
   `docs/TESTING.md`).
2. Identify newly added or changed features (endpoints, contract
   functions, exported SDK calls, dashboard pages) lacking real test
   coverage.

**Phase 2 — PARALLEL TEST GENERATION & VERIFICATION**
3. For each coverage gap, dispatch an independent background agent (this
   harness's `Agent` tool, `run_in_background: true`) rather than writing
   every test inline in the main session — this is the part worth keeping
   from the old loop, it's what let coverage work scale past what one
   session could grind through serially.
4. Each dispatched agent must operate autonomously end-to-end: write a
   real, deterministic test for its assigned gap (never a placeholder or
   a mock standing in for the real dependency — same "no silent mocks"
   rule as everywhere else in this repo), save it to the package's real
   test directory, run the package's actual test runner itself, and
   iterate on failures until green — without further orchestrator
   back-and-forth.

**Phase 3 — CONSOLIDATION**
5. The orchestrating session waits for dispatched agents to report back,
   confirms their tests are genuinely green (re-run the suite, don't just
   trust the agent's self-report), and only then logs the result
   (pass/fail, which gaps were closed) as one entry in `WIKI_LOG.md`.

For a single small, obvious gap found mid-task, adding the test inline
without spinning up a background agent is fine — Phase 2's parallel
dispatch is for when there are multiple independent gaps worth working
concurrently, not a mandatory hop for every one-line test.
