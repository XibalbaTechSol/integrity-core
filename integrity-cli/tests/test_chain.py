"""
Real, end-to-end test of integrity-cli's OWN chain.py against a live anvil
running the real `contracts/script/Deploy.s.sol` — no mocked web3, no
dependency on integrity-sdk (per identity.py's "no sibling dependency"
philosophy, the CLI carries its own copy of the on-chain logic, so it gets
its own real-chain proof rather than trusting the SDK's).

Mirrors integrity-sdk/tests/test_chain.py's harness. Opt-in via anvil/forge
being present; if they're not, the test skips with a note rather than
failing a bare `pytest` run.
"""

from __future__ import annotations

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


def test_cli_chain_full_registration(deployed_chain, tmp_path, monkeypatch):
    monkeypatch.setenv("INTEGRITY_WALLET_HOME", str(tmp_path / "wallets"))
    monkeypatch.setenv("INTEGRITY_WALLET_PASSWORD", "cli-chain-test-pw")

    w3 = deployed_chain["w3"]
    chain_id = deployed_chain["chain_id"]
    funder = deployed_chain["funder"]
    addr = deployed_chain["addresses"]

    agent = wallet.generate_or_load_evm_wallet("cli-test-agent")
    oracle_signer = funder.address  # Deploy.s.sol defaults oracleSigner to the deployer.

    chain.fund_agent_wallet(w3, funder, agent.address, Web3.to_wei(1, "ether"), chain_id)

    did = "did:integrity:cli-test-agent"
    sovereign_agent = chain.deploy_sovereign_agent(w3, agent, did, oracle_signer, chain_id)
    state_anchor = chain.deploy_state_anchor(w3, agent, sovereign_agent, chain_id)

    # Regression coverage for PRODUCTION_GAPS.md Sec3: minted to the SovereignAgent
    # CONTRACT (only deployable once we're past the two lines above), never the raw
    # EOA wallet -- IntegrityMarket/A2ACapitalPool pull ITK from msg.sender, which is
    # always the SovereignAgent address when routed through its own execute(), so ITK
    # minted to the wallet is stranded and unspendable through that path. This test
    # used to mint to `agent.address` before the SovereignAgent even existed, matching
    # the bug this reorder fixes, and asserted nothing about where the ITK actually
    # landed.
    mint_amount = Web3.to_wei(10_000, "ether")
    chain.mint_testnet_itk(w3, funder, addr["IntegrityToken"], sovereign_agent, mint_amount, chain_id)
    itk = chain._contract(w3, "IntegrityToken", address=addr["IntegrityToken"])
    assert itk.functions.balanceOf(sovereign_agent).call() == mint_amount, "testnet ITK must land on the SovereignAgent contract"
    assert itk.functions.balanceOf(agent.address).call() == 0, "the raw EOA wallet must NOT receive testnet ITK"

    chain.grant_anchor_role(w3, agent, sovereign_agent, state_anchor, oracle_signer, chain_id)

    chain.approve_factory_bond(w3, agent, sovereign_agent, addr["IntegrityToken"], addr["AgentPrimitivesFactory"], Web3.to_wei(100, "ether"), chain_id)

    result = chain.register_primitives(
        w3, agent, addr["AgentPrimitivesFactory"], sovereign_agent, state_anchor,
        did, GENERAL_DOMAIN_ID, 0, "ipfs://cli-test", chain_id,
    )

    assert result.sovereign_agent == sovereign_agent
    assert result.controller == agent.address
    zero = "0x0000000000000000000000000000000000000000"
    for a in (result.reputation_registry, result.slasher, result.verifier_registry, result.compliance_gate, result.agent_profile):
        assert a.lower() != zero

    # --- XNS, real end-to-end against the now-registered agent above ---
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
    # registerPrimitives, so XibalbaAgentRegistry never indexes it. XNS's own
    # isRegisteredAgent(msg.sender) check must reject it, mirroring
    # XibalbaNameServiceTest.test_unregisteredCallerCannotClaimAHandle in
    # contracts/test/, but proven here against the real deployed contract
    # rather than a Foundry unit-test fixture, and specifically isolating
    # "not indexed in the registry" from "has no SovereignAgent at all".
    oracle_signer = funder.address
    stranger = wallet.generate_or_load_evm_wallet("cli-test-stranger")
    chain.fund_agent_wallet(w3, funder, stranger.address, Web3.to_wei(1, "ether"), chain_id)
    unregistered_sovereign_agent = chain.deploy_sovereign_agent(
        w3, stranger, "did:integrity:cli-test-stranger", oracle_signer, chain_id
    )

    with pytest.raises(Exception):
        chain.xns_register(
            w3, stranger, unregistered_sovereign_agent, addr["XibalbaNameService"], "squatter.integrity", chain_id
        )
