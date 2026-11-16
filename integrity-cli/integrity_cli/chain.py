"""
Agent-side on-chain client for the CLI: funding, direct contract deployment, and
primitive registration against the Integrity Protocol contracts.

Registration v3 (decision D4): the CLI uses ONE chain layer, integrity_sdk.chain. The
deploy/XNS/domain helpers at the bottom of this module are re-exports of the SDK's. What is
still defined here is `fund_agent_wallet` (test/dev funding) and `anchor_root`, which
`vault sync` uses (decision D3). The legacy seven-primitives registration path was deleted in
registration v3 PR 3.4; `integrity register` is off-chain and gas-free.

Except `fund_agent_wallet` (explicitly the funder wallet's action), every write here
signs as the *agent's own* controller wallet (see wallet.py).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

from eth_account.signers.local import LocalAccount
from web3 import Web3
from web3.contract import Contract

_ABIS_DIR = Path(__file__).resolve().parent / "abis"


@lru_cache(maxsize=8)
def get_w3(rpc_url: str) -> Web3:
    """Cached per rpc_url: a single `agent register` invocation makes several
    transactions in sequence, and there's no reason to reopen the HTTP
    provider each time."""
    return Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))


@lru_cache(maxsize=8)
def _load_artifact(contract_name: str) -> dict:
    """Loads the trimmed {abi, bytecode} JSON synced from contracts/out/ via
    `make sync-abis` (see scripts/sync_abis.py, which writes this CLI's copy
    alongside the SDK's) -- never reads contracts/out/ directly, so this
    package stays usable without a Foundry toolchain present."""
    path = _ABIS_DIR / f"{contract_name}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"No synced ABI for {contract_name!r} at {path}. Run `make sync-abis` "
            f"from the repo root after building contracts/."
        )
    return json.loads(path.read_text())


def _contract(w3: Web3, contract_name: str, address: Optional[str] = None) -> Contract:
    artifact = _load_artifact(contract_name)
    if address is not None:
        return w3.eth.contract(address=Web3.to_checksum_address(address), abi=artifact["abi"])
    return w3.eth.contract(abi=artifact["abi"], bytecode=artifact["bytecode"])


class DeploymentsFileMissing(RuntimeError):
    pass


def load_deployments(path: str) -> dict:
    """
    Reads the genesis deployments file written by `contracts/script/Deploy.s.sol`
    (see docs/INTERFACE_CONTRACT.md §6.6 for the exact nested shape --
    `singletons` / `cloneTemplates` / `protocolAddresses` / `domains`).

    Deliberately raises rather than returning `{}` on a missing file: every
    caller of this function is about to sign and broadcast a real
    transaction that needs a real address from this file, so silently
    proceeding with an empty dict would just produce a much more confusing
    `KeyError` several lines later instead of a clear one here.
    """
    p = Path(path)
    if not p.exists():
        raise DeploymentsFileMissing(
            f"{path} does not exist -- run `forge script script/Deploy.s.sol "
            f"--broadcast` (see contracts/README.md) before registering any agent."
        )
    return json.loads(p.read_text())


def _wait(w3: Web3, tx_hash: bytes, *, action: str):
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    if receipt.status != 1:
        raise RuntimeError(f"{action} transaction reverted (tx {tx_hash.hex()})")
    return receipt


def fund_agent_wallet(w3: Web3, funder: LocalAccount, agent_address: str, amount_wei: int, chain_id: int) -> str:
    """
    Sends `amount_wei` of native ETH from the protocol's funder wallet to a
    freshly-generated agent wallet, so that wallet can sign its own
    deployment transactions (§ "Wallet & funding flow" in the interface
    contract). This is the ONE step in the whole registration sequence
    signed by a key other than the agent's own -- by construction, since a
    wallet with zero balance cannot pay for the transaction that would fund it.
    """
    tx = {
        "from": funder.address,
        "to": Web3.to_checksum_address(agent_address),
        "value": amount_wei,
        "nonce": w3.eth.get_transaction_count(funder.address),
        "chainId": chain_id,
        "gas": 21_000,
        "gasPrice": w3.eth.gas_price,
    }
    signed = funder.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    _wait(w3, tx_hash, action="fund_agent_wallet")
    return tx_hash.hex()


#: An agent with no bound actor: nothing to anchor under, so no transaction is sent and the
#: vault stays local (v2 graph deletion slice D1, owner question 8b).
NO_ACTOR = "NO_ACTOR"

_ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"


def resolve_actor(w3: Web3, agent_registry_address: str, did: str) -> Optional[str]:
    """`AgentRegistry.resolveDID(did).actor`, or None when no actor is bound."""
    registry = _contract(w3, "AgentRegistry", address=agent_registry_address)
    actor = registry.functions.resolveDID(did).call()[2]
    if not actor or actor.lower() == _ZERO_ADDRESS:
        return None
    return Web3.to_checksum_address(actor)


def root_was_anchored(w3: Web3, action_anchor_address: str, anchorer: str, root: bytes) -> bool:
    """True when `anchorer` anchored `root` on this `ActionAnchor` at any epoch.

    `ActionAnchor` stores only each anchorer's latest root, so an older one is proved by its own
    `RootAnchored(agent indexed, epoch, root)` log.
    """
    contract = _contract(w3, "ActionAnchor", address=action_anchor_address)
    who = Web3.to_checksum_address(anchorer)
    if bytes(contract.functions.latestRoot(who).call()) == bytes(root):
        return True
    logs = contract.events.RootAnchored.get_logs(from_block=0, argument_filters={"agent": who})
    return any(bytes(e["args"]["root"]) == bytes(root) for e in logs)


def anchor_root(
    w3: Web3,
    agent: LocalAccount,
    actor_address: str,
    action_anchor_address: str,
    chain_id: int,
    root: bytes,
    nonce: Optional[int] = None,
) -> str:
    """
    Anchors the agent's memory root under its actor on the shared `ActionAnchor`.

    Routed through the actor's `SovereignAgent.execute`, signed by its controller: `ActionAnchor`
    keys roots on `msg.sender`, so this is what puts the root under the actor rather than under
    the controller EOA. Used by `integrity vault sync`.
    """
    action_anchor = _contract(w3, "ActionAnchor", address=action_anchor_address)
    anchor_calldata = action_anchor.functions.anchorRoot(root).build_transaction({"gas": 0})["data"]

    sovereign_agent = _contract(w3, "SovereignAgent", address=actor_address)
    tx_nonce = nonce if nonce is not None else w3.eth.get_transaction_count(agent.address)
    tx = sovereign_agent.functions.execute(
        Web3.to_checksum_address(action_anchor_address), 0, anchor_calldata
    ).build_transaction(
        {
            "from": agent.address,
            "nonce": tx_nonce,
            "chainId": chain_id,
        }
    )
    signed = agent.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    _wait(w3, tx_hash, action="anchor_root")
    return tx_hash.hex()


# --------------------------------------------------------------------------
# One chain layer (registration v3 CLI redesign, decision D4)
# --------------------------------------------------------------------------
# These used to be byte-for-byte duplicates of integrity_sdk.chain (same ABIs, same calls), and
# had already drifted: the SDK retries reads and nonce races, this copy did not. The CLI now
# calls the SDK's versions; the names are re-exported so `chain.xns_register(...)` etc. keep
# working for main.py and tests/test_chain.py. The primitives-path helpers above stay here
# until registration v3 PR 3.4 retires that path.
from integrity_sdk.chain import (  # noqa: E402,F401
    can_join_domain,
    deploy_sovereign_agent,
    domain_exists,
    execute_via_agent,
    register_domain,
    xns_primary_handle,
    xns_register,
    xns_release,
    xns_resolve,
    xns_set_primary_handle,
)
