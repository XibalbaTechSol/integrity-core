#!/usr/bin/env python3
"""
Seeds the currently-configured chain + integrity-oracle with a handful of
REAL registered test agents (and one real market) so integrity-dashboard's UI
pages have something to render during local dev/testing, instead of
showing empty states everywhere.

This is deliberately NOT a "write fake rows into Postgres" script. Per this
repo's "no silent mocks" rule (see root CLAUDE.md), everything this script
creates is a real on-chain registration/market — the same
fund->deploy->registerPrimitives->oracle-verify sequence a real agent goes
through (via integrity_sdk.registration.register_agent), just run
repeatedly for a handful of throwaway test identities. Nothing here is
faked; it's genuinely-registered test data.

Must be run with integrity-sdk's own venv Python (this script imports
integrity_sdk as a library, it does not vendor any of its logic):

    cd integrity-sdk && uv run python ../integrity-dashboard/scripts/seed_mock_data.py

Requires MOCK=true in the environment as an explicit safety rail -- this
prevents ever accidentally running this against a shared/production
deployment by muscle memory. Also requires FUNDER_PRIVATE_KEY (the
protocol's testnet funder wallet) and INTEGRITY_WALLET_PASSWORD (gates the
new test agents' local EVM keystores), same as `agent register` in
integrity-cli / `make demo`.
"""

import os
import sys
import time

if os.getenv("MOCK") != "true":
    print(
        "Refusing to run: set MOCK=true in the environment first.\n"
        "This is a safety rail so this script can never be run against a "
        "shared/production deployment by accident.\n"
        "  MOCK=true FUNDER_PRIVATE_KEY=... INTEGRITY_WALLET_PASSWORD=... "
        "uv run python scripts/seed_mock_data.py",
        file=sys.stderr,
    )
    sys.exit(1)

try:
    from integrity_sdk import registration, wallet, markets, chain
except ImportError:
    print(
        "Could not import integrity_sdk -- run this with integrity-sdk's own "
        "venv:\n  cd integrity-sdk && uv run python "
        "../integrity-dashboard/scripts/seed_mock_data.py",
        file=sys.stderr,
    )
    sys.exit(1)

TEST_AGENTS = [
    ("mock-agent-alpha", "none"),
    ("mock-agent-beta", "none"),
    ("mock-agent-gamma", "healthcare"),
    ("mock-agent-delta", "finance"),
    ("mock-agent-epsilon", "supply-chain"),
]


def main() -> None:
    registrations = []
    for agent_id, vertical in TEST_AGENTS:
        print(f"Registering {agent_id} (vertical={vertical})...")
        try:
            reg = registration.register_agent(agent_id, compliance_vertical=vertical)
        except Exception as e:  # noqa: BLE001 -- best-effort seeding, keep going
            print(f"  failed: {e}", file=sys.stderr)
            continue
        print(f"  done: {reg.did} -> sovereign_agent={reg.sovereign_agent}")
        registrations.append((agent_id, reg))

    if not registrations:
        print("No agents registered successfully -- skipping market deploy.", file=sys.stderr)
        sys.exit(1)

    # Deploy one real market owned by the first successfully-registered agent
    # so ExchangePage/FinancePage have a real market to list.
    agent_id, reg = registrations[0]
    print(f"Deploying a test market via {agent_id}...")
    rpc_url = os.getenv("RPC_URL", "http://localhost:8545")
    deployments_file = os.getenv("DEPLOYMENTS_FILE", "../deployments.local.json")
    w3 = chain.get_w3(rpc_url)
    deployments = chain.load_deployments(deployments_file)
    controller = wallet.generate_or_load_evm_wallet(agent_id)
    try:
        market_address = markets.deploy_market(
            w3,
            controller,
            reg.sovereign_agent,
            deployments["singletons"]["MarketFactory"],
            question="[MOCK] Will this seed script's market resolve YES within a week?",
            outcome_count=2,
            min_ais_to_enter=0,
            resolve_deadline=int(time.time()) + 7 * 24 * 3600,
            resolver=deployments["protocolAddresses"]["resolverSigner"],
            chain_id=w3.eth.chain_id,
        )
        print(f"  done: market deployed at {market_address}")
    except Exception as e:  # noqa: BLE001
        print(f"  market deploy failed (agents are still seeded): {e}", file=sys.stderr)

    print(f"\nSeeded {len(registrations)}/{len(TEST_AGENTS)} test agents.")


if __name__ == "__main__":
    main()
