.PHONY: setup chain chain-reset up down test test-e2e sync-abis demo check-deploy verify-kernel

setup:
	cd contracts && npm install
	cd integrity-oracle && cargo build
	cd integrity-sdk && uv sync
	cd integrity-cli && uv sync
	cd bcc_middleware && uv sync
	cd integrity-dashboard && npm install
	cd integrity-userapi && uv sync

chain:
	touch deployments.local.json
	@# Load existing state if present so registered agents survive restarts.
	@# On first run .anvil-state.json doesn't exist — no --load-state flag.
	@# On subsequent runs the saved state is restored and contracts are already
	@# deployed at their original addresses, so the forge script is skipped.
	@if [ -f .anvil-state.json ]; then \
		echo "Restoring Anvil state from .anvil-state.json..."; \
		cd contracts && anvil --host 0.0.0.0 \
			--load-state ../.anvil-state.json \
			--dump-state ../.anvil-state.json & \
		sleep 2; \
		echo "Chain restored — contracts and registered agents intact."; \
	else \
		echo "No saved state found — fresh chain + genesis deploy..."; \
		cd contracts && anvil --host 0.0.0.0 \
			--dump-state ../.anvil-state.json & \
		sleep 2; \
		cd contracts && FUNDER_PRIVATE_KEY=0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80 \
			forge script script/Deploy.s.sol --rpc-url http://localhost:8545 --broadcast; \
	fi

# Wipe saved Anvil state and force a clean genesis deploy on the next `make chain`.
# Use this when you've changed contracts and need fresh addresses.
chain-reset:
	@echo "Removing .anvil-state.json — next 'make chain' will do a full genesis deploy."
	rm -f .anvil-state.json
	rm -f deployments.local.json

# Extracts {abi, bytecode} for the 3 contracts integrity-sdk's chain.py needs to deploy
# directly (SovereignAgent, StateAnchor) or call (AgentPrimitivesFactory) out of forge's
# build artifacts in contracts/out/, trimmed to just what a Python caller needs — not a
# runtime cross-package filesystem dependency, a deliberate one-way sync step run after
# any contract interface change.
sync-abis:
	cd contracts && forge build
	python3 scripts/sync_abis.py

# Halmos (0.3.3, pinned) symbolic/bounded-model-checking pass over the Phase I kernel slice --
# workstream 3 of docs/plans/2026-08-24-phase1-formal-verification-proposal.md. Isolated in its
# own uv-managed venv (contracts/.venv-halmos), never installed globally, matching this repo's
# existing per-package Python isolation. --ast is required: without it Halmos silently skips
# every contract's build artifact ("KeyError: 'ast'") rather than erroring loudly. Creates the
# venv on first run if missing. Runs both the harness proof (KernelSwapHarnessTest -- the real
# kernel installs via governance swap, PRODUCTION_GAPS.md §42) and the four target properties
# (KernelPropertiesTest -- PRODUCTION_GAPS.md §43); previously only ran the former, a known gap
# now closed.
verify-kernel:
	cd contracts && [ -d .venv-halmos ] || uv venv .venv-halmos --python 3.12
	cd contracts && uv pip install --python .venv-halmos/bin/python "halmos==0.3.3"
	cd contracts && forge build --ast
	cd contracts && .venv-halmos/bin/halmos --contract KernelSwapHarnessTest --root .
	cd contracts && .venv-halmos/bin/halmos --contract KernelPropertiesTest --root .

# Is the running stack actually built from the code in this tree? On 2026-07-30 the
# oracle image was three minutes older than the commit adding the Verification Ladder
# ceiling, so a live security control was documented, tested, committed — and not
# running, with every other signal saying it was. Never let that be invisible again.
check-deploy:
	python3 scripts/check_deploy_freshness.py

# Default target network is Base Sepolia (see root .env) — the stack runs against the real
# deployed protocol so testnet inconsistencies surface before mainnet.
# `--build` makes drift impossible for services started here; the post-check catches
# anything already running that this invocation did not rebuild.
# Content-hash args, one per service (scripts/service_content_hash.py, PRODUCTION_GAPS.md
# §22) — baked into each image as a LABEL so check-deploy can compare exact source content
# instead of an mtime approximation.
ORACLE_SOURCE_HASH := $(shell python3 scripts/service_content_hash.py oracle-backend)
BCC_MIDDLEWARE_SOURCE_HASH := $(shell python3 scripts/service_content_hash.py bcc-middleware)
DASHBOARD_SOURCE_HASH := $(shell python3 scripts/service_content_hash.py dashboard)
USERAPI_SOURCE_HASH := $(shell python3 scripts/service_content_hash.py userapi)
export ORACLE_SOURCE_HASH BCC_MIDDLEWARE_SOURCE_HASH DASHBOARD_SOURCE_HASH USERAPI_SOURCE_HASH

up:
	docker-compose up --build
	@python3 scripts/check_deploy_freshness.py --warn-only || true

# Local-anvil escape hatch. Anvil is no longer the default: agents registered locally do
# not exist on Base Sepolia, so XNS/governance/primitive reads fail against a local chain
# and the dashboard degrades to unnamed agents. Run `make chain` first.
up-local:
	RPC_URL=http://localhost:8545 \
	CHAIN_ID=31337 \
	DOCKER_RPC_URL=http://host.docker.internal:8545 \
	DOCKER_DEPLOYMENTS_FILE=/deployments.local.json \
	docker-compose up --build

down:
	docker-compose down

# Each suite's outcome is recorded to .integrity-test-status (gitignored), which the
# post-commit Trust Vault hook hashes into the next commit's leaf. Without it every anchored
# leaf says "unverified" — honest, but it means the anchored history records that work
# happened, never that it was sound.
#
# $(CURDIR), not a bare relative path — and `{ ...; false; }` on the failure branch.
# Both are load-bearing; the previous form was
#
#     cd pkg && uv run python -m pytest && cd .. && $(TEST_STATUS) pkg pass || $(TEST_STATUS) pkg fail
#
# which had two compounding bugs (found 2026-07-31 by actually running a failing suite):
#
#  1. When pytest failed, `&&` short-circuited so `cd ..` never ran, and the `||` branch
#     tried to exec `scripts/record_test_status.py` from *inside* the package directory,
#     where it does not exist. So a FAILURE WAS NEVER RECORDABLE — the mechanism that
#     feeds test outcomes into the anchored evidence chain could only ever write `pass`.
#     That is the worst possible failure direction for an evidence system, and it is a
#     contributing cause of audit finding F5 (every leaf `unverified`).
#  2. That crash then aborted `make test` at the first failing package, so the packages
#     after it never ran at all — one bcc_middleware failure silently skipped userapi and
#     dashboard entirely, while looking like a single ordinary failure.
#
# Each suite branch records pass or fail and returns success so the remaining suites still run.
# The finalizer derives the aggregate result and returns nonzero after all expected outcomes have
# been persisted; recorder/instrumentation errors still stop immediately.
TEST_RUN_ID := $(shell python3 -c 'import uuid; print(uuid.uuid4())')
TEST_STATUS := uv run --project $(CURDIR)/integrity-sdk python $(CURDIR)/scripts/record_test_status.py --run-id $(TEST_RUN_ID)

test:
	$(TEST_STATUS) --begin contracts zkp oracle sdk cli bcc userapi dashboard
	@if cd contracts && forge test; then $(TEST_STATUS) contracts pass; else $(TEST_STATUS) contracts fail; fi
	@if cd integrity-zkp && nargo test; then $(TEST_STATUS) zkp pass; else $(TEST_STATUS) zkp fail; fi
	@if cd integrity-oracle && cargo test; then $(TEST_STATUS) oracle pass; else $(TEST_STATUS) oracle fail; fi
	@if cd integrity-sdk && uv run python -m pytest; then $(TEST_STATUS) sdk pass; else $(TEST_STATUS) sdk fail; fi
	@if cd integrity-cli && uv run python -m pytest; then $(TEST_STATUS) cli pass; else $(TEST_STATUS) cli fail; fi
	@if cd bcc_middleware && uv run python -m pytest; then $(TEST_STATUS) bcc pass; else $(TEST_STATUS) bcc fail; fi
	@if cd integrity-userapi && uv run python -m pytest; then $(TEST_STATUS) userapi pass; else $(TEST_STATUS) userapi fail; fi
	@if cd integrity-dashboard && npm run build && npm run lint; then $(TEST_STATUS) dashboard pass; else $(TEST_STATUS) dashboard fail; fi
	$(TEST_STATUS) --finalize

# Real browser (Playwright) end-to-end tests — a separate, slower layer from
# `test` above, deliberately not folded into it. Playwright starts only the Vite
# frontend; the real chain/backend stack must be started separately as described
# in docs/TESTING.md.
test-e2e:
	cd integrity-dashboard && npx playwright test

# Runs integrity-dashboard/demo's real 4-persona scenario engine (agent
# registration + a live LLM-driven capital-allocation tool-call loop) --
# was previously referenced by README/CLAUDE.md/docs/TESTING.md with no
# actual Makefile target to back it. Against LIVE Base Sepolia by default
# (whatever RPC_URL/CHAIN_ID/DEPLOYMENTS_FILE are set to, normally the root
# .env's Base Sepolia values) -- real transactions, real gas. Needs
# FUNDER_PRIVATE_KEY (funds each new agent wallet -- see FAUCET_INFO.md if
# it's running low) and INTEGRITY_WALLET_PASSWORD (encrypts the generated
# keystores) in the environment; the engine itself now checks the funder's
# balance up front and fails clearly if it's short, rather than partially
# registering agents and failing confusingly partway through.
# To run against a local anvil instead: `make chain` first, then
# `RPC_URL=http://localhost:8545 CHAIN_ID=31337 DEPLOYMENTS_FILE=../../deployments.local.json make demo`.
demo:
	cd integrity-dashboard/demo && uv sync && uv run integrity-demo
