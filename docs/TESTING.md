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

**What `e2e/global-setup.ts` stands up, for real, before any spec runs:**
1. A dedicated local `anvil` chain (fixed port, see `e2e/constants.ts` —
   deliberately NOT dynamically chosen; Playwright's `webServer` needs
   `VITE_ORACLE_URL` at boot time, before `globalSetup` would otherwise
   have picked a port).
2. The real genesis deploy (`Deploy.s.sol`) + market layer
   (`DeployMarkets.s.sol`) against that chain.
3. An ephemeral, dedicated Postgres + Redis (Docker containers, separate
   from any dev-time `docker-compose` services — an E2E run shouldn't
   write test rows into a database a developer is also using).
4. The real `integrity-oracle` backend (`cargo run`), pointed at the fresh
   chain + fresh DB.
5. One real seed agent, registered through the real
   `integrity_sdk.registration.register_agent` flow — on-chain AND in the
   oracle's own DB (not `skip_oracle_registration`) — so specs assert
   against real, oracle-served data.

`e2e/global-teardown.ts` tears all of it back down after the run.

**Local network only — never live Base Sepolia.** Base Sepolia stays the
live investor/developer demo target (`integrity-dashboard/demo/`, `make demo`);
spinning up a fresh chain per E2E run would be slow, cost real (if tiny)
gas, and be non-deterministic across runs. Mirrors the convention
`integrity-sdk`'s and `integrity-oracle`'s own test suites already use.

**Run it**: `make test-e2e` from the repo root, or `cd integrity-dashboard && npx
playwright test`. Requires `anvil`/`forge` on `PATH`, `cargo`, Docker, and
the `integrity-sdk` `uv` venv already synced (`cd integrity-sdk && uv
sync`) — same toolchain the rest of this repo already assumes, nothing
E2E-specific to install beyond `npx playwright install chromium` once.

**Convention for new specs**: as `integrity-dashboard`'s dashboard pages get
built out (task #21 — Markets, Leaderboard, Wallet, Capital Allocation,
Cognition, Identity, Shield, Landing), each new page's Playwright spec
ships in the *same pass* as the page, not as a follow-up. Cover real
negative paths too, not just happy paths (a low-AIS agent's market-entry
control is genuinely disabled by a real on-chain check, an unauthenticated
user is genuinely redirected, a resolved market's payout genuinely reflects
an on-chain balance change) — a spec that only exercises the happy path
proves less than it looks like it does.

**Known simplification**: `bcc_middleware` is not yet part of
`global-setup.ts`'s stack (not needed by the current specs). Any spec that
exercises BCC-commitment history or BAA status should add it to setup
first, not silently pass against a `bcc_middleware`-shaped 404/connection
error the way `agent-detail.spec.ts` currently, honestly, does.

## What's explicitly NOT here yet: hosted CI

This repo is not a git repository today (no remote), so there is nothing
for GitHub Actions (or any hosted CI) to trigger from. `make test` and
`make test-e2e`, run by a human (or an agent) before considering a change
done, are the enforcement mechanism until that changes — see
`.agents/AGENTS.md` §6. This is a real, current gap, not a silently-skipped
one; revisit once/if this repo gets a git remote.
