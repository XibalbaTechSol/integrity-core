"""Registration v3 Phase 4, PR 4.4: `integrity register --onchain [--confined --domain ID]`.

`register` stays off-chain by default. `--onchain` runs off-chain register -> attestation -> one
`AgentRegistry.register` from the guardian wallet -> Oracle sync. `--confined --domain` also
deploys a `SovereignAgent` and binds it as actor, consenting by calling `register` through its
own `execute`.

The Anvil e2e runs the real Deploy.s.sol. The Oracle is a local HTTP stand-in (`_FakeOracle`)
that does what the real PR 4.3 handlers do (proven in `integrity-oracle/backend/tests/e2e.rs`):
verify the Ed25519 signature over the contract's own `registerDigest`, attest with the
attester key (Anvil's deployer holds ATTESTER_ROLE locally), and sync by reading `resolveDID`.
"""
from __future__ import annotations

import json
import shutil
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from typer.testing import CliRunner
from web3 import Web3

from integrity_cli import chain, identity, main as main_module, status_cmd, wallet
from integrity_cli.main import app

from .test_chain import CONTRACTS_DIR, deployed_chain  # noqa: F401 -- module-scoped Anvil + Deploy.s.sol

runner = CliRunner()
needs_anvil = pytest.mark.skipif(
    shutil.which("anvil") is None or shutil.which("forge") is None,
    reason="anvil/forge (foundry) required for the on-chain e2e",
)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _boom(*_a, **_k):
    raise AssertionError("must not be touched without --onchain")


# --------------------------------------------------------------------------
# default stays off-chain; flag validation; outages (no chain needed)
# --------------------------------------------------------------------------

def test_register_without_onchain_never_touches_the_rpc_or_wallet(monkeypatch):
    assert runner.invoke(app, ["identity", "new"]).exit_code == 0
    did = identity.did_document("default")["id"]
    monkeypatch.setattr(chain, "get_w3", _boom)
    monkeypatch.setattr(status_cmd, "get_w3", _boom)
    monkeypatch.setattr(wallet, "generate_or_load_evm_wallet", _boom)

    class _Reg:
        agent_id, verification_tier, outcome, handle = did, 1, "created", None

    monkeypatch.setattr(main_module, "register_offchain", lambda *a, **k: _Reg())
    result = runner.invoke(app, ["register", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["outcome"] == "created"


@pytest.mark.parametrize("args", [["--confined", "--domain", "general.integrity"], ["--onchain", "--confined"],
                                  ["--domain", "general.integrity"]])
def test_confined_and_domain_need_onchain_and_each_other(args):
    assert runner.invoke(app, ["identity", "new"]).exit_code == 0
    result = runner.invoke(app, ["register", *args])
    assert result.exit_code == 2, result.output


def test_onchain_with_an_unreachable_oracle_exits_3(tmp_path):
    assert runner.invoke(app, ["identity", "new"]).exit_code == 0
    deployments = tmp_path / "d.json"
    deployments.write_text(json.dumps({"singletons": {"AgentRegistry": "0x" + "22" * 20}}))
    dead = f"http://127.0.0.1:{_free_port()}"
    result = runner.invoke(app, ["register", "--onchain", "--oracle-url", dead, "--rpc-url", dead,
                                 "--deployments-file", str(deployments), "--json"])
    assert result.exit_code == 3, result.output
    assert json.loads(result.stdout)["error"]["code"] == "UNREACHABLE"


def _offchain_only_oracle():
    """An Oracle that accepts off-chain registration and answers every on-chain step 503, as the
    live Oracle does while it has no AgentRegistry in its deployments file."""

    class _H(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            n = int(self.headers.get("content-length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
            if self.path == "/v1/agent/register/offchain":
                status, payload = 201, {"agent_id": body["did"], "verification_tier": 1, "outcome": "created"}
            else:
                status, payload = 503, {"error": "AgentRegistry is not in this Oracle's deployments file"}
            raw = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *_a):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), _H)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_onchain_with_an_unreachable_rpc_exits_3(tmp_path, monkeypatch):
    """The Oracle is up, the RPC is not: on-chain state can't be read, so it's "can't tell" (3)."""
    assert runner.invoke(app, ["identity", "new"]).exit_code == 0
    monkeypatch.setenv("INTEGRITY_WALLET_HOME", str(tmp_path / "wallets"))
    monkeypatch.setenv("INTEGRITY_WALLET_PASSWORD", "register-onchain-test-pw")
    deployments = tmp_path / "d.json"
    deployments.write_text(json.dumps({"singletons": {"AgentRegistry": "0x" + "22" * 20}}))
    server = _offchain_only_oracle()
    try:
        result = runner.invoke(app, [
            "register", "--onchain", "--oracle-url", f"http://127.0.0.1:{server.server_address[1]}",
            "--rpc-url", f"http://127.0.0.1:{_free_port()}", "--deployments-file", str(deployments), "--json"])
    finally:
        server.shutdown()
    assert result.exit_code == 3, result.output
    assert json.loads(result.stdout)["error"]["code"] == "UNREACHABLE"


def test_onchain_oracle_without_agent_registry_exits_3(tmp_path, monkeypatch):
    """The live Oracle's state today: off-chain works, on-chain steps 503. That is "can't tell
    right now" (3), not a refusal (1)."""
    assert runner.invoke(app, ["identity", "new"]).exit_code == 0
    monkeypatch.setenv("INTEGRITY_WALLET_HOME", str(tmp_path / "wallets"))
    monkeypatch.setenv("INTEGRITY_WALLET_PASSWORD", "register-onchain-test-pw")
    deployments = tmp_path / "d.json"
    deployments.write_text(json.dumps({"singletons": {"AgentRegistry": "0x" + "22" * 20}}))

    def oracle_503(*_a, **_k):
        raise main_module.registration_onchain.OnchainRegistrationError(
            "attestation", 503, "AgentRegistry is not in this Oracle's deployments file")

    monkeypatch.setattr(main_module.registration_onchain, "register_onchain", oracle_503)
    server = _offchain_only_oracle()
    try:
        result = runner.invoke(app, ["register", "--onchain", "--oracle-url", f"http://127.0.0.1:{server.server_address[1]}",
                                     "--deployments-file", str(deployments), "--json"])
    finally:
        server.shutdown()
    assert result.exit_code == 3, result.output
    err = json.loads(result.stdout)["error"]
    assert err["code"] == "HTTP_503" and "AgentRegistry" in err["detail"]


def test_onchain_without_an_agent_registry_is_a_definite_no(tmp_path):
    assert runner.invoke(app, ["identity", "new"]).exit_code == 0
    deployments = tmp_path / "d.json"
    deployments.write_text(json.dumps({"singletons": {}}))
    result = runner.invoke(app, ["register", "--onchain", "--deployments-file", str(deployments), "--json"])
    assert result.exit_code == 1, result.output
    assert json.loads(result.stdout)["error"]["code"] == "NO_AGENT_REGISTRY"


# --------------------------------------------------------------------------
# Anvil e2e (plan acceptance)
# --------------------------------------------------------------------------

class _FakeOracle:
    def __init__(self, w3, registry_address: str, chain_id: int, attester):
        self.w3, self.chain_id, self.attester, self.registry_address = w3, chain_id, attester, registry_address
        self.registry = chain._contract(w3, "AgentRegistry", address=registry_address)
        self.keys: dict[str, bytes] = {}

    def handle(self, method: str, path: str, body: dict) -> tuple[int, dict]:
        parts = path.strip("/").split("/")  # v1/agent/<did>[/...]
        if method == "POST" and path == "/v1/agent/register/offchain":
            self.keys[body["did"]] = bytes.fromhex(body["ed25519_pubkey_hex"])
            return 201, {"agent_id": body["did"], "verification_tier": 1, "outcome": "created"}
        did = parts[2] if len(parts) > 2 else ""
        if method == "GET" and len(parts) == 3:
            if did not in self.keys:
                return 404, {"error": "unknown agent"}
            return 200, {"id": did, "verification_tier": 1}
        if method == "POST" and path.endswith("/onchain/attestation"):
            pubkey = self.keys.get(did)
            if pubkey is None:
                return 404, {"error": "no off-chain registration"}
            dom = bytes.fromhex(body["domain_id"][2:])
            digest = self.registry.functions.registerDigest(
                pubkey, body["guardian"], body["actor"], dom, body["uri"], body["deadline"]).call()
            try:
                Ed25519PublicKey.from_public_bytes(pubkey).verify(bytes.fromhex(body["signature"]), digest)
            except InvalidSignature:
                return 401, {"error": "bad signature"}
            return 200, {
                "agent_id": did, "digest": "0x" + digest.hex(),
                "attestation": "0x" + self.attester.unsafe_sign_hash(digest).signature.hex(),
                "attester": self.attester.address, "proof_kind": 1, "chain_id": self.chain_id,
                "agent_registry": self.registry_address, "pubkey": "0x" + pubkey.hex(),
                "guardian": body["guardian"], "actor": body["actor"], "domain_id": body["domain_id"],
                "uri": body["uri"], "deadline": body["deadline"],
            }
        if method == "POST" and path.endswith("/onchain/sync"):
            rec = self.registry.functions.resolveDID(did).call()
            if not rec[5]:
                return 404, {"error": "not registered on-chain"}
            actor = None if int(rec[2], 16) == 0 else rec[2]
            return 200, {"agent_id": did, "actor": actor, "settlement_eligible": actor is not None and rec[6] == 0}
        return 404, {"error": f"no route {method} {path}"}


@pytest.fixture
def oracle(deployed_chain):  # noqa: F811 -- the imported fixture
    fake = _FakeOracle(deployed_chain["w3"], deployed_chain["addresses"]["AgentRegistry"],
                       deployed_chain["chain_id"], deployed_chain["funder"])

    class _H(BaseHTTPRequestHandler):
        def _reply(self, method: str):
            n = int(self.headers.get("content-length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}") if n else {}
            status, payload = fake.handle(method, self.path, body)
            raw = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):  # noqa: N802
            self._reply("GET")

        def do_POST(self):  # noqa: N802
            self._reply("POST")

        def log_message(self, *_a):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), _H)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture
def onchain_env(deployed_chain, oracle, tmp_path, monkeypatch):  # noqa: F811
    deployments = tmp_path / "deployments.json"
    deployments.write_text((CONTRACTS_DIR.parent / "deployments.local.json").read_text())
    assert json.loads(deployments.read_text())["singletons"]["AgentRegistry"] == \
        deployed_chain["addresses"]["AgentRegistry"]
    monkeypatch.setenv("INTEGRITY_WALLET_HOME", str(tmp_path / "wallets"))
    monkeypatch.setenv("INTEGRITY_WALLET_PASSWORD", "register-onchain-test-pw")
    flags = ["--oracle-url", oracle, "--rpc-url", deployed_chain["rpc_url"], "--deployments-file", str(deployments)]

    def new_funded_identity(name: str) -> None:
        assert runner.invoke(app, ["identity", "new", "--name", name]).exit_code == 0
        guardian = wallet.generate_or_load_evm_wallet(name)
        chain.fund_agent_wallet(deployed_chain["w3"], deployed_chain["funder"], guardian.address,
                                Web3.to_wei(1, "ether"), deployed_chain["chain_id"])

    return flags, new_funded_identity


@needs_anvil
def test_register_onchain_confined_then_status_and_onchain_handle(onchain_env):
    flags, new_funded_identity = onchain_env
    new_funded_identity("default")

    result = runner.invoke(app, ["register", "--onchain", "--confined", "--domain", "general.integrity", "--json", *flags])
    assert result.exit_code == 0, result.output
    doc = json.loads(result.stdout)
    assert doc["onchain"]["outcome"] == "registered" and doc["onchain"]["actor"]
    assert doc["onchain"]["record"]["settlement_eligible"] is True

    status = runner.invoke(app, ["status", "--json", *flags])
    assert status.exit_code == 0, status.output
    onchain = json.loads(status.stdout)["onchain"]
    assert onchain["record"]["status"] == "present"
    assert onchain["actor"]["status"] == "bound" and onchain["actor"]["actor"] == doc["onchain"]["actor"]
    assert onchain["trust"]["status"] != "unverified", onchain["trust"]

    handle = runner.invoke(app, ["handle", "register", "pr44-agent", "--onchain", "--json",
                                 "--rpc-url", flags[3], "--deployments-file", flags[5]])
    assert handle.exit_code == 0, handle.output
    assert json.loads(handle.stdout)["actor"] == doc["onchain"]["actor"]

    again = runner.invoke(app, ["register", "--onchain", "--confined", "--domain", "general.integrity", "--json", *flags])
    assert again.exit_code == 0, again.output
    assert json.loads(again.stdout)["onchain"]["outcome"] == "already_registered"


@needs_anvil
def test_register_onchain_revert_exits_4_with_the_decoded_name(onchain_env):
    flags, new_funded_identity = onchain_env
    new_funded_identity("reverter")
    result = runner.invoke(app, ["register", "--identity", "reverter", "--onchain", "--confined",
                                 "--domain", "no-such-domain.integrity", "--json", *flags])
    assert result.exit_code == 4, result.output
    err = json.loads(result.stdout)["error"]
    assert err["code"] == "REVERT" and "DomainJoinNotAllowed" in err["detail"]
