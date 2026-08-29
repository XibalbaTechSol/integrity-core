#!/usr/bin/env python3
"""
Test support: registers ONE real agent on-chain but deliberately SKIPS the genesis
memory root, producing the exact on-chain shape spec v0.3 §7.1 says the oracle must
reject (`StateAnchor.latestRoot == 0`).

Why this doesn't just call `registration.register_agent`: that flow now anchors the
genesis root itself (step 8b), by design — there is no "skip it" switch in the
production path, and adding one only so a test could produce a broken agent would put
test-shaped cruft in the real registration flow. So this script drives the same
underlying `chain.*` primitives directly, minus the anchor step.

Everything here is still the real on-chain path (real deploys, real
`registerPrimitives`) — the only difference from the sibling `register_agent.py` is the
one omitted transaction that the test is about.

Args (all via argv): rpc_url, deployments_file, agent_id
"""

import json
import os
import sys

from eth_account import Account
from eth_utils import keccak
from integrity_sdk import chain, did, wallet

FUND_WEI = 10**16  # 0.01 ETH — same order as registration.py's default agent funding.


def main() -> None:
    rpc_url = sys.argv[1]
    deployments_file = sys.argv[2]
    agent_id = sys.argv[3] if len(sys.argv) > 3 else "oracle-e2e-no-genesis"

    w3 = chain.get_w3(rpc_url)
    chain_id = w3.eth.chain_id
    deployments = chain.load_deployments(deployments_file)
    factory_address = deployments["singletons"]["AgentPrimitivesFactory"]

    agent_did, _keypair, _doc = did.load_or_create_did(agent_id)
    evm_account = wallet.generate_or_load_evm_wallet(agent_id)
    funder = Account.from_key(os.environ["FUNDER_PRIVATE_KEY"])
    oracle_signer = funder.address

    chain.fund_agent_wallet(w3, funder, evm_account.address, FUND_WEI, chain_id)
    sovereign_agent = chain.deploy_sovereign_agent(w3, evm_account, agent_did, oracle_signer, chain_id)
    state_anchor = chain.deploy_state_anchor(w3, evm_account, sovereign_agent, chain_id)
    # NO chain.anchor_genesis_root(...) here — that omission is the point of this script.
    chain.grant_anchor_role(w3, evm_account, sovereign_agent, state_anchor, oracle_signer, chain_id)

    result = chain.register_primitives(
        w3,
        evm_account,
        factory_address,
        sovereign_agent,
        state_anchor,
        agent_did,
        keccak(text="general.integrity"),
        0,
        "",
        chain_id,
    )

    print(
        json.dumps(
            {
                "did": agent_did,
                "eth_address": evm_account.address,
                "sovereign_agent": result.sovereign_agent,
                "state_anchor": result.state_anchor,
                "reputation_registry": result.reputation_registry,
                "slasher": result.slasher,
                "verifier_registry": result.verifier_registry,
                "compliance_gate": result.compliance_gate,
                "agent_profile": result.agent_profile,
            }
        )
    )


if __name__ == "__main__":
    main()
