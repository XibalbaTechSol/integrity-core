# Contributor validation matrix

Run these commands from the repository root unless the command is already scoped to a package. The matrix is generated from the root `Makefile`, package manifests, and CI workflows.

| Command | Scope | Requirements | Expected result | Limitation |
|---|---|---|---|---|
| `make setup` | Toolchains and dependencies | Network access | Installs package dependencies | One-time per environment |
| `make test` | Package suites plus dashboard build/lint | `forge`, `nargo`, `cargo`, `uv`, `npm`, `opa`, and Postgres for userapi | Package suites plus `npm run build && npm run lint` pass and write outcomes to `.integrity-test-status` | Does not run Playwright; userapi needs Postgres |
| `cd contracts && forge test` | Contracts | Foundry | Current suite passes; 209 tests passed on 2026-08-17 | Local EVM only |
| `cd integrity-zkp && nargo test` | ZKP circuits | Noir / nargo | Circuits compile and tests pass | Requires Noir toolchain |
| `cd integrity-oracle && cargo test` | Oracle | Cargo | Current workspace suite passes | `ORACLE_E2E=1` adds a live end-to-end test |
| `cd integrity-sdk && uv run pytest` | SDK | `uv`, `anvil` | Current suite passes | Chain tests boot a real local anvil |
| `cd integrity-cli && uv run pytest` | CLI | `uv` | Current suite passes | Includes real local-chain coverage |
| `cd bcc_middleware && uv run pytest && opa test .` | Middleware | `uv`, OPA | Pytest and OPA tests pass | Needs a reachable OPA server |
| `cd integrity-userapi && uv run pytest` | User API | Docker / Postgres | Current suite passes | Postgres container required |
| `cd integrity-dashboard && npm run build && npm run lint` | Dashboard static validation | Node / npm | Production build and ESLint pass | No dashboard unit/component test script exists |
| `make test-e2e` | Browser E2E | Separately booted chain/backends, synced SDK environment, Playwright Chromium | Playwright specs pass against the prepared local stack | Slow; starts only Vite, not chain, DB, Redis, or Oracle |
| `make chain` / `make chain-reset` | Local chain | Foundry / anvil | Genesis deploy and saved state management | Local network only |
| `make up` / `make down` | Full stack | Docker | Containers start or stop | Defaults to live Base Sepolia |
| `make demo` | Demo scenario engine | Live RPC credentials, `FUNDER_PRIVATE_KEY`, `INTEGRITY_WALLET_PASSWORD` | Demo runs real agent allocation loop | Uses real transactions and gas |
| `make check-deploy` | Deployment freshness | Running stack | Reports stale service images | Only meaningful with a running stack |
| `make sync-abis` | Contract ABI sync | Foundry | ABIs regenerated and synced | Run after contract interface changes |
