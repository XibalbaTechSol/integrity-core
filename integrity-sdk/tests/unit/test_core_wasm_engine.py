"""The in-process wasm engine decides exactly like a real OPA server, and fails closed.

Never a mock of OPA (see test_core_bcc_pack_equivalence): the reference is a real `opa` server running
the same signed pack. The corpus is the equivalence suite's own, so a case added there is covered here.
"""

from __future__ import annotations

import importlib.util
import shutil
import time
from pathlib import Path

import pytest

from integrity_sdk.core import decision as d
from integrity_sdk.core import packs
from integrity_sdk.core.opa import OpaClient, OpaError
from integrity_sdk.core.wasm_build import WasmBuildError, build_pack_wasm, verify_pack_wasm
from integrity_sdk.core.wasm_engine import WASM_FILE, WasmPolicyClient, _go_sprintf, _Abort
from integrity_sdk.did import Keypair, public_key_multibase

pytest.importorskip("wasmtime")
_EQ_PATH = Path(__file__).with_name("test_core_bcc_pack_equivalence.py")
_spec = importlib.util.spec_from_file_location("_bcc_pack_equivalence", _EQ_PATH)
eq = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(eq)
pytestmark = pytest.mark.skipif(eq.OPA is None, reason="opa binary not installed (scripts/install_toolchain.sh)")


def _sign_and_load(pack_dir: Path):
    signer = Keypair.generate()
    packs.sign_pack(pack_dir, signer)
    return packs.load_pack(pack_dir, trusted_signers=[public_key_multibase(signer.public_bytes())])


@pytest.fixture(scope="module")
def wasm_pack(tmp_path_factory):
    work = tmp_path_factory.mktemp("bcc-wasm-pack") / "bcc"
    shutil.copytree(eq.PACK_DIR, work)
    build_pack_wasm(work)
    return _sign_and_load(work)


@pytest.fixture(scope="module")
def wasm_client(wasm_pack):
    client = WasmPolicyClient()
    client.install(wasm_pack)
    return client


@pytest.fixture(scope="module")
def opa_client(wasm_pack):
    server = eq._Server()
    client = OpaClient(server.url)
    client.install(wasm_pack)
    yield client
    server.stop()


def _input(case: dict) -> dict:
    return {**case, "event_class": "agent.tool_call", "clinical_allowlist": [eq.EXTRA_AGENT]}


# ------------------------------------------------------------------ equivalence with real OPA


def test_wasm_and_opa_return_the_identical_raw_result_on_every_corpus_case(wasm_pack, wasm_client, opa_client):
    corpus = eq._corpus()
    assert len(corpus) > 1000, "the corpus shrank; the equivalence claim is only as strong as it is large"
    differences = []
    for case in corpus:
        want = opa_client.query(wasm_pack, _input(case))
        got = wasm_client.query(wasm_pack, _input(case))
        if want != got:
            differences.append((case, want, got))
    assert not differences, f"{len(differences)} differences, first: {differences[0]}"


def test_the_corpus_exercises_both_permit_and_deny_and_many_reason_codes(wasm_pack, wasm_client):
    seen = set()
    for case in eq._corpus():
        r = wasm_client.query(wasm_pack, _input(case))
        seen.add((r["decision"], r["reason_code"]))
    assert ("permit", "BCC_POLICY_PERMIT") in seen
    assert len({code for decision, code in seen if decision == "deny"}) >= 6


def test_decide_resolves_like_the_opa_client(wasm_pack, wasm_client, opa_client):
    for case in eq._corpus()[:300]:
        a = wasm_client.decide(wasm_pack, "agent.tool_call", _input(case))
        b = opa_client.decide(wasm_pack, "agent.tool_call", _input(case))
        assert a == b


def test_a_request_with_no_matching_event_class_denies_like_opa(wasm_pack, wasm_client, opa_client):
    inp = {"agent_id": "did:integrity:x", "intent_type": "read", "clinical_allowlist": []}
    assert wasm_client.query(wasm_pack, inp) == opa_client.query(wasm_pack, inp)
    assert wasm_client.decide(wasm_pack, "agent.tool_call", inp).decision == d.DENY


def test_evaluations_do_not_leak_state_between_calls(wasm_pack, wasm_client):
    permit = eq._build({})
    deny = eq._build({"intent_type": "SECURE_EMR_WRITE"})
    first = wasm_client.query(wasm_pack, _input(permit))
    wasm_client.query(wasm_pack, _input(deny))
    assert wasm_client.query(wasm_pack, _input(permit)) == first


def test_per_evaluation_latency_is_reported(wasm_pack, wasm_client, capsys):
    case = _input(eq._build({}))
    start = time.perf_counter()
    for _ in range(200):
        wasm_client.query(wasm_pack, case)
    per_ms = (time.perf_counter() - start) / 200 * 1000
    print(f"wasm eval: {per_ms:.2f} ms/call")
    assert per_ms < 50, "in-process evaluation should be far below a network round-trip budget"


# ---------------------------------------------------------------------------- failing closed


def test_a_pack_without_wasm_is_refused_and_every_decision_denies(tmp_path):
    work = tmp_path / "bcc"
    shutil.copytree(eq.PACK_DIR, work)
    pack = _sign_and_load(work)  # signed, verified -- but no policy.wasm
    client = WasmPolicyClient()
    with pytest.raises(OpaError) as exc:
        client.install(pack)
    assert exc.value.code == "WASM_MISSING"
    assert client.installed_pack_hash is None
    assert client.decide(pack, "agent.tool_call", _input(eq._build({}))).decision == d.DENY


def test_garbage_wasm_is_refused(tmp_path):
    work = tmp_path / "bcc"
    shutil.copytree(eq.PACK_DIR, work)
    (work / WASM_FILE).write_bytes(b"\x00asm\x01\x00\x00\x00not really")
    pack = _sign_and_load(work)
    client = WasmPolicyClient()
    with pytest.raises(OpaError) as exc:
        client.install(pack)
    assert exc.value.code == "WASM_LOAD_FAILED"
    assert client.decide(pack, "agent.tool_call", _input(eq._build({}))).decision == d.DENY


def test_querying_a_pack_that_is_not_installed_raises(wasm_pack):
    with pytest.raises(OpaError) as exc:
        WasmPolicyClient().query(wasm_pack, _input(eq._build({})))
    assert exc.value.code == "PACK_NOT_INSTALLED"


def test_a_failed_reinstall_leaves_nothing_installed(wasm_pack, tmp_path):
    client = WasmPolicyClient()
    client.install(wasm_pack)
    bad = tmp_path / "bcc"
    shutil.copytree(eq.PACK_DIR, bad)
    with pytest.raises(OpaError):
        client.install(_sign_and_load(bad))
    assert client.installed_pack_hash is None
    assert client.decide(wasm_pack, "agent.tool_call", _input(eq._build({}))).decision == d.DENY


def test_a_policy_needing_an_unimplemented_builtin_is_refused_not_approximated(tmp_path):
    work = tmp_path / "p"
    work.mkdir()
    (work / "pack.yaml").write_text(
        "pack_format: integrity.pack/1\nname: t\nversion: 0.1.0\nkernel_range: '>=1.0.0 <2.0.0'\n"
        "decision_contract: integrity.decision/1\nentrypoint: data.t.decision\n"
        "event_classes:\n  agent.tool_call: {no_match: deny}\n"
    )
    (work / "policy.rego").write_text(
        'package t\nimport rego.v1\ndecision := {"decision":"permit","reason_code":"X","controls":[]} if '
        'crypto.sha256(input.s) == input.want\n'
    )
    build_pack_wasm(work)
    pack = _sign_and_load(work)
    client = WasmPolicyClient()
    with pytest.raises(OpaError) as exc:
        client.install(pack)
    assert exc.value.code == "WASM_UNSUPPORTED_BUILTIN"
    assert "crypto.sha256" in str(exc.value)
    assert client.installed_pack_hash is None


def test_unsupported_sprintf_forms_abort_instead_of_guessing():
    for fmt, args in [("%v", [1.5]), ("%v", [True]), ("%v", [["a"]]), ("%x", [1]), ("%v", []), ("%v", ["a", "b"]), ("%", [])]:
        with pytest.raises(_Abort):
            _go_sprintf(fmt, args)
    assert _go_sprintf("%v:", ["prefix"]) == "prefix:"
    assert _go_sprintf("%d%%", [7]) == "7%"
    assert _go_sprintf("%s-%v", ["a", 3]) == "a-3"


# ----------------------------------------------------------------------- the wasm is audited


def test_verify_pack_wasm_accepts_the_real_build(wasm_pack):
    assert verify_pack_wasm(wasm_pack) is True


def test_verify_pack_wasm_catches_a_signed_but_stale_wasm(tmp_path):
    """The gap signing cannot close: wasm built from rego A, rego edited to B, then BOTH signed."""
    work = tmp_path / "bcc"
    shutil.copytree(eq.PACK_DIR, work)
    build_pack_wasm(work)
    policy = work / "policy.rego"
    policy.write_text(policy.read_text().replace("BCC_POLICY_PERMIT", "BCC_POLICY_PERMIT_EDITED"))
    stale = _sign_and_load(work)  # signature is valid; wasm no longer matches the Rego
    assert verify_pack_wasm(stale) is False


def test_verify_pack_wasm_is_false_when_no_wasm_ships(tmp_path):
    work = tmp_path / "bcc"
    shutil.copytree(eq.PACK_DIR, work)
    assert verify_pack_wasm(_sign_and_load(work)) is False


def test_building_without_rego_fails(tmp_path):
    (tmp_path / "pack.yaml").write_text("entrypoint: data.t.decision\n")
    with pytest.raises(WasmBuildError):
        build_pack_wasm(tmp_path)
