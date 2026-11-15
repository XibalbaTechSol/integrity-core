"""XNS helpers live in the SDK (one chain layer; the CLI re-exports them).

Every XNS write is routed through the caller's own `SovereignAgent.execute`, because XNS gates on
the registered agent CONTRACT, never the controller EOA.
"""

from __future__ import annotations

from unittest import mock

from eth_utils import keccak
from web3 import Web3

from integrity_sdk import chain

XNS = "0x00000000000000000000000000000000000000aa"
AGENT = "0x00000000000000000000000000000000000000bb"


def _calldata(sig: str, handle: str) -> bytes:
    w3 = Web3()
    return bytes.fromhex(chain._contract(w3, "XibalbaNameService", address=XNS).encode_abi(sig, args=[handle])[2:])


def test_writes_route_through_execute_via_agent_with_the_xns_calldata():
    w3, controller = Web3(), mock.Mock()  # no provider: calldata encodes offline
    cases = [
        (chain.xns_register, "register"),
        (chain.xns_set_primary_handle, "setPrimaryHandle"),
        (chain.xns_release, "release"),
    ]
    for fn, sig in cases:
        with mock.patch.object(chain, "execute_via_agent", return_value={"status": 1}) as ex:
            assert fn(w3, controller, AGENT, XNS, "atlas", 31337) == {"status": 1}
        ex.assert_called_once()
        args = ex.call_args.args
        assert args[0] is w3 and args[1] is controller and args[2] == AGENT
        assert args[3].lower() == XNS
        assert args[4] == _calldata(sig, "atlas")
        assert args[4][:4] == keccak(text=f"{sig}(string)")[:4]
        assert args[5] == 31337


def test_resolve_returns_none_on_revert():
    w3 = mock.Mock()
    with mock.patch.object(chain, "_contract") as c:
        c.return_value.functions.resolve.return_value.call.side_effect = ValueError("HandleNotFound")
        assert chain.xns_resolve(w3, XNS, "nope") is None
        c.return_value.functions.resolve.return_value.call.side_effect = None
        c.return_value.functions.resolve.return_value.call.return_value = AGENT
        assert chain.xns_resolve(w3, XNS, "atlas") == AGENT
