# Integrity Protocol — Testing Strategy

> How every package in this monorepo is tested, and how the layers fit
> together. See `.agents/AGENTS.md` §6 for the loop this feeds into
> (continuous test-coverage discipline, including when to fan work out to
> parallel background agents) and `docs/INTERFACE_CONTRACT.md` for the
> schemas/ports each layer talks to.

## The test pyramid

```
                    ┌─────────────────────────────┐
                    │   Playwright E2E (browser)   │  integrity-dashboard/e2e/
                    │   real backends, real chain  │  make test-e2e
                    └─────────────────────────────┘
              ┌───────────────────────────────────────┐
              │      Component tests (vitest+msw)      │  integrity-dashboard/src/**/*.test.tsx
              │   real components, HTTP boundary mocked │  npm test
              └───────────────────────────────────────┘
   ┌──────────────────────────────────────────────────────────┐
   │  Per-package unit/integration tests (forge/cargo/pytest)  │  make test
   │        real toolchains — several already infra-backed     │
   └──────────────────────────────────────────────────────────┘
```

**Ground rule that applies at every layer**: no silent mocks. A test either
exercises real code against a real dependency (real anvil, real Postgres,
real OPA server, real `bb prove`/`verify`), or it mocks exactly one seam
deliberately (e.g. `msw` at the HTTP boundary in component tests) and says
so. Nothing pretends a stubbed dependency is the real thing.

## Layer 1 — per-package unit/integration tests

Run via `make test` from the repo root, or per-package directly. Every
suite is real, not smoke-tested against fixtures:

| Package | Runner | What's real |
|---|---|---|
| `contracts/` | `forge test` | Real EVM (Foundry's local VM), 165 tests |
| `integrity-zkp/` | `nargo test` | Real Noir circuit compilation |
| `integrity-oracle/` | `cargo test` | 37 lib tests (29 backend + 8 scoring-core) + a real e2e test (anvil + Deploy.s.sol + SDK registration + Postgres + Redis + HTTP, opt-in via `ORACLE_E2E=1`) |
| `integrity-sdk/` | `uv run pytest` | Chain-touching tests run against a real anvil (`tests/conftest.py`'s `deployed_chain` fixture: real `anvil` subprocess + real `Deploy.s.sol`/`DeployMarkets.s.sol`), 97 tests, +1 opt-in (`ORACLE_E2E=1`) = 98 |
| `integrity-cli/` | `uv run pytest` | Includes 1 real on-chain chain test, 49 total |
| `bcc_middleware/` | `uv run pytest` + `opa test .` | Real OPA server calls, real per-agent chain resolution, 49 + 12 |
| `integrity-userapi/` | `uv run pytest` | Real Postgres container (not sqlite/mocked), 33 tests |
| `integrity-dashboard/` | `npm test` (vitest) | Real React components, HTTP boundary mocked via `msw` — the ONE deliberate mock in this whole pyramid, and it's scoped to exactly the network seam, not business logic |

This layer runs on every change. Fast (seconds to low minutes per package),
no full-stack boot required.

## Layer 2 — Playwright E2E (`integrity-dashboard/e2e/`)

The layer above component tests: a real Chromium browser driving the real
`integrity-dashboard` app, which talks to a real running backend stack — not
`msw`, not any mock. This is what proves the pieces work *together*
through the actual UI, which no per-package suite (each testing its own
package in isolation) or component test (mocking the network boundary)
can prove on its own.

**No `global-setup.ts`/`global-teardown.ts` exists in this repo** — an
earlier version of this doc described one in detail; it was aspirational,
not real (confirmed by reading `integrity-dashboard/playwright.config.ts`
and `ls integrity-dashboard/e2e/`, corrected 2026-08-13). What actually
exists: `playwright.config.ts`'s `webServer` boots `npm run dev -- --port
5189` and waits for it — nothing else. The real backend stack (chain,
oracle, bcc_middleware, userapi, and — for `/memory` specifically —
`xibalba-cortex`'s separate `local_api.py`) must be started manually,
first, by whoever runs the suite. Every spec is written to degrade to a
real, honest empty state rather than assert fabricated data when a given
piece of that stack has no seeded activity yet — this is *by design*, not
a fallback for a broken setup step.

**To run the full suite against real data:**

```bash
make chain      # local anvil + genesis deploy -> deployments.local.json
# docker-compose (the standalone hyphenated binary) is not installed in every
# environment; `docker compose` (the plugin) is the more portable invocation —
# both should work if available.
docker compose up --build postgres redis opa oracle-backend bcc-middleware userapi-postgres userapi
# Note: docker-compose.yml's `mvp` service (../integrity-mvp) and `shield`
# service (../xibalba-shield) reference sibling repos that may not exist on
# disk — target services explicitly by name (as above) rather than running
# a bare `docker compose up --build`, which tries to build every service.
cd integrity-dashboard && npx playwright test
```

For specs touching `/memory`, additionally run `xibalba-cortex`'s
`local_api.py` (a separate repo, not started by any of the above):

```bash
cd xibalba-cortex && uv run python -m xibalba_cortex.local_api \
  --home <a-fresh-empty-profile-dir> --allowed-origin http://127.0.0.1:5189
```

Point `--home` at a throwaway directory, not a real Hermes profile —
`xibalba-cortex`'s own background session-capture means even a freshly
created store won't reliably stay at zero records, so `/memory` specs
should assert real, non-fabricated counts (e.g. `/^\d+ memories$/`), not a
literal `0`.

**Local network only — never live Base Sepolia** for the *oracle-backed*
data path (`RPC_URL` pointed at local anvil). Note this is a stack-config
choice, not something every dashboard component obeys uniformly: a few
components (`StakingPanel`, `CreditPanel`, `PrivacyPanel`, `TokenWallet`,
`ActuarialHub`, all of `HealthPage`'s BAA/EHR-gate/quarantine reads) do
direct `ethers.JsonRpcProvider` reads against addresses hardcoded from the
committed `integrity-dashboard/src/deployments.baseSepolia.json` — those
*always* target real Base Sepolia regardless of local chain config, so an
agent registered only on a local chain will show real, honest empty states
on exactly those panels. See
`docs/wiki/entities/integrity-dashboard.md` for the full per-page
breakdown.

**Run it**: `make test-e2e` from the repo root (equivalent to `cd
integrity-dashboard && npx playwright test`, but does **not** stand up the
backend stack above first — see the manual steps). Requires `anvil`/`forge`
on `PATH`, `cargo`, Docker, and the `integrity-sdk` `uv` venv already synced
(`cd integrity-sdk && uv sync`) — same toolchain the rest of this repo
already assumes, nothing E2E-specific to install beyond `npx playwright
install chromium` once.

**Convention for new specs**: one spec file per route
(`integrity-dashboard/e2e/<page>.spec.ts`), covering the honest empty state
*and* the real-data state for every panel where both are reachable, ending
in a full-page screenshot — reviewed visually before the page is considered
done, since a test can pass while a layout is visibly broken (this caught
real bugs; see `docs/wiki/entities/integrity-dashboard.md`). Cover real
negative paths too, not just happy paths (a low-AIS agent's market-entry
control is genuinely disabled by a real on-chain check, a wrong-password
login genuinely surfaces a real 401, a resolved market's payout genuinely
reflects an on-chain balance change) — a spec that only exercises the happy
path proves less than it looks like it does.

## What's explicitly NOT here yet: hosted CI

`make test` and `make test-e2e`, run by a human (or an agent) before
considering a change done, are the enforcement mechanism — see
`.agents/AGENTS.md` §6. No GitHub Actions (or other hosted CI) is wired up
yet; revisit once/if that changes.
