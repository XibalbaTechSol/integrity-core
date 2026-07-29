import inspect
import os
import logging

from eth_account import Account

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from integrity_sdk import chain
from integrity_sdk.registration import register_agent, RegistrationError
from integrity_sdk.did import load_or_create_did
from integrity_sdk.wallet import generate_or_load_evm_wallet
from integrity_sdk.markets import allocate_capital
from integrity_sdk.chain import load_deployments
from integrity_sdk.client import IntegrityClient

from integrity_demo.agent_loop import IntegrityAgent
from integrity_demo import userapi_bridge

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("integrity_demo.main")

OTLP_ENDPOINT = "http://localhost:4317"

# Per-agent OTel tracers, deliberately NOT installed as the process-global
# provider. `opentelemetry.trace.set_tracer_provider` (and this SDK's own
# `telemetry/core.py::init_telemetry`, which wraps it) is a one-shot global
# -- the first call wins, every later call is a silent no-op. This engine
# registers 4 independent agent identities in one process, and the oracle's
# real OTLP receiver requires a genuine `integrity.agent.id` resource
# attribute on every span it accepts. The old code here built ONE shared
# module-level Resource with no such attribute at all, so every span this
# engine ever exported was rejected -- found by actually running this
# against a real oracle, not by inspection (see PRODUCTION_GAPS.md).
# Building one TracerProvider per agent and using it directly via
# `.get_tracer()`, never through the global setter, is the standard
# OTel pattern for several independent resources coexisting in one process.
_tracers: dict = {}
_tracer_providers: dict = {}
# Real IntegrityClient instances, one per agent, used ONLY for
# log_telemetry()/flush_telemetry() (POST /v1/telemetry/ingest) -- kept
# entirely separate from the OTel tracer machinery above. Before this, this
# engine only ever emitted OTel spans; it never called the SDK's telemetry-
# submission path at all, so `telemetry_events` (the table AIS's
# entropy/grounding/sacrifice/compliance signals are actually derived from)
# stayed empty for every demo agent forever, regardless of how many times
# the demo ran -- confirmed by querying the oracle directly after a real run
# and finding zero rows despite real OTel spans/traces existing. `enable_
# otel_export=False` here is deliberate: IntegrityClient.__init__ would
# otherwise call telemetry_core.init_telemetry(), which installs a GLOBAL
# TracerProvider (see that function's own one-shot-singleton warning) --
# exactly the trap `_tracer_for`'s per-agent providers above were built to
# avoid for this same multi-agent-in-one-process engine. OTel tracing and
# telemetry-event submission are two independent real pipelines here, not
# one going through the other.
_clients: dict = {}


def _client_for(agent_id: str, keypair) -> IntegrityClient:
    if agent_id not in _clients:
        _clients[agent_id] = IntegrityClient(agent_id=agent_id, keypair=keypair, enable_otel_export=False)
    return _clients[agent_id]


def _submit_telemetry(agent_did: str, keypair, metadata: dict) -> None:
    """Best-effort, matching this module's existing tolerance for telemetry/
    tracing failures not aborting the run (see _flush_all_tracers' docstring
    for the same posture applied to OTel spans). A failed submission here
    means one demo agent's AIS stays at "no data yet" for this run, not that
    registration or capital allocation should be considered failed."""
    try:
        client = _client_for(agent_did, keypair)
        client.log_telemetry(metadata)
        if not client.flush_telemetry():
            logger.warning("telemetry flush for %s was not accepted by the oracle", agent_did)
    except Exception:
        logger.warning("failed to submit telemetry for %s", agent_did, exc_info=True)


def _tracer_for(agent_id: str):
    if agent_id not in _tracers:
        resource = Resource.create(
            {
                "service.name": "integrity-demo-scenario-engine",
                "integrity.agent.id": agent_id,
            }
        )
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=OTLP_ENDPOINT, insecure=True)))
        _tracer_providers[agent_id] = provider
        _tracers[agent_id] = provider.get_tracer(__name__)
    return _tracers[agent_id]


def _flush_all_tracers() -> None:
    """`BatchSpanProcessor` buffers spans and exports on a timer/batch-size
    threshold -- nothing forces a flush on process exit. Without this, any
    span still sitting in the buffer when this short-lived script's process
    exits is silently dropped, never reaching the oracle's OTLP receiver
    (found by actually running the demo and checking the oracle's real
    otel_spans table came up empty, not by inspection)."""
    for agent_id, provider in _tracer_providers.items():
        try:
            provider.force_flush(timeout_millis=5000)
            provider.shutdown()
        except Exception:
            logger.warning("failed to flush OTel spans for %s", agent_id, exc_info=True)


def _check_funder_balance(agent_ids: list) -> None:
    """Real preflight check against the actual chain, not a guess -- reads
    the same FUNDER_PRIVATE_KEY/RPC_URL `register_agent` itself reads, and
    fails loudly with the exact shortfall before any registration is
    attempted. Found the need for this the hard way: the funder wallet on
    live Base Sepolia sits well under one agent's worth of funding today
    (see FAUCET_INFO.md) -- without this check, a real run silently fails
    registration 1 of N with a deep RPC error instead of a clear upfront
    one. Required amount is read off `register_agent`'s own default
    parameter via reflection, not a second hardcoded constant that could
    drift from the real one."""
    funder_key = os.getenv("FUNDER_PRIVATE_KEY")
    if not funder_key:
        return  # register_agent() raises its own clear error for this
    rpc_url = os.getenv("RPC_URL", "http://localhost:8545")
    w3 = chain.get_w3(rpc_url)
    if not w3.is_connected():
        return  # register_agent() raises its own clear error for this

    fund_amount_wei = inspect.signature(register_agent).parameters["fund_amount_wei"].default
    funder = Account.from_key(funder_key)
    balance = w3.eth.get_balance(funder.address)
    required = fund_amount_wei * len(agent_ids)
    if balance < required:
        raise RegistrationError(
            f"Funder wallet {funder.address} has {w3.from_wei(balance, 'ether')} ETH, but "
            f"registering {len(agent_ids)} agents needs at least {w3.from_wei(required, 'ether')} ETH "
            f"({w3.from_wei(fund_amount_wei, 'ether')} ETH each, register_agent's own default). "
            f"Fund the wallet before running this scenario -- see FAUCET_INFO.md for faucet links."
        )


def main():
    logger.info("Initializing Integrity Demo Scenario Engine")
    # No-op unless USERAPI_URL/USERAPI_TOKEN/USERAPI_RUN_ID are all set (see
    # userapi_bridge.py's module docstring) -- lets an operator tie this run
    # back to a demo_runs row created via POST /demo/run beforehand.
    userapi_bridge.report_status("running")

    try:
        summary = _run_scenario()
    except Exception as exc:
        userapi_bridge.report_status("failed", {"error": str(exc)})
        raise
    else:
        userapi_bridge.report_status("completed", summary)
    finally:
        _flush_all_tracers()


def _run_scenario() -> dict:
    agents = [
        {"id": "healthcare_agent", "vertical": "healthcare"},
        {"id": "prediction_market_agent", "vertical": "prediction_market"},
        {"id": "trading_agent", "vertical": "trading"},
        {"id": "capital_allocation_agent", "vertical": "capital_allocation"},
    ]

    _check_funder_balance([a["id"] for a in agents])

    agent_data = {}

    for a in agents:
        logger.info(f"Registering {a['id']}...")
        # Resolve the real DID before opening the span -- `load_or_create_did`
        # is a pure, deterministic local keypair load/create with no chain
        # interaction, and `register_agent` calls it again internally with
        # the same result, so this doesn't duplicate any real work. Every
        # OTel span for this agent must be tagged with its real DID, not the
        # internal persona short-name ("capital_allocation_agent") -- the
        # oracle's telemetry/trace endpoints and the frontend both key
        # exclusively by DID (see GET /v1/agents, /v1/agent/{did}/telemetry),
        # so a span resource attribute using the short-name would be
        # permanently invisible to any per-agent view (found by actually
        # querying the oracle after a real run and getting zero rows back
        # for a DID that had spans stored under the short-name instead).
        agent_did, keypair, _ = load_or_create_did(a["id"])
        with _tracer_for(agent_did).start_as_current_span("register_agent"):
            try:
                # skip_oracle_registration if no oracle running locally
                reg = register_agent(
                    agent_id=a["id"],
                    compliance_vertical=a["vertical"],
                    skip_oracle_registration=False
                )
                evm_wallet = generate_or_load_evm_wallet(a["id"])

                agent_data[a["id"]] = {
                    "registration": reg,
                    "keypair": keypair,
                    "evm_wallet": evm_wallet
                }

                # Real telemetry_events row -- see _submit_telemetry's
                # docstring for why this didn't exist before. No text_output
                # yet at this point (nothing has "said" anything), so
                # entropy/grounding derive to their real, honest neutral
                # defaults (1.0 -- "no evidence of instability", per
                # derive.py's own docstring) rather than a fabricated score;
                # what matters here is a real, signed, oracle-accepted event
                # existing at all for every agent, not just the one that
                # happens to make an LLM call below.
                _submit_telemetry(
                    agent_did,
                    keypair,
                    {"event": "agent_registered", "vertical": a["vertical"], "persona": a["id"]},
                )
            except Exception as e:
                logger.error(f"Failed to register {a['id']}: {e}")

    tool_call_error = None
    if "capital_allocation_agent" in agent_data:
        allocator = agent_data["capital_allocation_agent"]
        target = agent_data.get("trading_agent")

        if target:
            allocator_did = allocator["registration"].did
            allocator_tracer = _tracer_for(allocator_did)

            def tool_allocate_capital(target_address: str, amount_wei: str):
                with allocator_tracer.start_as_current_span("agent_tool_allocate_capital") as span:
                    span.set_attribute("agent.id", allocator_did)
                    span.set_attribute("target.address", target_address)
                    try:
                        deployments = load_deployments(os.getenv("DEPLOYMENTS_FILE", "../../deployments.local.json"))
                        from integrity_sdk.bcc import NonceStore
                        from integrity_sdk.did import agent_dir
                        nonce_store = NonceStore(agent_dir("capital_allocation_agent") / "nonce")
                        next_nonce = nonce_store.next()
                        
                        alloc_id, token = allocate_capital(
                            allocator_agent_id=allocator["registration"].did,
                            keypair=allocator["keypair"],
                            evm_account=allocator["evm_wallet"],
                            allocator_sovereign_agent_address=allocator["registration"].sovereign_agent,
                            capital_pool_address=deployments["singletons"]["A2ACapitalPool"],
                            itk_address=deployments["singletons"]["IntegrityToken"],
                            target_agent_address=target_address,
                            amount_wei=int(amount_wei),
                            min_ais_to_maintain=50,
                            nonce=next_nonce,
                            bcc_middleware_url="http://localhost:8000"
                        )
                        span.set_attribute("allocation.id", alloc_id)
                        return {"status": "success", "allocation_id": alloc_id, "token": token}
                    except Exception as e:
                        logger.exception("Capital allocation tool execution failed")
                        span.record_exception(e)
                        return {"status": "error", "message": str(e)}

            tools = [{
                "type": "function",
                "function": {
                    "name": "allocate_capital",
                    "description": "Allocate ITK capital to another trusted agent on-chain.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "target_address": {"type": "string", "description": "The target agent's SovereignAgent contract address"},
                            "amount_wei": {"type": "string", "description": "Amount in WEI to allocate"}
                        },
                        "required": ["target_address", "amount_wei"]
                    }
                }
            }]
            tool_map = {"allocate_capital": tool_allocate_capital}

            logger.info("Running Xibalba Agent Loop for Capital Allocator...")
            agent = IntegrityAgent(
                system_prompt="You are a capital allocator agent. Your task is to allocate 1000000000000000000 WEI (1 ITK) to the trading agent.",
                tools=tools,
                tool_map=tool_map
            )

            # Real, previously-unguarded LLM call -- found by actually
            # running this: any failure here (bad/missing API key, rate
            # limit, network outage) used to crash the entire process with
            # a raw traceback, unlike the registration loop above (which
            # already degrades one agent at a time). Now degrades the same
            # way: log it, record it in the summary main() reports via
            # userapi_bridge, and let the run finish with whatever DID
            # register successfully rather than losing that too.
            try:
                with allocator_tracer.start_as_current_span("agent_conversation") as span:
                    span.set_attribute("agent.id", allocator_did)
                    target_addr = target["registration"].sovereign_agent
                    response = agent.run_conversation(f"Please allocate capital to the trading agent. Their address is: {target_addr}")
                    logger.info(f"Agent Final Response: {response}")
                    # Real telemetry_events row carrying the real LLM output --
                    # unlike the neutral registration-only entry above, this one
                    # lets derive.py compute a genuine (not neutral-default)
                    # entropy/grounding signal from real text, since
                    # `agent.run_conversation`'s actual final response is
                    # available here.
                    _submit_telemetry(
                        allocator_did,
                        allocator["keypair"],
                        {"event": "agent_conversation", "text_output": response},
                    )
            except Exception as e:
                logger.error(f"Capital allocator's agent conversation failed: {e}")
                tool_call_error = str(e)

    summary = {
        "agents_attempted": len(agents),
        "agents_registered": sorted(agent_data.keys()),
        "sovereign_agent_addresses": {
            agent_id: data["registration"].sovereign_agent for agent_id, data in agent_data.items()
        },
    }
    if tool_call_error:
        summary["tool_call_error"] = tool_call_error
    return summary


if __name__ == "__main__":
    main()
