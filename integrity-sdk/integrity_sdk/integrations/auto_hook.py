"""
Auto-hook integration: global zero-code instrumentation hook for Python agent
runtimes and subagent execution frameworks (such as Antigravity MoE, LangChain,
and custom subprocesses).

Enabling `enable_auto_hooks()` will:
1. Initialize the global `IntegrityClient` and OTel telemetry exporter.
2. Auto-patch LLM/Agent execution frames to capture spans and report telemetry.
"""

from __future__ import annotations

import logging
import os
import sys
import functools
import time
from typing import Any, Callable, Optional

from ..client import IntegrityClient
from ..telemetry.core import init_telemetry, get_tracer
from ..telemetry.tracing import traceable

logger = logging.getLogger("integrity_sdk.integrations.auto_hook")

_hook_installed = False
_global_client: Optional[IntegrityClient] = None


def enable_auto_hooks(
    agent_id: Optional[str] = None,
    oracle_url: Optional[str] = None,
    otlp_endpoint: Optional[str] = None,
    auto_patch_antigravity: bool = True,
) -> IntegrityClient:
    """
    Installs global automatic telemetry hooks for the current process.
    Safe to call multiple times — only the first execution initializes hooks.
    """
    global _hook_installed, _global_client
    if _hook_installed and _global_client is not None:
        return _global_client

    agent_id = agent_id or os.getenv("INTEGRITY_AGENT_ID", "xibalba-agent")
    oracle_url = oracle_url or os.getenv("ORACLE_URL", "http://localhost:8080")
    otlp_endpoint = otlp_endpoint or os.getenv("OTLP_GRPC_ADDR", "localhost:4317")

    # 1. Init OTel telemetry provider
    init_telemetry(agent_id=agent_id, endpoint=otlp_endpoint)

    # 2. Init global Integrity client
    _global_client = IntegrityClient(agent_id=agent_id, oracle_url=oracle_url)

    # 3. Patch Antigravity MoE / Subagent execution if available in process
    if auto_patch_antigravity:
        _patch_antigravity_moe(_global_client)

    _hook_installed = True
    logger.info(f"Integrity SDK Auto-Hooks enabled for agent_id='{agent_id}' -> Oracle='{oracle_url}'")
    return _global_client


def _patch_antigravity_moe(client: IntegrityClient) -> None:
    """
    Intercepts Antigravity MoE `Subagent.execute_task` calls to auto-trace
    and submit telemetry reports for each execution step.
    """
    try:
        import antigravity_moe.core as moe_core
        if hasattr(moe_core, "Subagent") and not getattr(moe_core.Subagent, "_integrity_patched", False):
            orig_execute = moe_core.Subagent.execute_task

            @functools.wraps(orig_execute)
            async def patched_execute_task(self, task_description: str) -> Any:
                start_time = time.time()
                tracer = get_tracer("integrity_sdk.auto_hook")
                with tracer.start_as_current_span(f"subagent:{self.name}") as span:
                    span.set_attribute("integrity.agent.id", client.agent_id)
                    span.set_attribute("integrity.subagent.name", getattr(self, "name", "unknown"))
                    span.set_attribute("integrity.subagent.role", getattr(self, "role", "unknown"))

                    try:
                        result = await orig_execute(self, task_description)
                        latency_ms = int((time.time() - start_time) * 1000)

                        # Submit telemetry envelope to Oracle
                        client.report_transaction(
                            agent_id=client.agent_id,
                            performer_address=client.agent_wallet_address or "0x0000000000000000000000000000000000000000",
                            deal_amount=0.0,
                            accuracy_score=1.0,
                            latency_ms=latency_ms,
                        )
                        return result
                    except Exception as exc:
                        latency_ms = int((time.time() - start_time) * 1000)
                        span.record_exception(exc)
                        client.report_transaction(
                            agent_id=client.agent_id,
                            performer_address=client.agent_wallet_address or "0x0000000000000000000000000000000000000000",
                            deal_amount=0.0,
                            accuracy_score=0.0,
                            latency_ms=latency_ms,
                        )
                        raise

            moe_core.Subagent.execute_task = patched_execute_task
            moe_core.Subagent._integrity_patched = True
            logger.info("Successfully auto-patched Antigravity MoE Subagent framework.")
    except ImportError:
        pass
