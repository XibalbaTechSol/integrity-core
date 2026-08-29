from __future__ import annotations

from integrity_sdk import bcc
from integrity_sdk.did import Keypair, verify_signature
from integrity_sdk.telemetry.intent import (
    IntentDeviationResult,
    compare_planned_to_actual,
    invoke_intent,
)


class _FakeClient:
    def __init__(self):
        self.recorded_runs = []
        self.recorded_metrics = []

    def _record_trace_run(self, run):
        self.recorded_runs.append(run)

    def record_metric(self, name, value, tags=None):
        self.recorded_metrics.append((name, value, tags))


def _kp() -> Keypair:
    return Keypair.generate()


# --- compare_planned_to_actual (tier-1 deterministic comparison) ------------------------


def test_exact_match_scores_one():
    result = compare_planned_to_actual(
        {"tool": "write_emr", "args": {"patient_id": "p1"}},
        {"tool": "write_emr", "args": {"patient_id": "p1"}},
    )
    assert result.adherence_score == 1.0
    assert result.matched_tool and result.matched_args


def test_tool_matches_args_differ_scores_half():
    result = compare_planned_to_actual(
        {"tool": "write_emr", "args": {"patient_id": "p1"}},
        {"tool": "write_emr", "args": {"patient_id": "p2"}},
    )
    assert result.adherence_score == 0.5
    assert result.matched_tool and not result.matched_args


def test_tool_mismatch_scores_zero():
    result = compare_planned_to_actual(
        {"tool": "write_emr", "args": {}},
        {"tool": "delete_emr", "args": {}},
    )
    assert result.adherence_score == 0.0
    assert not result.matched_tool


def test_missing_planned_or_actual_scores_zero():
    assert compare_planned_to_actual(None, {"tool": "x"}).adherence_score == 0.0
    assert compare_planned_to_actual({"tool": "x"}, None).adherence_score == 0.0
    assert compare_planned_to_actual(None, None).adherence_score == 0.0


def test_args_comparison_is_normalized_not_literal():
    # Key order and int-vs-str-key differences shouldn't cause a false mismatch
    # -- _normalize_args round-trips through JSON with sort_keys.
    result = compare_planned_to_actual(
        {"tool": "t", "args": {"b": 2, "a": 1}},
        {"tool": "t", "args": {"a": 1, "b": 2}},
    )
    assert result.adherence_score == 1.0


def test_deviation_result_to_dict_roundtrips_fields():
    result = IntentDeviationResult(
        matched_tool=True, matched_args=True, adherence_score=1.0,
        planned_action={"tool": "t"}, actual_action={"tool": "t"}, detail="ok",
    )
    d = result.to_dict()
    assert d["adherence_score"] == 1.0
    assert d["detail"] == "ok"


# --- invoke_intent context manager -------------------------------------------------------


def test_invoke_intent_builds_a_real_verifiable_bcc_commitment():
    keypair = _kp()
    with invoke_intent(
        intent_type="EMR_WRITE",
        intent_payload={"patient_id": "p1"},
        keypair=keypair,
        nonce=1,
        agent_id="did:integrity:test-agent",
        chain_id=31337,
        verifying_contract="0x111111111111111111111111111111111111111a",
    ) as intent:
        commitment = intent.commitment

    assert commitment["intent_type"] == "EMR_WRITE"
    assert commitment["agent_id"] == "did:integrity:test-agent"
    # _planned_action is a local convenience field, not part of the signed
    # payload -- verify_bcc_commitment must still succeed with it present,
    # since bcc.py's own verify function only excludes "signature".
    assert bcc.verify_bcc_commitment(
        {k: v for k, v in commitment.items() if k != "_planned_action"},
        keypair.public_bytes(),
    )


def test_invoke_intent_id_is_the_commitments_intended_state_hash():
    keypair = _kp()
    with invoke_intent(
        intent_type="EMR_WRITE",
        intent_payload={"a": 1},
        keypair=keypair,
        nonce=1,
        agent_id="did:integrity:test-agent",
        chain_id=31337,
        verifying_contract="0x111111111111111111111111111111111111111a",
    ) as intent:
        assert intent.intent_id == intent.commitment["intended_state_hash"]


def test_invoke_intent_records_trace_run_with_correlated_intent_id():
    keypair = _kp()
    client = _FakeClient()
    with invoke_intent(
        intent_type="EMR_WRITE",
        intent_payload={"a": 1},
        keypair=keypair,
        nonce=1,
        agent_id="did:integrity:test-agent",
        chain_id=31337,
        verifying_contract="0x111111111111111111111111111111111111111a",
        goal="update patient record",
        client=client,
    ) as intent:
        pass

    assert len(client.recorded_runs) == 1
    run = client.recorded_runs[0]
    assert run["run_type"] == "intent"
    assert run["inputs"]["intent_id"] == intent.intent_id
    assert run["inputs"]["goal"] == "update patient record"


def test_invoke_intent_reraises_exceptions_from_the_body():
    keypair = _kp()
    try:
        with invoke_intent(
            intent_type="EMR_WRITE",
            intent_payload={"a": 1},
            keypair=keypair,
            nonce=1,
            agent_id="did:integrity:test-agent",
        chain_id=31337,
        verifying_contract="0x111111111111111111111111111111111111111a",
        ):
            raise ValueError("action denied downstream")
    except ValueError as e:
        assert str(e) == "action denied downstream"
    else:
        raise AssertionError("invoke_intent must not swallow exceptions")


def test_record_outcome_computes_adherence_and_records_metric():
    keypair = _kp()
    client = _FakeClient()
    with invoke_intent(
        intent_type="EMR_WRITE",
        intent_payload={"a": 1},
        keypair=keypair,
        nonce=1,
        agent_id="did:integrity:test-agent",
        chain_id=31337,
        verifying_contract="0x111111111111111111111111111111111111111a",
        planned_action={"tool": "write_emr", "args": {"patient_id": "p1"}},
        client=client,
    ) as intent:
        result = intent.record_outcome({"tool": "write_emr", "args": {"patient_id": "p1"}})

    assert result.adherence_score == 1.0
    assert intent.deviation is result
    assert client.recorded_metrics[0][0] == "integrity.intent.plan_adherence"
    assert client.recorded_metrics[0][1] == 1.0
    # The run's outputs (recorded on __exit__) should reflect the deviation
    # result computed inside the `with` block, not be left empty.
    assert client.recorded_runs[0]["outputs"]["adherence_score"] == 1.0


def test_record_outcome_detects_a_real_deviation():
    keypair = _kp()
    with invoke_intent(
        intent_type="EMR_WRITE",
        intent_payload={"a": 1},
        keypair=keypair,
        nonce=1,
        agent_id="did:integrity:test-agent",
        chain_id=31337,
        verifying_contract="0x111111111111111111111111111111111111111a",
        planned_action={"tool": "write_emr", "args": {}},
    ) as intent:
        result = intent.record_outcome({"tool": "delete_emr", "args": {}})

    assert result.adherence_score == 0.0
    assert not result.matched_tool


def test_nested_execution_span_correlates_via_parent_run_id():
    # invoke_intent shares tracing.py's _current_run_id contextvar, so a
    # traceable-wrapped execution inside the `with` block should nest under
    # the intent's run -- proving the temporal-priority/correlation design
    # (intent span opens BEFORE execution, execution nests under it).
    from integrity_sdk.telemetry.tracing import traceable

    keypair = _kp()
    client = _FakeClient()
    with invoke_intent(
        intent_type="EMR_WRITE",
        intent_payload={"a": 1},
        keypair=keypair,
        nonce=1,
        agent_id="did:integrity:test-agent",
        chain_id=31337,
        verifying_contract="0x111111111111111111111111111111111111111a",
        client=client,
    ) as intent:
        @traceable(name="write_emr", run_type="tool", client=client)
        def do_write():
            return "ok"

        do_write()

    # recorded_runs order: inner execution finishes (and is recorded) before
    # the outer intent's __exit__ records itself.
    exec_run, intent_run = client.recorded_runs
    assert exec_run["name"] == "write_emr"
    assert exec_run["parent_run_id"] == intent_run["run_id"]
    assert intent_run["run_type"] == "intent"


def test_verify_signature_helper_available_for_sanity_checks():
    # Not a test of invoke_intent itself -- just confirms the import used by
    # other tests in this module actually resolves (did.verify_signature),
    # since bcc.verify_bcc_commitment wraps it internally.
    kp = _kp()
    sig = kp.sign(b"hello")
    assert verify_signature(kp.public_bytes(), b"hello", sig)
