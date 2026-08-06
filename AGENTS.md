# Integrity Protocol — Agent Instructions

> **Full protocol** is in [`.agents/AGENTS.md`](.agents/AGENTS.md). Read that
> file first. Everything below is a quick-start summary for agents (including
> Jules) that read only the root `AGENTS.md`.

## Quick-start for Jules and other GitHub-integrated agents

### What this repo is

A monorepo implementing a self-sovereign agent identity and reputation protocol
on Base (EVM). Eight packages, each with its own real test suite:

| Package | Language / stack | Test command |
|---|---|---|
| `contracts/` | Solidity / Foundry | `forge test -vvv` |
| `integrity-zkp/` | Noir / Barretenberg | `nargo test` |
| `integrity-oracle/` | Rust / Axum | `cargo test --workspace` |
| `integrity-sdk/` | Python / uv | `uv run pytest` |
| `integrity-cli/` | Python / uv | `uv run pytest` |
| `bcc_middleware/` | Python / uv + OPA | `uv run pytest && opa test policies/ -v` |
| `integrity-userapi/` | Python / uv + Postgres | `uv run pytest` (needs Postgres on 5435) |
| `integrity-dashboard/` | React / Vite / TypeScript | `npm test` |

CI runs all eight in parallel. See `.github/workflows/ci.yml`.

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
   `.agents/AGENTS.md` §2. Short version:
   - Update the relevant `docs/wiki/entities/<package>.md` page.
   - Append one entry to `docs/wiki/WIKI_LOG.md` (append-only).
   - Update `docs/wiki/WIKI_INDEX.md` if pages were added or removed.

### What Jules is used for in this repo

Jules is invoked automatically by `.github/workflows/ci.yml`'s
`notify-jules-on-failure` job when a CI run on `main` fails. Jules's task is
to investigate the failing run's logs, identify the root cause, fix it, and
open a PR. It should:

- Read the failing job's logs via the GitHub Actions run URL in the prompt.
- Read the relevant package's wiki entity page in `docs/wiki/entities/`.
- Make the minimal change that fixes the root cause — not a workaround that
  hides the failure.
- Run the package's real test suite (see table above) to confirm the fix.
- Follow all five rules above when writing the fix and the PR description.
- **Not** force-push, bypass the test suite, or touch `main` directly.

### Key files to read before making any change

- `.agents/AGENTS.md` — full procedural schema (read this)
- `docs/INTERFACE_CONTRACT.md` — cross-package schemas, ports, decisions
- `docs/wiki/WIKI_INDEX.md` — map of all 25 wiki pages
- `docs/wiki/WIKI_LOG.md` — recent session history (last ~10 entries)
- `docs/TESTING.md` — test pyramid: what CI covers vs. what needs a live stack
- Per-package `README.md` — setup, run, test instructions for each package
