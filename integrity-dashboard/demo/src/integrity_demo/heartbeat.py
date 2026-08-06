"""
Continuous real-activity generator for the 4 demo personas.

NOT a mock/fake data seeder -- every event this emits goes through the exact
same real, signature-verified pipelines PRODUCTION_GAPS.md Sec15 proved work
end-to-end: `IntegrityClient.flush_telemetry()` (POST /v1/telemetry/ingest,
Ed25519-signed over the canonical payload, verified and derived server-side
by the real oracle) and a real, signed `BCCCommitment` evaluated by
bcc_middleware's real OPA policy engine (POST /v1/bcc/intercept) -- nothing
here writes to any database directly. The *content* of each submission is a
small rotating set of realistic task descriptions (the same category of
scripted-but-real content as the existing demo's capital-allocation
prompt), but every signature, nonce, and policy decision made about it is
genuine.

Why this exists: a single `make demo` run only ever produces 1-2 telemetry
rows per agent and 0-1 audit_log rows -- enough to prove the pipeline works
(see Sec15), not enough to make time-bucketed charts (AIS history, telemetry
volume) or the live SSE feed / Audit Logs panel feel like an active system.
This loop runs indefinitely, submitting a mix of real telemetry and real BCC
intercepts -- a deliberate minority of the latter are real policy
violations (an unauthorized clinical intent_type, a keyword-flagged one),
using bcc_middleware's own real OPA rules, not a manufactured "looks
interesting" flag -- so the audit trail shows genuine ALLOW/DENY variety.

Usage: `uv run integrity-heartbeat` (runs until Ctrl-C / SIGTERM). Reads the
same RPC_URL/ORACLE_URL/DEPLOYMENTS_FILE env vars main.py does; needs no
FUNDER_PRIVATE_KEY or INTEGRITY_WALLET_PASSWORD since it only touches
already-registered agents' DID keypairs (unlocked without a password, see
did.py) -- it never registers a new agent or touches an EVM wallet keystore.
"""

from __future__ import annotations

import argparse
import logging
import os
import random
import signal
import time

import requests
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from integrity_sdk.bcc import NonceStore, build_bcc_commitment
from integrity_sdk.client import IntegrityClient
from integrity_sdk.did import agent_dir, load_or_create_did

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("integrity_demo.heartbeat")

ORACLE_URL = os.getenv("ORACLE_URL", "http://localhost:8080")
BCC_MIDDLEWARE_URL = os.getenv("BCC_MIDDLEWARE_URL", "http://localhost:8000")
OTLP_ENDPOINT = os.getenv("OTLP_ENDPOINT", "http://localhost:4317")

PERSONAS = [
    "healthcare_agent",
    "prediction_market_agent",
    "trading_agent",
    "capital_allocation_agent",
]

# Realistic, varied task descriptions -- rotated per persona so telemetry
# content isn't identical every call (identical text would make every
# entropy/grounding derivation identical too, which reads as fake even
# though the pipeline is real). Written as short first-person summaries of
# real-shaped agent work, matching the style of the existing demo's own
# scripted capital-allocation prompt.
_TASK_TEMPLATES = {
    "healthcare_agent": [
        "Reviewed patient census for the overnight shift and flagged two charts for physician follow-up.",
        "Cross-referenced medication orders against the formulary and found no interaction conflicts.",
        "Summarized discharge instructions for a patient being transferred to outpatient care.",
        "Verified insurance eligibility for three scheduled procedures ahead of tomorrow's clinic.",
    ],
    "prediction_market_agent": [
        "Rebalanced position sizing after new odds data shifted the implied probability by 4%.",
        "Closed out a resolved market and reconciled the payout against the on-chain escrow balance.",
        "Evaluated a new market proposal for internal consistency before recommending a stake.",
        "Monitored an active market's liquidity depth and adjusted the standing limit order.",
    ],
    "trading_agent": [
        "Executed a rebalance trade to bring portfolio allocation back within target bands.",
        "Reviewed overnight price action and confirmed no stop-loss triggers were breached.",
        "Reconciled the day's fills against the expected execution report with zero discrepancies.",
        "Evaluated counterparty risk exposure ahead of increasing position size.",
    ],
    "capital_allocation_agent": [
        "Reviewed the trading agent's recent AIS trend before considering a follow-on allocation.",
        "Audited the last allocation's on-chain settlement for correctness.",
        "Assessed the prediction market agent's compliance history ahead of a capital request.",
        "Recomputed the network's capital utilization ratio across all funded agents.",
    ],
}

# Mostly-safe intent types (real OPA ALLOW, no clinical/keyword rule fires)
# and a deliberate minority of intent types that trip a real bcc.rego rule --
# see that file's `clinical_intent_types`/keyword-deny lists. Not agents on
# bcc.rego's clinical allowlist, so a clinical intent_type here is a genuine
# HIPAA_ACCESS_CONTROL_VIOLATION deny, not a staged one.
_SAFE_INTENT_TYPES = ["payment", "contract_call", "data_query", "trading_decision"]
_VIOLATION_INTENT_TYPES = ["EMR_WRITE", "exfiltrate_customer_records"]

# Realistic nested-span shapes per persona, matching the real
# agent_conversation -> agent_tool_allocate_capital nesting main.py's own
# capital-allocation flow already produces -- a root "agent_task" span with
# 1-2 real child spans (llm_call/tool_call), not a single flat span, so
# Trace Analytics' DAG/Gantt views and Compare Traces have real structure to
# render for every persona, not just the one main.py exercises.
_TRACE_SHAPES = {
    "healthcare_agent": [
        ("review_patient_chart", [("llm_call.summarize_chart", None), ("tool_call.check_formulary_interactions", None)]),
        ("verify_insurance_eligibility", [("tool_call.payer_lookup", None)]),
    ],
    "prediction_market_agent": [
        ("evaluate_market_position", [("llm_call.assess_odds_shift", None), ("tool_call.rebalance_position", None)]),
        ("reconcile_resolved_market", [("tool_call.read_escrow_balance", None)]),
    ],
    "trading_agent": [
        ("execute_rebalance", [("llm_call.plan_rebalance", None), ("tool_call.submit_order", None)]),
        ("review_overnight_risk", [("tool_call.check_stop_loss_triggers", None)]),
    ],
    "capital_allocation_agent": [
        ("agent_conversation", [("llm_call.plan_allocation", None), ("agent_tool_allocate_capital", None)]),
        ("audit_allocation_history", [("tool_call.read_capital_pool_state", None)]),
    ],
}

_clients: dict = {}
_nonce_stores: dict = {}
_tracers: dict = {}
_tracer_providers: dict = {}
_running = True


def _client_for(agent_id: str, keypair) -> IntegrityClient:
    if agent_id not in _clients:
        _clients[agent_id] = IntegrityClient(agent_id=agent_id, keypair=keypair, oracle_url=ORACLE_URL, enable_otel_export=False)
    return _clients[agent_id]


def _bcc_nonce_store(persona: str) -> NonceStore:
    if persona not in _nonce_stores:
        _nonce_stores[persona] = NonceStore(agent_dir(persona) / "bcc_nonce")
    return _nonce_stores[persona]


def _tracer_for(agent_id: str):
    """Same per-agent-provider pattern as main.py's `_tracer_for` (and the
    same reason: a real `integrity.agent.id` resource attribute per agent,
    never routed through the global TracerProvider singleton)."""
    if agent_id not in _tracers:
        resource = Resource.create({"service.name": "integrity-demo-heartbeat", "integrity.agent.id": agent_id})
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=OTLP_ENDPOINT, insecure=True)))
        _tracer_providers[agent_id] = provider
        _tracers[agent_id] = provider.get_tracer(__name__)
    return _tracers[agent_id]


def _flush_all_tracers() -> None:
    for agent_id, provider in _tracer_providers.items():
        try:
            provider.force_flush(timeout_millis=5000)
        except Exception:
            logger.warning("failed to flush OTel spans for %s", agent_id, exc_info=True)


def _submit_trace(persona: str, agent_did: str) -> None:
    root_name, children = random.choice(_TRACE_SHAPES[persona])
    tracer = _tracer_for(agent_did)
    with tracer.start_as_current_span(root_name) as root_span:
        root_span.set_attribute("agent.id", agent_did)
        root_span.set_attribute("persona", persona)
        for child_name, _ in children:
            with tracer.start_as_current_span(child_name) as child_span:
                child_span.set_attribute("agent.id", agent_did)
                time.sleep(random.uniform(0.02, 0.15))  # real, small, non-zero duration for the Gantt view
    # Flushed immediately (not just at process exit) so a short-lived
    # `--iterations` run or a user actively watching the Live Stream tab
    # sees spans land promptly -- BatchSpanProcessor's default export
    # schedule otherwise buffers for several seconds.
    try:
        _tracer_providers[agent_did].force_flush(timeout_millis=5000)
    except Exception:
        logger.warning("failed to flush OTel spans for %s", agent_did, exc_info=True)
    logger.info("trace OK  [%s] %s (%d child spans)", persona, root_name, len(children))


def _submit_telemetry(persona: str, agent_did: str, keypair) -> None:
    text = random.choice(_TASK_TEMPLATES[persona])
    client = _client_for(agent_did, keypair)
    client.log_telemetry({
        "event": "heartbeat_task",
        "persona": persona,
        "text_output": text,
        "token_usage": {"prompt_tokens": random.randint(80, 400), "completion_tokens": random.randint(20, 150)},
    })
    if client.flush_telemetry():
        logger.info("telemetry OK  [%s] %s", persona, text[:60])
    else:
        logger.warning("telemetry rejected by oracle [%s]", persona)


def _submit_bcc_intercept(persona: str, agent_did: str, keypair) -> None:
    violation = random.random() < 0.25
    intent_type = random.choice(_VIOLATION_INTENT_TYPES if violation else _SAFE_INTENT_TYPES)
    nonce = _bcc_nonce_store(persona).next()
    commitment = build_bcc_commitment(
        agent_id=agent_did,
        intent_type=intent_type,
        intent_payload={"task": random.choice(_TASK_TEMPLATES[persona]), "nonce": nonce},
        nonce=nonce,
        keypair=keypair,
    )
    try:
        resp = requests.post(f"{BCC_MIDDLEWARE_URL}/v1/bcc/intercept", json=commitment, timeout=10)
        resp.raise_for_status()
        body = resp.json()
        decision = "ALLOW" if body.get("authorized") else "DENY"
        logger.info("bcc intercept %s  [%s] intent_type=%s reason=%s", decision, persona, intent_type, body.get("reason"))
    except requests.RequestException as exc:
        logger.warning("bcc intercept failed [%s]: %s", persona, exc)


def _handle_signal(signum, frame):
    global _running
    logger.info("received signal %s, shutting down after current iteration", signum)
    _running = False


def run(min_interval: float, max_interval: float, iterations: int | None) -> None:
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    identities = {}
    for persona in PERSONAS:
        try:
            agent_did, keypair, _ = load_or_create_did(persona)
            identities[persona] = (agent_did, keypair)
            logger.info("loaded identity for %s -> %s", persona, agent_did)
        except Exception:
            logger.warning("could not load identity for %s, skipping it this run", persona, exc_info=True)

    if not identities:
        raise RuntimeError("no demo agent identities found -- run `make demo` at least once first")

    count = 0
    try:
        while _running and (iterations is None or count < iterations):
            persona = random.choice(list(identities.keys()))
            agent_did, keypair = identities[persona]

            # 45% telemetry, 30% OTel trace, 25% BCC intercept -- weighted so
            # Trace Analytics (this session's explicit ask) gets steady new
            # traces without starving the telemetry/audit-log pipelines the
            # rest of the dashboard depends on.
            roll = random.random()
            if roll < 0.45:
                _submit_telemetry(persona, agent_did, keypair)
            elif roll < 0.75:
                _submit_trace(persona, agent_did)
            else:
                _submit_bcc_intercept(persona, agent_did, keypair)

            count += 1
            if _running and (iterations is None or count < iterations):
                time.sleep(random.uniform(min_interval, max_interval))
    finally:
        _flush_all_tracers()

    logger.info("heartbeat stopped after %d iterations", count)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-interval", type=float, default=3.0, help="minimum seconds between events")
    parser.add_argument("--max-interval", type=float, default=8.0, help="maximum seconds between events")
    parser.add_argument("--iterations", type=int, default=None, help="stop after N events (default: run forever)")
    args = parser.parse_args()
    run(args.min_interval, args.max_interval, args.iterations)


if __name__ == "__main__":
    main()
