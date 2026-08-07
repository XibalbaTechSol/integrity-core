# Contributor validation matrix

Run these commands from the repository root unless the command is already scoped to a package. The matrix is generated from the root `Makefile`, package manifests, and CI workflows.

| Command | Scope | Requirements | Expected result | Limitation |
|---|---|---|---|---|
| `make setup` | Toolchains and dependencies | Network access | Installs package dependencies | One-time per environment |
| `make test` | All package unit/integration suites | `forge`, `nargo`, `cargo`, `uv`, `npm`, `opa`, and a Postgres container for userapi | Each suite passes and writes its outcome to `.integrity-test-status` | Takes minutes; userapi needs Postgres |
| `cd contracts && forge test` | Contracts | Foundry | 165 tests pass | Local EVM only |
| `cd integrity-zkp && nargo test` | ZKP circuits | Noir / nargo | Circuits compile and tests pass | Requires Noir toolchain |
| `cd integrity-oracle && cargo test` | Oracle | Cargo | 37 tests pass | `ORACLE_E2E=1` adds a live end-to-end test |
| `cd integrity-sdk && uv run pytest` | SDK | `uv`, `anvil` | 97 tests pass | Chain tests boot a real local anvil |
| `cd integrity-cli && uv run pytest` | CLI | `uv` | 49 tests pass | Includes one real on-chain test |
| `cd bcc_middleware && uv run pytest && opa test .` | Middleware | `uv`, OPA | Pytest and OPA tests pass | Needs a reachable OPA server |
| `cd integrity-userapi && uv run pytest` | User API | Docker / Postgres | 33 tests pass | Postgres container required |
| `cd integrity-dashboard && npm test` | Dashboard components | Node / npm | Vitest suite passes | Uses `msw` only at the HTTP seam |
| `make test-e2e` | Browser E2E | `forge`/`anvil`, `cargo`, Docker, synced SDK venv, Playwright Chromium | Playwright specs pass against a real local stack | Slow; starts its own chain, DB, Redis, and oracle |
| `make chain` / `make chain-reset` | Local chain | Foundry / anvil | Genesis deploy and saved state management | Local network only |
| `make up` / `make down` | Full stack | Docker | Containers start or stop | Defaults to live Base Sepolia |
| `make demo` | Demo scenario engine | Live RPC credentials, `FUNDER_PRIVATE_KEY`, `INTEGRITY_WALLET_PASSWORD` | Demo runs real agent allocation loop | Uses real transactions and gas |
| `make check-deploy` | Deployment freshness | Running stack | Reports stale service images | Only meaningful with a running stack |
| `make sync-abis` | Contract ABI sync | Foundry | ABIs regenerated and synced | Run after contract interface changes |
