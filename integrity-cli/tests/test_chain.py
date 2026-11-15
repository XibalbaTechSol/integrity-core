"""
Real, end-to-end test of the chain calls the CLI makes, against a live anvil running the real
`contracts/script/Deploy.s.sol` -- no mocked web3.

Since registration v3 (decision D4) the CLI's deploy/XNS helpers are re-exports of
integrity_sdk.chain; this proves the CLI's wiring of them against a v3-bound agent. The old
seven-primitives `test_cli_chain_full_registration` was deleted with that path in PR 3.4.

Mirrors integrity-sdk/tests/test_chain.py's harness. Opt-in via anvil/forge
being present; if they're not, the test skips with a note rather than
failing a bare `pytest` run.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

import pytest
from eth_account import Account
from eth_utils import keccak
from web3 import Web3

from integrity_cli import chain, wallet

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_DIR = REPO_ROOT / "contracts"
ANVIL_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
GENERAL_DOMAIN_ID = keccak(text="general.integrity")

pytestmark = pytest.mark.skipif(
    shutil.which("anvil") is None or shutil.which("forge") is None,
    reason="anvil/forge (foundry) required for the on-chain integration test",
)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def deployed_chain():
    port = _free_port()
    rpc_url = f"http://127.0.0.1:{port}"

    # Ensure foundry.toml fs_permissions don't block the genesis script
    deployments_file = CONTRACTS_DIR.parent / "deployments.local.json"
    deployments_file.touch(exist_ok=True)

    proc = subprocess.Popen(["anvil", "--port", str(port), "--silent"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        w3 = Web3(Web3.HTTPProvider(rpc_url))
        for _ in range(50):
            try:
                if w3.is_connected():
                    break
            except Exception:
                pass
            time.sleep(0.2)
        else:
            raise RuntimeError("anvil did not become reachable")

        (CONTRACTS_DIR.parent / "deployments.local.json").touch(exist_ok=True)

        result = subprocess.run(
            ["forge", "script", "script/Deploy.s.sol", "--rpc-url", rpc_url, "--broadcast"],
            cwd=CONTRACTS_DIR,
            capture_output=True,
            text=True,
            env={**os.environ, "FUNDER_PRIVATE_KEY": ANVIL_KEY},
        )
        if result.returncode != 0:
            raise RuntimeError(f"Deploy.s.sol failed:\n{result.stdout}\n{result.stderr}")

        broadcast = json.loads((CONTRACTS_DIR / "broadcast/Deploy.s.sol/31337/run-latest.json").read_text())
        addresses = {
            tx["contractName"]: Web3.to_checksum_address(tx["contractAddress"])
            for tx in broadcast["transactions"]
            if tx.get("transactionType") == "CREATE"
        }
        yield {"rpc_url": rpc_url, "chain_id": w3.eth.chain_id, "w3": w3, "funder": Account.from_key(ANVIL_KEY), "addresses": addresses}
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def _bind_v3(w3, chain_id, funder, controller, registry_address, did):
    """Deploys a canonical SovereignAgent for the v3 AgentRegistry and binds it as an actor.

    The attester is the deployer on anvil (`ATTESTER_ADDRESS` defaults to it locally); the agent
    consents via EIP-1271 with its controller's signature. Both sign raw EIP-712 digests.
    """
    zero = "0x0000000000000000000000000000000000000000"
    sovereign_agent = chain.deploy_sovereign_agent(w3, controller, did, zero, chain_id, registry_address)
    registry = chain._contract(w3, "AgentRegistry", address=registry_address)
    pubkey = os.urandom(32)
    deadline = w3.eth.get_block("latest")["timestamp"] + 3600
    proof = funder.unsafe_sign_hash(
        registry.functions.registerDigest(pubkey, controller.address, sovereign_agent, GENERAL_DOMAIN_ID, "", deadline).call()
    ).signature
    consent = controller.unsafe_sign_hash(
        registry.functions.bindActorDigest(hashlib.sha256(pubkey).digest(), sovereign_agent, deadline).call()
    ).signature
    tx = registry.functions.register(
        pubkey, controller.address, sovereign_agent, GENERAL_DOMAIN_ID, "", deadline, 1, proof, consent
    ).build_transaction({"from": funder.address, "nonce": w3.eth.get_transaction_count(funder.address), "chainId": chain_id})
    receipt = w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(funder.sign_transaction(tx).raw_transaction))
    assert receipt.status == 1
    assert registry.functions.isRegisteredAgent(sovereign_agent).call()
    return sovereign_agent


def test_cli_chain_xns_lifecycle_for_a_v3_bound_agent(deployed_chain, tmp_path, monkeypatch):
    """XNS reads the v3 AgentRegistry (registration v3 Phase 3): only a bound actor may hold handles."""
    monkeypatch.setenv("INTEGRITY_WALLET_HOME", str(tmp_path / "wallets-v3"))
    monkeypatch.setenv("INTEGRITY_WALLET_PASSWORD", "cli-chain-test-pw")

    w3 = deployed_chain["w3"]
    chain_id = deployed_chain["chain_id"]
    funder = deployed_chain["funder"]
    addr = deployed_chain["addresses"]

    agent = wallet.generate_or_load_evm_wallet("cli-test-agent")
    chain.fund_agent_wallet(w3, funder, agent.address, Web3.to_wei(1, "ether"), chain_id)
    sovereign_agent = _bind_v3(w3, chain_id, funder, agent, addr["AgentRegistry"], "did:integrity:cli-test-agent")

    # --- XNS, real end-to-end against the bound agent above ---
    # All three writes route through SovereignAgent.execute, signed by the
    # controller `agent` EOA -- NOT a direct call to XNS with the EOA as
    # signer, which is what an earlier version of this test (and of
    # chain.py's xns_* functions) incorrectly did, and which this real
    # end-to-end test is what actually caught: XNS checks
    # isRegisteredAgent(msg.sender), and the registry only knows the
    # SovereignAgent *contract* address, never the controller EOA.
    xns_address = addr["XibalbaNameService"]
    chain.xns_register(w3, agent, sovereign_agent, xns_address, "cli-test-agent.integrity", chain_id)
    assert chain.xns_resolve(w3, xns_address, "cli-test-agent.integrity") == sovereign_agent
    assert chain.xns_primary_handle(w3, xns_address, sovereign_agent) == "cli-test-agent.integrity"

    chain.xns_register(w3, agent, sovereign_agent, xns_address, "cli-test-agent-alt.integrity", chain_id)
    chain.xns_set_primary_handle(w3, agent, sovereign_agent, xns_address, "cli-test-agent-alt.integrity", chain_id)
    assert chain.xns_primary_handle(w3, xns_address, sovereign_agent) == "cli-test-agent-alt.integrity"

    chain.xns_release(w3, agent, sovereign_agent, xns_address, "cli-test-agent-alt.integrity", chain_id)
    assert chain.xns_resolve(w3, xns_address, "cli-test-agent-alt.integrity") is None



def test_cli_chain_xns_register_fails_for_unregistered_agent(deployed_chain, tmp_path, monkeypatch):
    monkeypatch.setenv("INTEGRITY_WALLET_HOME", str(tmp_path / "wallets-unregistered"))
    monkeypatch.setenv("INTEGRITY_WALLET_PASSWORD", "cli-chain-test-pw")

    w3 = deployed_chain["w3"]
    chain_id = deployed_chain["chain_id"]
    funder = deployed_chain["funder"]
    addr = deployed_chain["addresses"]

    # A funded wallet that deploys its OWN SovereignAgent (so it has a real
    # contract to route execute() through -- a bare EOA can't call execute()
    # at all, that's a different failure mode) but never completes
    # an AgentRegistry bind, so XNS (which reads the v3 AgentRegistry) does not see it. XNS's own
    # isRegisteredAgent(msg.sender) check must reject it, mirroring
    # XibalbaNameServiceTest.test_unregisteredCallerCannotClaimAHandle in
    # contracts/test/, but proven here against the real deployed contract
    # rather than a Foundry unit-test fixture, and specifically isolating
    # "not indexed in the registry" from "has no SovereignAgent at all".
    oracle_signer = funder.address
    stranger = wallet.generate_or_load_evm_wallet("cli-test-stranger")
    chain.fund_agent_wallet(w3, funder, stranger.address, Web3.to_wei(1, "ether"), chain_id)
    unregistered_sovereign_agent = chain.deploy_sovereign_agent(
        w3, stranger, "did:integrity:cli-test-stranger", oracle_signer, chain_id, addr["AgentRegistry"]
    )

    with pytest.raises(Exception):
        chain.xns_register(
            w3, stranger, unregistered_sovereign_agent, addr["XibalbaNameService"], "squatter.integrity", chain_id
        )
