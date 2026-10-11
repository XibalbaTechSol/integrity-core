"""Hot reload of the signed pack: all-or-nothing, the old pack keeps enforcing on any failure (app/pack_policy.py).

Everything runs against a REAL `opa run --server` and REAL signed packs. The two packs differ only in the reason code
their permit rule reports (BCC_POLICY_PERMIT vs BCC_POLICY_PERMIT_V2), which is exactly what a receipt records, so which
pack decided is observable on every verdict.
"""

from __future__ import annotations

import shutil
import threading

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.config import Settings
from app.pack_policy import PackPolicy, PackPolicyError
from integrity_sdk.core.packs import compile_pack

AGENT = "did:integrity:" + "ab" * 32
TOKEN = "t" * 40
INPUT = {
    "agent_id": AGENT, "intent_type": "payment", "intended_state_hash": "0x" + "11" * 32, "nonce": 1,
    "timestamp": 1730000000000, "verification_tier": 1, "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
    "span_id": "00f067aa0ba902b7", "intent_rationale": "A sufficiently long declared rationale.",
    "token_count": 0, "daily_token_spend": 0,
}


def v2(source: str) -> str:
    assert '"BCC_POLICY_PERMIT"' in source
    return source.replace('"BCC_POLICY_PERMIT"', '"BCC_POLICY_PERMIT_V2"')


@pytest.fixture()
def world(make_signed_pack, start_empty_opa, tmp_path):
    """A live pack directory currently holding pack A, plus staged signed packs: B (a different permit code), a copy of
    A, one that is valid-signed but is not Rego OPA will accept, one unsigned, and one signed by an untrusted key."""
    a_dir, a_signer = make_signed_pack()
    b_dir, b_signer = make_signed_pack(edit=v2)
    broken_dir, broken_signer = make_signed_pack(edit=lambda s: s + "\nthis is not rego {{{\n")
    unsigned_dir, _ = make_signed_pack(edit=v2, sign=False)
    untrusted_dir, _ = make_signed_pack(edit=lambda s: v2(s).replace("BCC_POLICY_PERMIT_V2", "BCC_POLICY_PERMIT_V3"))
    live = tmp_path / "live-pack"
    shutil.copytree(a_dir, live)
    # `broken` is signed by a trusted key, so it is refused at INSTALL (OPA rejects it), not at verification.
    settings = Settings(
        policy_pack_dir=str(live), trusted_pack_signers=frozenset({a_signer, b_signer, broken_signer}),
        pack_opa_url=start_empty_opa(), opa_timeout_seconds=2.0,
    )
    policy = PackPolicy.load(Settings(**{**settings.__dict__, "policy_pack_dir": a_dir, "trusted_pack_signers": frozenset({a_signer})}))

    class World:
        pass

    w = World()
    w.policy, w.settings, w.live = policy, settings, live
    w.dirs = {"a": a_dir, "b": b_dir, "broken": broken_dir, "unsigned": unsigned_dir, "untrusted": untrusted_dir}
    w.hash = {name: _hash(path) for name, path in w.dirs.items() if name in ("a", "b")}
    return w


def _hash(directory: str) -> str:
    return compile_pack(directory).pack_hash


def stage(world, name: str) -> None:
    """Make the live directory hold the named staged pack."""
    shutil.rmtree(world.live)
    shutil.copytree(world.dirs[name], world.live)


def verdict_code(policy: PackPolicy) -> str:
    return policy.decide_sync(INPUT).reason_code


# -------------------------------------------------------------------------------- the happy path


def test_reload_swaps_the_pack_and_decisions_follow(world):
    assert verdict_code(world.policy) == "BCC_POLICY_PERMIT"
    stage(world, "b")
    result = world.policy.reload(world.settings, expected_pack_hash=world.hash["b"])
    assert (result.changed, result.previous_hash, result.pack_hash) == (True, world.hash["a"], world.hash["b"])
    assert world.policy.pack_hash == world.hash["b"] and verdict_code(world.policy) == "BCC_POLICY_PERMIT_V2"
    assert world.policy.health()["reloads"] == 1 and world.policy.health()["last_reload"]["to"] == world.hash["b"]


def test_reloading_the_pack_already_running_is_a_no_op(world, monkeypatch):
    installs = []
    real = world.policy._client.install
    monkeypatch.setattr(world.policy._client, "install", lambda pack: (installs.append(pack.pack_hash), real(pack))[1])
    stage(world, "a")
    result = world.policy.reload(world.settings, expected_pack_hash=world.hash["a"])
    assert result.changed is False and installs == [] and world.policy.reloads == 0


def test_reload_can_go_back_to_the_previous_pack(world):
    stage(world, "b")
    world.policy.reload(world.settings, expected_pack_hash=world.hash["b"])
    stage(world, "a")
    world.policy.reload(world.settings, expected_pack_hash=world.hash["a"])
    assert verdict_code(world.policy) == "BCC_POLICY_PERMIT" and world.policy.reloads == 2


# ------------------------------------------------------------------- every failure keeps the old pack


def _assert_old_pack_still_enforces(world):
    assert world.policy.pack_hash == world.hash["a"]
    assert verdict_code(world.policy) == "BCC_POLICY_PERMIT"
    assert world.policy.reloads == 0


def test_a_wrong_expected_hash_is_refused_before_anything_is_touched(world, monkeypatch):
    installs = []
    real = world.policy._client.install
    monkeypatch.setattr(world.policy._client, "install", lambda pack: (installs.append(1), real(pack))[1])
    stage(world, "b")
    with pytest.raises(PackPolicyError, match="failed verification"):
        world.policy.reload(world.settings, expected_pack_hash=world.hash["a"])  # the operator named the OLD hash
    assert installs == []
    _assert_old_pack_still_enforces(world)


def test_a_missing_expected_hash_is_refused(world):
    stage(world, "b")
    with pytest.raises(PackPolicyError, match="expected_pack_hash is required"):
        world.policy.reload(world.settings, expected_pack_hash="")
    _assert_old_pack_still_enforces(world)


@pytest.mark.parametrize("name", ["unsigned", "untrusted"])
def test_an_unsigned_or_untrusted_candidate_is_refused(world, name):
    stage(world, name)
    with pytest.raises(PackPolicyError, match="failed verification"):
        world.policy.reload(world.settings, expected_pack_hash=_hash(world.dirs[name]))
    _assert_old_pack_still_enforces(world)


def test_a_candidate_edited_after_signing_is_refused(world):
    stage(world, "b")
    policy_file = world.live / "policy.rego"
    policy_file.write_text(policy_file.read_text() + "\n# tampered after signing\n")
    with pytest.raises(PackPolicyError, match="failed verification"):
        world.policy.reload(world.settings, expected_pack_hash=world.hash["b"])
    _assert_old_pack_still_enforces(world)


def test_a_candidate_opa_rejects_restores_the_previous_pack(world):
    """Validly signed by a trusted key, but not Rego OPA accepts: the install fails AFTER verification. The old pack must be
    put back, because OpaClient.install clears its installed state before it tries."""
    stage(world, "broken")
    with pytest.raises(PackPolicyError, match="previous pack .* kept"):
        world.policy.reload(world.settings, expected_pack_hash=_hash(world.dirs["broken"]))
    _assert_old_pack_still_enforces(world)


def test_when_even_the_restore_fails_every_decision_denies(world):
    """The pack's OPA goes away during the swap, so neither the install nor the restore can succeed. The REAL install path
    clears the client's installed state first, so nothing may be allowed afterwards -- not even by the old pack."""
    stage(world, "b")
    client = world.policy._client
    live_url = client._base
    client._base = "http://127.0.0.1:1"  # nothing listens here
    try:
        with pytest.raises(PackPolicyError, match="could not be restored"):
            world.policy.reload(world.settings, expected_pack_hash=world.hash["b"])
    finally:
        client._base = live_url
    with pytest.raises(PackPolicyError):  # fail closed: PACK_NOT_INSTALLED, never an allow
        world.policy.decide_sync(INPUT)
    # ...and a later reload with OPA back heals it.
    result = world.policy.reload(world.settings, expected_pack_hash=world.hash["b"])
    assert result.changed and verdict_code(world.policy) == "BCC_POLICY_PERMIT_V2"


def test_a_decision_fails_closed_when_a_swap_takes_too_long(world, monkeypatch):
    """Decisions wait for an in-progress swap, but only for SWAP_WAIT_SECONDS: past that they deny rather than query a
    half-swapped OPA or hang the request."""
    import app.pack_policy as module

    monkeypatch.setattr(module, "SWAP_WAIT_SECONDS", 0.05)
    world.policy._swap_ready.clear()  # a swap that never finishes
    try:
        with pytest.raises(PackPolicyError, match="taking too long"):
            world.policy.decide_sync(INPUT)
    finally:
        world.policy._swap_ready.set()
    assert verdict_code(world.policy) == "BCC_POLICY_PERMIT"


def test_a_decision_waits_for_a_short_swap_instead_of_denying(world):
    world.policy._swap_ready.clear()
    timer = threading.Timer(0.2, world.policy._swap_ready.set)
    timer.start()
    assert verdict_code(world.policy) == "BCC_POLICY_PERMIT"  # waited ~0.2s, then decided normally
    timer.join()


def test_a_reload_in_progress_refuses_a_second(world):
    assert world.policy._reload_lock.acquire(blocking=False)
    try:
        with pytest.raises(PackPolicyError, match="already in progress"):
            world.policy.reload(world.settings, expected_pack_hash=world.hash["b"])
    finally:
        world.policy._reload_lock.release()


def test_the_reinstall_after_opa_forgets_never_undoes_a_reload(world):
    """A decision that began on the OLD pack and then sees OPA 'forget' it must not re-install the old pack over the new one."""
    old_pack = world.policy._pack
    stage(world, "b")
    world.policy.reload(world.settings, expected_pack_hash=world.hash["b"])
    assert world.policy._reinstall_if_forgotten(old_pack) is False
    assert verdict_code(world.policy) == "BCC_POLICY_PERMIT_V2"


# ------------------------------------------------------------------------------------- concurrency


def test_decisions_during_reloads_are_never_from_a_mixed_or_wrong_pack(world):
    """Hammer decisions from several threads while the pack flips A<->B. Every outcome must be a clean A allow, a clean B
    allow, or a fail-closed PackPolicyError for a decision caught in the swap -- never an allow with some other code."""
    outcomes: list[str] = []
    errors: list[BaseException] = []
    stop = threading.Event()

    def hammer():
        while not stop.is_set():
            try:
                outcomes.append(world.policy.decide_sync(INPUT).reason_code)
            except PackPolicyError:
                outcomes.append("FAIL_CLOSED")
            except BaseException as exc:  # pragma: no cover - the failure being tested for
                errors.append(exc)
                return

    threads = [threading.Thread(target=hammer) for _ in range(4)]
    [t.start() for t in threads]
    try:
        for index in range(12):
            name = "b" if index % 2 == 0 else "a"
            stage(world, name)
            world.policy.reload(world.settings, expected_pack_hash=world.hash[name])
    finally:
        stop.set()
        [t.join() for t in threads]
    assert not errors, errors
    assert set(outcomes) <= {"BCC_POLICY_PERMIT", "BCC_POLICY_PERMIT_V2", "FAIL_CLOSED"}, set(outcomes)
    assert "BCC_POLICY_PERMIT_V2" in outcomes and "BCC_POLICY_PERMIT" in outcomes
    assert world.policy.reloads == 12


# ------------------------------------------------------------------------------------------ endpoint


@pytest.fixture()
def client(world, monkeypatch):
    settings = Settings(**{**world.settings.__dict__, "admin_token": TOKEN})
    monkeypatch.setattr(main_module, "default_settings", settings)
    monkeypatch.setattr(main_module, "pack_policy", world.policy)
    world.settings = settings
    return TestClient(main_module.app)


RELOAD = "/v1/admin/policy-pack/reload"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def test_the_endpoint_requires_the_admin_token(client, world):
    stage(world, "b")
    assert client.post(RELOAD, json={"expected_pack_hash": world.hash["b"]}).status_code == 401
    assert world.policy.pack_hash == world.hash["a"]


def test_the_endpoint_reloads_and_health_reports_it(client, world):
    stage(world, "b")
    response = client.post(RELOAD, json={"expected_pack_hash": world.hash["b"]}, headers=AUTH)
    assert response.status_code == 200
    body = response.json()
    assert (body["changed"], body["previous_hash"], body["pack_hash"]) == (True, world.hash["a"], world.hash["b"])
    health = client.get("/health").json()["policy"]["pack"]
    assert health["hash"] == world.hash["b"] and health["reloads"] == 1


def test_the_endpoint_refuses_a_bad_reload_with_409_and_keeps_the_old_pack(client, world):
    stage(world, "b")
    response = client.post(RELOAD, json={"expected_pack_hash": world.hash["a"]}, headers=AUTH)
    assert response.status_code == 409 and "failed verification" in response.json()["detail"]
    assert client.get("/health").json()["policy"]["pack"]["hash"] == world.hash["a"]


def test_the_endpoint_rejects_a_missing_hash(client):
    assert client.post(RELOAD, json={}, headers=AUTH).status_code == 422
    assert client.post(RELOAD, json={"expected_pack_hash": ""}, headers=AUTH).status_code == 422


def test_the_endpoint_is_409_when_no_pack_is_loaded(monkeypatch):
    monkeypatch.setattr(main_module, "default_settings", Settings(admin_token=TOKEN))
    monkeypatch.setattr(main_module, "pack_policy", None)
    response = TestClient(main_module.app).post(RELOAD, json={"expected_pack_hash": "sha256:" + "00" * 32}, headers=AUTH)
    assert response.status_code == 409 and "no policy pack is loaded" in response.json()["detail"]
