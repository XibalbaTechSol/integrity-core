"""The signed pack decides exactly like bcc.rego THROUGH THE REAL PIPELINE (B2 stage 2).

`integrity-sdk/tests/unit/test_core_bcc_pack_equivalence.py` proves the two policies agree on 2,000+ raw
inputs. This file proves the property that matters at the cutover: real, validly-signed commitments sent
through `run_intercept` get the same outcome under all three configurations --

    rego         bcc.rego decides (today's behaviour, the default)
    dual-run     bcc.rego decides, the pack is evaluated beside it and compared
    pack         the signed pack decides (BCC_POLICY_ENGINE=pack)

-- including the steps AFTER policy (the BAA gate, which depends on the gate's `requires_baa` constant
standing in for the output the decision contract does not have). Every scenario also states its expected
reason code, so a bug that made all three engines agree on the wrong answer would still fail.

Also under test: the failure postures (fail closed in pack mode; dual-run can never change a response),
startup, `/health`, and the admin allowlist endpoint's behaviour in pack mode.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

import httpx
import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.config import Settings
from app.main import run_intercept
from app.pack_policy import PackPolicy, PackPolicyError
from tests.helpers import make_commitment_model, new_agent, sign_commitment

RATIONALE = "A sufficiently long declared intent rationale."
TRACE = {"trace_id": "4bf92f3577b34da6a3ce929d0e0e4736", "span_id": "00f067aa0ba902b7"}


@dataclass(frozen=True)
class Scenario:
    label: str
    intent_type: str
    tier: int = 1
    allowlisted: bool = False
    trace: bool = False
    rationale: str | None = RATIONALE
    token_count: int | None = None
    #: What must happen, in every engine. "allow", "BAA_CANNOT_VERIFY" (policy passed, on-chain check could
    #: not confirm: no deployments file in tests), or the single reason code a policy denial must carry.
    expected: str = "allow"


SCENARIOS = [
    Scenario("ordinary payment, tier 1", "payment"),
    Scenario("ordinary payment, tier 0", "payment", tier=0),
    Scenario("lowercase look-alike is not clinical", "emr_write"),
    Scenario("unlisted agent, clinical intent", "EMR_WRITE", expected="HIPAA_ACCESS_CONTROL_VIOLATION"),
    Scenario("allowlisted agent passes policy, then the BAA gate cannot verify", "EMR_WRITE", allowlisted=True,
             expected="BAA_CANNOT_VERIFY"),
    Scenario("allowlisted agent, tier 0", "SECURE_EMR_WRITE", tier=0, allowlisted=True,
             expected="VERIFICATION_TIER_INSUFFICIENT"),
    Scenario("unlisted and tier 0: access control is reported first", "DISPENSE_MEDICATION", tier=0,
             expected="HIPAA_ACCESS_CONTROL_VIOLATION"),
    Scenario("read-only agent tool with full audit fields", "claude_tool:Bash:readonly", trace=True),
    Scenario("destructive tool, tier 0", "claude_tool:Bash:destructive", tier=0, trace=True,
             expected="TOOL_RISK_TIER_INSUFFICIENT"),
    Scenario("financial tool, tier 0", "hermes_tool:coinbase_trade:financial", tier=0, trace=True,
             expected="TOOL_RISK_TIER_INSUFFICIENT"),
    Scenario("agent tool with no trace/span", "claude_tool:Bash", expected="AOS_VIOLATION"),
    Scenario("agent tool, rationale too brief", "claude_tool:Read:readonly", trace=True, rationale="too short",
             expected="AOS_VIOLATION"),
    Scenario("suspicious word AND missing audit fields: the label check is reported first",
             "claude_tool:bypass_step", expected="POLICY_VIOLATION"),
    Scenario("exfiltration reference", "EXFILTRATE_records", expected="POLICY_VIOLATION"),
    Scenario("SSN-shaped label", "note 123-45-6789", expected="HIPAA_TECHNICAL_SAFEGUARD_FAILURE"),
    Scenario("within the tier-0 token budget", "payment", tier=0, token_count=5000),
    Scenario("over the tier-0 token budget", "payment", tier=0, token_count=20000, expected="TOKEN_BUDGET_OPA"),
]


def _codes_in(reason: str) -> set[str]:
    return set(re.findall(r"(?:^|; )([A-Z][A-Z0-9_]+):", reason.split("OPA_REJECTION: ", 1)[-1]))


@pytest.fixture()
def world(real_opa_server, make_signed_pack, start_empty_opa, tmp_path, monkeypatch):
    """Both engines wired to the same allowlisted agent: bcc.rego via its OPA data document, the pack via the
    allowlist file. Returns a callable that runs one scenario under one configuration."""
    allowed_id, allowed_key = new_agent()
    httpx.put(f"{real_opa_server}/v1/data/clinical_allowlist/agents", json=[allowed_id]).raise_for_status()
    allowlist_file = tmp_path / "allow.json"
    allowlist_file.write_text(json.dumps({"agents": [allowed_id]}))

    pack_dir, signer = make_signed_pack()
    pack_opa = start_empty_opa()
    base = dict(
        opa_url=real_opa_server, merkle_batch_size=999, quarantine_fail_closed_intents=frozenset(), shadow_mode=False,
        policy_pack_dir=pack_dir, trusted_pack_signers=frozenset({signer}), pack_opa_url=pack_opa,
        clinical_allowlist_file=str(allowlist_file),
    )
    policy = PackPolicy.load(Settings(**base))
    nonces: dict[str, int] = {}
    state = {"tier": 1}
    monkeypatch.setattr(main_module, "resolve_verification_tier", lambda agent_id, oracle_url=None: state["tier"])
    monkeypatch.setattr(main_module, "default_settings", Settings(**base))

    async def run(scenario: Scenario, *, engine: str, with_pack: bool, identity=None):
        """`identity` lets several runs share one agent: the deny reason names the agent, so runs can only be
        compared byte for byte when they are about the same one."""
        if scenario.allowlisted:
            agent_id, key = allowed_id, allowed_key
        else:
            agent_id, key = identity or new_agent()
        nonces[agent_id] = nonces.get(agent_id, 0) + 1
        payload = sign_commitment(
            key, agent_id=agent_id, intent_type=scenario.intent_type, nonce=nonces[agent_id],
            intent_rationale=scenario.rationale,
        )
        if scenario.trace:
            payload.update(TRACE)
        if scenario.token_count is not None:
            payload["token_count"] = scenario.token_count
        state["tier"] = scenario.tier
        main_module.circuit_breaker.reset()
        # BCC's token budget accumulates spend per agent in process memory. Three runs by one identity would
        # otherwise add up (5000 + 5000 + 5000 > 10000) and look like an engine disagreement.
        main_module.token_budget_enforcer.reset()
        monkeypatch.setattr(main_module, "pack_policy", policy if with_pack else None)
        return await run_intercept(make_commitment_model(**payload), Settings(**{**base, "policy_engine": engine}))

    yield run, policy, base, allowlist_file
    httpx.put(f"{real_opa_server}/v1/data/clinical_allowlist/agents", json=[])


def _outcome(response) -> tuple[bool, str]:
    if response.authorized:
        return True, "allow"
    reason = response.reason
    if "OPA_REJECTION" in reason:
        return False, "OPA"
    return False, reason.split(":", 1)[0]


# ------------------------------------------------------------------ the differential


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s.label for s in SCENARIOS])
async def test_all_three_configurations_give_the_same_outcome(world, scenario):
    run, policy, _base, _file = world
    before = policy.stats.snapshot()

    who = new_agent()
    rego = await run(scenario, engine="rego", with_pack=False, identity=who)
    dual = await run(scenario, engine="rego", with_pack=True, identity=who)
    pack = await run(scenario, engine="pack", with_pack=True, identity=who)

    assert _outcome(rego) == _outcome(dual) == _outcome(pack), (rego.reason, dual.reason, pack.reason)
    assert rego.reason == dual.reason, "dual-run must not change a single byte of the response"

    if scenario.expected == "allow":
        assert rego.authorized and pack.authorized
    elif scenario.expected == "BAA_CANNOT_VERIFY":
        assert not rego.authorized and not pack.authorized
        assert rego.reason.startswith("BAA_CANNOT_VERIFY") and pack.reason.startswith("BAA_CANNOT_VERIFY")
    else:
        assert not rego.authorized and not pack.authorized
        assert scenario.expected in _codes_in(rego.reason), rego.reason
        assert scenario.expected in _codes_in(pack.reason), pack.reason
        assert _codes_in(pack.reason) <= _codes_in(rego.reason), "the pack reports one of bcc.rego's codes"

    after = policy.stats.snapshot()
    assert after["divergences"] == before["divergences"], after["last_divergence"]
    assert after["compared"] == before["compared"] + 1


# ------------------------------------------------------------ dual-run can't hurt


@pytest.mark.asyncio
async def test_a_disagreeing_pack_is_logged_and_counted_but_never_acted_on(
    real_opa_server, make_signed_pack, start_empty_opa, monkeypatch, caplog, tmp_path
):
    """A pack that disagrees (here: tier minimums removed) is exactly what dual-run exists to catch. The
    response must still be bcc.rego's, byte for byte."""
    pack_dir, signer = make_signed_pack(
        edit=lambda text: text.replace('"SECURE_EMR_WRITE": 1,', '"SECURE_EMR_WRITE": 0,').replace('"EMR_WRITE": 1,', '"EMR_WRITE": 0,')
    )
    # An agent allowlisted in BOTH engines (so only the tier rule can deny) but at tier 0.
    agent_id, key = new_agent()
    allowlist_file = tmp_path / "allow.json"
    allowlist_file.write_text(json.dumps({"agents": [agent_id]}))
    settings = Settings(
        opa_url=real_opa_server, merkle_batch_size=999, quarantine_fail_closed_intents=frozenset(), shadow_mode=False,
        policy_pack_dir=pack_dir, trusted_pack_signers=frozenset({signer}), pack_opa_url=start_empty_opa(),
        clinical_allowlist_file=str(allowlist_file),
    )
    policy = PackPolicy.load(settings)
    monkeypatch.setattr(main_module, "pack_policy", policy)
    monkeypatch.setattr(main_module, "resolve_verification_tier", lambda agent_id, oracle_url=None: 0)
    httpx.put(f"{real_opa_server}/v1/data/clinical_allowlist/agents", json=[agent_id]).raise_for_status()
    try:
        payload = sign_commitment(key, agent_id=agent_id, intent_type="SECURE_EMR_WRITE", nonce=1, intent_rationale=RATIONALE)
        main_module.circuit_breaker.reset()
        with caplog.at_level(logging.WARNING, logger="app.main"):
            response = await run_intercept(make_commitment_model(**payload), settings)
    finally:
        httpx.put(f"{real_opa_server}/v1/data/clinical_allowlist/agents", json=[])

    assert response.authorized is False and "VERIFICATION_TIER_INSUFFICIENT" in response.reason, "bcc.rego decided"
    stats = policy.stats.snapshot()
    assert stats["compared"] == 1 and stats["divergences"] == 1
    assert "verdict" in stats["last_divergence"]
    assert "POLICY DIVERGENCE" in caplog.text


@pytest.mark.asyncio
async def test_a_failing_pack_cannot_change_the_dual_run_response(world):
    run, policy, _base, _file = world
    healthy = await run(SCENARIOS[0], engine="rego", with_pack=False)
    policy._client._base = "http://127.0.0.1:9"  # the pack's OPA is down; bcc.rego's is fine
    degraded = await run(SCENARIOS[0], engine="rego", with_pack=True)
    assert degraded.authorized is True and _outcome(degraded) == _outcome(healthy)
    assert policy.stats.snapshot()["pack_errors"] == 1


# ------------------------------------------------------------ pack mode fails closed


@pytest.mark.asyncio
async def test_pack_mode_denies_when_the_packs_opa_is_down_and_does_not_trip_the_breaker(world):
    run, policy, _base, _file = world
    policy._client._base = "http://127.0.0.1:9"
    who = new_agent()
    response = await run(SCENARIOS[0], engine="pack", with_pack=True, identity=who)
    assert response.authorized is False
    assert response.reason.startswith("BCC_POLICY_ENGINE_UNAVAILABLE")
    # Infrastructure failure is not the agent's violation: no violation is recorded, so an outage can never
    # lock out well-behaved agents.
    assert main_module.circuit_breaker._agents.get(who[0]) is None


@pytest.mark.asyncio
async def test_pack_mode_without_a_loaded_pack_denies(world):
    run, _policy, _base, _file = world
    response = await run(SCENARIOS[0], engine="pack", with_pack=False)
    assert response.authorized is False and response.reason.startswith("BCC_POLICY_ENGINE_UNAVAILABLE")


@pytest.mark.asyncio
async def test_revoking_an_agent_in_the_file_takes_effect_on_the_next_request(world):
    run, _policy, _base, allowlist_file = world
    scenario = Scenario("allowlisted", "EMR_WRITE", allowlisted=True, expected="BAA_CANNOT_VERIFY")
    assert (await run(scenario, engine="pack", with_pack=True)).reason.startswith("BAA_CANNOT_VERIFY")
    allowlist_file.write_text(json.dumps({"agents": []}))
    revoked = await run(scenario, engine="pack", with_pack=True)
    assert revoked.authorized is False and "HIPAA_ACCESS_CONTROL_VIOLATION" in revoked.reason


# --------------------------------------------------------------------------- startup


@pytest.mark.asyncio
async def test_pack_mode_refuses_to_start_when_the_pack_does_not_verify(make_signed_pack, start_empty_opa, monkeypatch):
    pack_dir, signer = make_signed_pack(tamper_after=lambda text: text + "\n# edited after signing\n")
    settings = Settings(policy_engine="pack", policy_pack_dir=pack_dir, trusted_pack_signers=frozenset({signer}),
                        pack_opa_url=start_empty_opa())
    monkeypatch.setattr(main_module, "pack_policy", None)
    with pytest.raises(PackPolicyError, match="failed verification"):
        await main_module._init_pack_policy(settings)


@pytest.mark.asyncio
async def test_dual_run_starts_without_a_bad_pack_and_says_so(make_signed_pack, start_empty_opa, monkeypatch, caplog):
    pack_dir, signer = make_signed_pack(tamper_after=lambda text: text + "\n# edited after signing\n")
    settings = Settings(policy_pack_dir=pack_dir, trusted_pack_signers=frozenset({signer}), pack_opa_url=start_empty_opa())
    with caplog.at_level(logging.ERROR, logger="app.main"):
        await main_module._init_pack_policy(settings)
    assert main_module.pack_policy is None
    assert "failed verification" in main_module.pack_policy_error
    assert "dual-run disabled" in caplog.text


@pytest.mark.asyncio
async def test_nothing_is_loaded_when_nothing_is_configured():
    await main_module._init_pack_policy(Settings())
    assert main_module.pack_policy is None and main_module.pack_policy_error is None


def test_an_unknown_engine_is_a_configuration_error():
    with pytest.raises(ValueError, match="BCC_POLICY_ENGINE"):
        Settings(policy_engine="both")


# ------------------------------------------------------- health and the admin endpoint


def test_health_reports_the_engine_and_the_loaded_pack(world, monkeypatch):
    _run, policy, base, _file = world
    monkeypatch.setattr(main_module, "default_settings", Settings(**{**base, "policy_engine": "pack"}))
    monkeypatch.setattr(main_module, "pack_policy", policy)
    body = TestClient(main_module.app).get("/health").json()
    assert body["policy"]["engine"] == "pack"
    assert body["policy"]["pack"]["name"] == "bcc" and body["policy"]["pack"]["hash"] == policy.pack_hash
    assert body["policy"]["pack"]["allowlist"]["ok"] is True


def test_health_without_a_pack_still_reports_the_engine(monkeypatch):
    monkeypatch.setattr(main_module, "pack_policy", None)
    monkeypatch.setattr(main_module, "default_settings", Settings())
    body = TestClient(main_module.app).get("/health").json()
    assert body["policy"] == {"engine": "rego", "pack": None, "pack_error": None}


def test_the_admin_allowlist_write_is_refused_in_pack_mode_and_reads_the_file(world, monkeypatch):
    """In pack mode this endpoint would otherwise be a silent no-op (the pack reads the file, not OPA's data
    document) -- or, if it wrote the file, an UNAUTHENTICATED way to grant clinical authority."""
    _run, policy, base, allowlist_file = world
    monkeypatch.setattr(main_module, "default_settings", Settings(**{**base, "policy_engine": "pack"}))
    monkeypatch.setattr(main_module, "pack_policy", policy)
    client = TestClient(main_module.app)
    refused = client.put("/v1/admin/clinical-allowlist", json={"agents": ["did:integrity:attacker"]})
    assert refused.status_code == 409 and "BCC_CLINICAL_ALLOWLIST_FILE" in refused.json()["detail"]
    on_disk = json.loads(allowlist_file.read_text())["agents"]
    assert "did:integrity:attacker" not in on_disk
    assert client.get("/v1/admin/clinical-allowlist").json()["agents"] == on_disk
