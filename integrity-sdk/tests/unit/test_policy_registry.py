"""PolicyRegistry graph-root read + governance calldata (the CLI's `policy diff` / `publish`).

Publishing a root is a governance action: the SDK only builds the transaction, it never signs it.
"""

from __future__ import annotations

from unittest import mock

import pytest
from eth_utils import keccak

from integrity_sdk.policy_registry import graph_root_of, set_graph_root_tx

REGISTRY = "0x00000000000000000000000000000000000000AB"
DOMAIN = keccak(text="health")
ROOT = bytes(range(32))


def test_set_graph_root_tx_encodes_setgraphroot_and_never_signs():
    tx = set_graph_root_tx(REGISTRY, DOMAIN, ROOT, chain_id=84532)
    selector = keccak(text="setGraphRoot(bytes32,bytes32)")[:4]
    assert tx["data"] == "0x" + (selector + DOMAIN + ROOT).hex()
    assert tx["to"] == "0x00000000000000000000000000000000000000AB"
    assert tx["value"] == "0"
    assert tx["chainId"] == 84532
    assert tx["function"] == "setGraphRoot(bytes32,bytes32)"
    assert tx["args"] == {"domainId": "0x" + DOMAIN.hex(), "root": "0x" + ROOT.hex()}
    assert not {"nonce", "gas", "from", "signature", "raw"} & set(tx)


@pytest.mark.parametrize("bad", [b"\x00" * 31, b"\x00" * 33])
def test_set_graph_root_tx_rejects_non_bytes32(bad):
    with pytest.raises(ValueError):
        set_graph_root_tx(REGISTRY, bad, ROOT)
    with pytest.raises(ValueError):
        set_graph_root_tx(REGISTRY, DOMAIN, bad)


def test_graph_root_of_reads_the_public_mapping():
    w3 = mock.Mock()
    contract = w3.eth.contract.return_value
    contract.functions.graphRootOf.return_value.call.return_value = ROOT
    assert graph_root_of(w3, REGISTRY, DOMAIN) == ROOT
    contract.functions.graphRootOf.assert_called_once_with(DOMAIN)
    abi = w3.eth.contract.call_args.kwargs["abi"]
    assert [f["name"] for f in abi if f["type"] == "function"] == ["graphRootOf"]
