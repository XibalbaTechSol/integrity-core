.PHONY: setup chain chain-reset up down test test-e2e sync-abis demo check-deploy

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
# happened, never that it was sound. `|| true` on the recorder only: a recording failure must
# never mask a real test failure, and `set -e` semantics on the suite itself are preserved.
TEST_STATUS := python3 scripts/record_test_status.py

test:
	cd contracts && forge test && cd .. && $(TEST_STATUS) contracts pass || $(TEST_STATUS) contracts fail
	cd integrity-zkp && nargo test && cd .. && $(TEST_STATUS) zkp pass || $(TEST_STATUS) zkp fail
	cd integrity-oracle && cargo test && cd .. && $(TEST_STATUS) oracle pass || $(TEST_STATUS) oracle fail
	cd integrity-sdk && uv run pytest && cd .. && $(TEST_STATUS) sdk pass || $(TEST_STATUS) sdk fail
	cd integrity-cli && uv run pytest && cd .. && $(TEST_STATUS) cli pass || $(TEST_STATUS) cli fail
	cd bcc_middleware && uv run pytest && cd .. && $(TEST_STATUS) bcc pass || $(TEST_STATUS) bcc fail
	cd integrity-userapi && uv run pytest && cd .. && $(TEST_STATUS) userapi pass || $(TEST_STATUS) userapi fail
	cd integrity-dashboard && npm test && cd .. && $(TEST_STATUS) dashboard pass || $(TEST_STATUS) dashboard fail
	$(TEST_STATUS) --finalize

# Real browser (Playwright) end-to-end tests — a separate, slower layer from
# `test` above, deliberately not folded into it. Boots its own real anvil +
# genesis deploy + ephemeral Postgres/Redis + integrity-oracle + one real
# seeded agent (see integrity-dashboard/e2e/global-setup.ts), then drives a real
# chromium browser against the real running integrity-dashboard app. See
# docs/TESTING.md for the full test-pyramid rationale and what's covered.
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

