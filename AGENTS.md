# Integrity Protocol — Agent Instructions

This file is the single repository guidance authority. `CLAUDE.md` imports it;
there is no second procedural authority under `.agents/`.

## Quick-start for Jules and other GitHub-integrated agents

### What this repo is

A monorepo implementing a self-sovereign agent identity and reputation protocol
on Base (EVM). Five packages, each with its own real test suite:

| Package | Language / stack | Test command |
|---|---|---|
| `contracts/` | Solidity / Foundry | `forge test -vvv` |
| `integrity-oracle/` | Rust / Axum | `cargo test --workspace` |
| `integrity-sdk/` | Python / uv | `uv run pytest` |
| `integrity-cli/` | Python / uv | `uv run pytest` |
| `bcc_middleware/` | Python / uv + OPA | `uv run pytest && opa test policies/ -v` |

CI runs all five in parallel (plus a `docs` job). See `.github/workflows/ci.yml`.
`integrity-zkp/` was cut in A1 (`3739d3c5`) — ZK proving is retired for this phase; only stale
build artifacts remain, no source. See `integrity-lab`'s cut-path manifest.

### Non-negotiable rules for any agent making code changes

1. **No silent mocks.** If a real implementation doesn't exist yet, mark it
   `[PLANNED]` — do not write code that pretends to do something it doesn't.
   This project exists specifically because its predecessor faked ZK proving,
   TEE attestation, and OPA evaluation while documenting them as real.

2. **Run the real test suite for every package you touch.** Not just
   typecheck — the actual test runner listed in the table above.

3. **Never push directly to `main`.** Open a PR. CI must be green before
   merge.

4. **Read the interface contract before changing any cross-package schema.**
   `docs/INTERFACE_CONTRACT.md` is the authoritative record of ports,
   request/response shapes, and protocol decisions. If your change affects a
   cross-package schema, update that file in the same PR.

5. **Update the wiki after every material change.** See the full loop in
   `AGENTS.md`'s Wiki-as-memory procedure. Short version:
   - Update the relevant `docs/wiki/entities/<package>.md` page.
   - Append one entry to `docs/wiki/WIKI_LOG.md` (append-only).
   - Update `docs/wiki/WIKI_INDEX.md` if pages were added or removed.

### What Jules is used for in this repo

Jules dispatch is **not** wired into this repo's own CI anymore — `.github/workflows/ci.yml`
explicitly notes it was intentionally removed and relocated to
`xibalba-agents/ops/jules-loop/`. When Jules is invoked (from that external loop, on a CI
failure), its task is to investigate the failing run's logs, identify the root cause, fix it,
and open a PR. It should:

- Read the failing job's logs via the GitHub Actions run URL in the prompt.
- Read the relevant package's wiki entity page in `docs/wiki/entities/`.
- Make the minimal change that fixes the root cause — not a workaround that
  hides the failure.
- Run the package's real test suite (see table above) to confirm the fix.
- Follow all five rules above when writing the fix and the PR description.
- **Not** force-push, bypass the test suite, or touch `main` directly.

### Key files to read before making any change

- `AGENTS.md` — repository guidance and wiki procedural schema
- `docs/INTERFACE_CONTRACT.md` — cross-package schemas, ports, decisions
- `docs/wiki/WIKI_INDEX.md` — map of all 35 wiki pages (24 concepts, 8 entities, 2 architecture, 1 query)
- `docs/wiki/WIKI_LOG.md` — recent session history (last ~10 entries)
- `docs/TESTING.md` — test pyramid: what CI covers vs. what needs a live stack
- Per-package `README.md` — setup, run, test instructions for each package

## Wiki-as-memory procedure

This repository's compiled wiki is governed here as part of the same guidance
file. `docs/wiki/WIKI_SCHEMA.md` defines page content, `docs/INTERFACE_CONTRACT.md`
defines cross-package contracts, and `docs/TESTING.md` defines the test pyramid.

### Three-layer memory model

| Layer | Location | Purpose | Mutability |
|---|---|---|---|
| Raw sources | `contracts/`, `integrity-*/`, `bcc_middleware/`, configs | Ground truth | Written normally during development |
| Interface contract | `docs/INTERFACE_CONTRACT.md` | Cross-package decisions | Update when a boundary changes |
| Compiled wiki | `docs/wiki/` | Synthesized, interlinked knowledge | Update after material changes |

### Read → work → write → lint

At the start of a material session, read `docs/wiki/WIKI_SCHEMA.md`,
`docs/wiki/WIKI_INDEX.md`, the recent `docs/wiki/WIKI_LOG.md` entries, and the
affected entity page. During work, record changed files, APIs, schemas,
endpoints, and removed features. Afterward:

1. Update the affected wiki entity or create one from the schema template.
2. Update `docs/wiki/WIKI_INDEX.md` when pages are added or removed.
3. Append one entry to `docs/wiki/WIKI_LOG.md`; never rewrite older entries.
4. Update `docs/INTERFACE_CONTRACT.md` when a cross-package boundary changes.
5. Run orphan, dead-link, source-drift, staleness, counter, and TOC checks.

Only document behavior verified in source and tests. Unbuilt behavior is
`[PLANNED]`; mocks must not be presented as real implementations.

### Canonical repository structure

The wiki entity map must stay aligned with these package owners:

| Directory | Wiki entity |
|---|---|
| `contracts/` | `entities/contracts.md` |
| `integrity-oracle/` | `entities/integrity-oracle.md` |
| `integrity-sdk/` | `entities/integrity-sdk.md` |
| `integrity-cli/` | `entities/integrity-cli.md` |
| `bcc_middleware/` | `entities/bcc_middleware.md` |

Fix the table and wiki together if the repository structure changes. Every
entity page's `source_files` must point to files that exist now.

### Continuous test-coverage procedure

For implementation changes, run the touched package's real validation, identify
new coverage gaps, add deterministic tests against real dependencies, and rerun
the suite. For multiple independent gaps, parallel test work is appropriate;
the orchestrating session must rerun and verify the final suite before logging
the result. A small, obvious gap may be covered inline.
