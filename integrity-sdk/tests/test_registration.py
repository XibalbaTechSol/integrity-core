"""
Real end-to-end test of registration.register_agent against the session
anvil chain from conftest.py's `deployed_chain` fixture. Runs with
skip_oracle_registration=True since integrity-oracle's HTTP layer doesn't
exist yet (see docs/INTERFACE_CONTRACT.md §6.6's honest note on that) — this
test proves every ON-CHAIN step of the sequence, which is everything this
package can verify on its own; oracle re-verification gets its own coverage
once integrity-oracle's routes exist.
"""

from __future__ import annotations

import json
import os

import pytest

from integrity_sdk import registration


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch, deployed_chain):
    monkeypatch.setenv("INTEGRITY_DID_HOME", str(tmp_path / "dids"))
    monkeypatch.setenv("INTEGRITY_WALLET_HOME", str(tmp_path / "wallets"))
    monkeypatch.setenv("INTEGRITY_WALLET_PASSWORD", "test-only-password")
    monkeypatch.setenv("RPC_URL", deployed_chain["rpc_url"])
    monkeypatch.setenv("FUNDER_PRIVATE_KEY", deployed_chain["funder"].key.hex())

    # Write a deployments file matching the new nested shape, from the real
    # addresses this session's Deploy.s.sol run actually produced.
    addr = deployed_chain["addresses"]
    deployments = {
        "chainId": deployed_chain["chain_id"],
        "singletons": {
            "AgentPrimitivesFactory": addr["AgentPrimitivesFactory"],
            "IntegrityToken": addr["IntegrityToken"],
            "XibalbaAgentRegistry": addr["XibalbaAgentRegistry"],
            "DomainRegistry": addr["DomainRegistry"],
        },
        "protocolAddresses": {"oracleSigner": deployed_chain["funder"].address},
    }
    deployments_path = tmp_path / "deployments.local.json"
    deployments_path.write_text(json.dumps(deployments))
    monkeypatch.setenv("DEPLOYMENTS_FILE", str(deployments_path))


def test_register_agent_full_onchain_sequence():
    result = registration.register_agent("registration-test-agent", skip_oracle_registration=True)

    assert result.did.startswith("did:integrity:")
    assert result.evm_address.startswith("0x")
    assert result.oracle_registered is False
    zero = "0x0000000000000000000000000000000000000000"
    for field_value in (
        result.sovereign_agent,
        result.state_anchor,
        result.reputation_registry,
        result.slasher,
        result.verifier_registry,
        result.compliance_gate,
        result.agent_profile,
    ):
        assert field_value.lower() != zero


def test_register_agent_persists_document_and_primitives(tmp_path):
    from integrity_sdk import did

    result = registration.register_agent("persist-test-agent", skip_oracle_registration=True)

    doc_path = did.agent_dir("persist-test-agent") / "document.json"
    primitives_path = did.agent_dir("persist-test-agent") / "primitives.json"
    assert doc_path.exists()
    assert primitives_path.exists()

    doc = json.loads(doc_path.read_text())
    assert doc["id"] == result.did
    evm_methods = [vm for vm in doc["verificationMethod"] if vm["type"] == "EcdsaSecp256k1RecoveryMethod2020"]
    assert len(evm_methods) == 1
    assert result.evm_address in evm_methods[0]["blockchainAccountId"]

    primitives = json.loads(primitives_path.read_text())
    assert primitives["sovereign_agent"] == result.sovereign_agent


def test_register_agent_is_idempotent_for_an_already_registered_did():
    """
    Regression test for PRODUCTION_GAPS.md Sec3: register_agent() used to
    always deploy a FRESH SovereignAgent/StateAnchor pair on every call, so
    calling it twice for the same identity (a real retry-after-partial-failure
    scenario, or simply an idempotent re-run) deployed a second, orphaned pair
    that then reverted AlreadyRegistered() at the final registerPrimitives
    step -- after gas and testnet ITK were already spent on the throwaway
    deploy. The second call must now short-circuit and return the SAME
    on-chain primitives, with no new SovereignAgent deployed.
    """
    first = registration.register_agent("idempotent-test-agent", skip_oracle_registration=True)
    second = registration.register_agent("idempotent-test-agent", skip_oracle_registration=True)

    assert second.sovereign_agent == first.sovereign_agent
    assert second.state_anchor == first.state_anchor
    assert second.reputation_registry == first.reputation_registry
    assert second.slasher == first.slasher
    assert second.verifier_registry == first.verifier_registry
    assert second.compliance_gate == first.compliance_gate
    assert second.agent_profile == first.agent_profile


def test_register_agent_resumes_from_partial_failure_without_redeploying(monkeypatch):
    """
    Regression test for the real incidents in PRODUCTION_GAPS.md's registration entry
    (2026-08-14, 2026-08-17): a failure after SovereignAgent/StateAnchor deploy but before
    registerPrimitives succeeds used to be invisible to register_agent's idempotency check
    (which only fires once registerPrimitives has already succeeded), so every retry
    deployed a fresh, throwaway pair -- real gas spent, real orphaned contracts, five
    separate incidents across two sessions.

    Simulates that exact failure shape: monkeypatch register_primitives to fail on the
    first call (as if the on-chain registerPrimitives itself reverted, e.g. a missing role
    grant), then let it succeed on a second call. The second call must reuse the SAME
    SovereignAgent/StateAnchor -- not deploy a second pair.
    """
    from integrity_sdk import chain as chain_module

    real_register_primitives = chain_module.register_primitives
    call_count = {"n": 0}

    def flaky_register_primitives(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("simulated registerPrimitives revert (e.g. a missing role grant)")
        return real_register_primitives(*args, **kwargs)

    monkeypatch.setattr(chain_module, "register_primitives", flaky_register_primitives)

    with pytest.raises(registration.RegistrationError, match="step 9"):
        registration.register_agent("resume-test-agent", skip_oracle_registration=True)

    # Progress must be recorded after the failed attempt.
    from integrity_sdk import did as did_module

    progress_path = did_module.agent_dir("resume-test-agent") / "registration_progress.json"
    assert progress_path.exists()
    progress = json.loads(progress_path.read_text())
    assert progress["sovereign_agent"].startswith("0x")
    assert progress["state_anchor"].startswith("0x")

    result = registration.register_agent("resume-test-agent", skip_oracle_registration=True)

    assert result.sovereign_agent.lower() == progress["sovereign_agent"].lower()
    assert result.state_anchor.lower() == progress["state_anchor"].lower()
    assert call_count["n"] == 2

    # Progress file must be cleared once registration genuinely completes.
    assert not progress_path.exists()


def test_register_agent_discards_stale_progress_with_no_bytecode(tmp_path, monkeypatch):
    """A progress file pointing at an address with no deployed bytecode (e.g. hand-edited,
    corrupted, or pointing at a phantom address the way deployments.baseSepolia.json once
    did) must never be trusted blindly -- register_agent must fall back to a fresh deploy
    rather than trying to reuse something that was never really there."""
    from integrity_sdk import did as did_module

    did_module.load_or_create_did("stale-progress-agent")
    progress_path = did_module.agent_dir("stale-progress-agent") / "registration_progress.json"
    progress_path.write_text(json.dumps({
        "sovereign_agent": "0x000000000000000000000000000000000000dEaD",
        "state_anchor": "0x000000000000000000000000000000000000bEEF",
    }))

    result = registration.register_agent("stale-progress-agent", skip_oracle_registration=True)

    assert result.sovereign_agent.lower() != "0x000000000000000000000000000000000000dead"
    assert result.state_anchor.lower() != "0x000000000000000000000000000000000000beef"


def test_register_agent_requires_funder_key(monkeypatch):
    monkeypatch.delenv("FUNDER_PRIVATE_KEY", raising=False)
    with pytest.raises(registration.RegistrationError, match="FUNDER_PRIVATE_KEY"):
        registration.register_agent("no-funder-agent", skip_oracle_registration=True)


def test_register_agent_rejects_unknown_vertical():
    with pytest.raises(ValueError, match="compliance_vertical"):
        registration.register_agent("bad-vertical-agent", compliance_vertical="not-a-real-vertical")


def test_register_agent_self_registers_personal_domain_when_missing():
    """Regression test for the 2026-08-30 incident: registering under an agent's own
    f"{agent_id}.integrity" domain used to revert DomainJoinNotApproved() at the final
    registerPrimitives step -- after a real SovereignAgent/StateAnchor deploy had already
    spent gas -- because DomainRegistry was never checked, and the domain never existed.
    auto_register_domain defaults to True specifically for this personal-domain pattern."""
    from integrity_sdk import chain as chain_module

    agent_id = "domain-self-register-agent"
    domain_name = f"{agent_id}.integrity"

    result = registration.register_agent(
        agent_id, domain_name=domain_name, skip_oracle_registration=True,
    )

    assert result.sovereign_agent.startswith("0x")

    from eth_utils import keccak
    w3 = chain_module.get_w3(os.environ["RPC_URL"])
    domain_registry_address = json.loads(open(os.environ["DEPLOYMENTS_FILE"]).read())["singletons"]["DomainRegistry"]
    domain_id = keccak(text=domain_name)
    assert chain_module.domain_exists(w3, domain_registry_address, domain_id)
    assert chain_module.can_join_domain(w3, domain_registry_address, domain_id, result.evm_address)


def test_register_agent_rejects_missing_nonpersonal_domain_before_spending_gas():
    """A domain_name that is NOT the agent's own personal-domain convention must never be
    auto-registered (claiming a name this flow doesn't own by construction would be a real
    mistake), and the rejection must happen before any gas is spent -- no funding, no
    deploy, no progress file."""
    from integrity_sdk import did as did_module

    agent_id = "domain-reject-agent"
    with pytest.raises(registration.RegistrationError, match="does not exist"):
        registration.register_agent(
            agent_id, domain_name="some-domain-nobody-registered.integrity",
            skip_oracle_registration=True,
        )

    progress_path = did_module.agent_dir(agent_id) / "registration_progress.json"
    assert not progress_path.exists()


def test_register_agent_rejects_missing_personal_domain_when_auto_register_disabled():
    """auto_register_domain=False must be honored even for the personal-domain pattern --
    an explicit opt-out means opt-out, not a silent auto-fix anyway."""
    agent_id = "domain-no-auto-agent"
    domain_name = f"{agent_id}.integrity"
    with pytest.raises(registration.RegistrationError, match="does not exist"):
        registration.register_agent(
            agent_id, domain_name=domain_name, auto_register_domain=False,
            skip_oracle_registration=True,
        )


def test_preflight_register_agent_reports_every_check():
    """preflight_register_agent is a pure read-only dry run -- running it must never spend
    gas or create a progress file, and it must report on both the registrar-role and
    domain checks this session's incident revealed were previously unchecked entirely."""
    from integrity_sdk import did as did_module

    agent_id = "preflight-report-agent"
    result = registration.preflight_register_agent(agent_id, domain_name="general.integrity")

    names = {c.name for c in result.checks}
    assert {"rpc_reachable", "deployments_file", "factory_registrar_role", "funder_balance", "domain_exists"} <= names
    assert result.ok  # "general.integrity" is a real, pre-existing Open domain in the test deployment

    progress_path = did_module.agent_dir(agent_id) / "registration_progress.json"
    assert not progress_path.exists()


def test_preflight_register_agent_flags_missing_personal_domain_as_autofixable():
    agent_id = "preflight-missing-domain-agent"
    domain_name = f"{agent_id}.integrity"
    result = registration.preflight_register_agent(agent_id, domain_name=domain_name)

    domain_check = next(c for c in result.checks if c.name == "domain_can_join")
    assert not domain_check.passed
    assert "auto_register_domain=True" in domain_check.detail
    assert not result.ok
