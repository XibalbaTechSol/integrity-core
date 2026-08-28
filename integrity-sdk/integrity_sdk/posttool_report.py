"""
The missing half of the BCC intent-vs-effect join (~/.claude/plans/velvet-giggling-quill.md).

`bcc_middleware`'s audit row already stores `intended_state_hash` on ALLOW specifically so a
later verifier can "line intent up against effect" (see that repo's app/main.py) -- this module
is that verifier's submission side, referenced but never implemented before now. Computes
nothing itself (that's `telemetry.intent.IntentInvocation.record_outcome`'s job, via
`bcc.hash_intent_payload`); this module only submits the result to integrity-oracle's
`POST /v1/audit/effect`, mirroring `bcc.submit_commitment`'s own request pattern (requests,
OTel span, 10s timeout).
"""

from __future__ import annotations

from typing import Any, Dict, Optional


def submit_effect_report(
    *,
    agent_id: str,
    intended_state_hash: str,
    effect_hash: str,
    matches: bool,
    oracle_url: str,
    timeout: int = 10,
) -> Dict[str, Any]:
    """POSTs the intent-vs-effect comparison to integrity-oracle. The oracle inserts a new,
    separate `audit_log` row (event_type="posttool_effect") rather than mutating the original
    intent row -- append-only, joined by matching `intended_state_hash` values, not by
    rewriting history. See integrity-oracle/backend/src/handlers.rs's `submit_audit_effect`.
    """
    import requests
    from .telemetry.core import get_tracer

    tracer = get_tracer("integrity_sdk.posttool_report")
    with tracer.start_as_current_span("integrity.posttool.effect_report") as span:
        span.set_attribute("integrity.intent.effect_hash", effect_hash)
        span.set_attribute("integrity.intent.matches_effect", matches)
        try:
            resp = requests.post(
                f"{oracle_url}/v1/audit/effect",
                json={
                    "agent_id": agent_id,
                    "intended_state_hash": intended_state_hash,
                    "effect_hash": effect_hash,
                    "matches": matches,
                },
                timeout=timeout,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            span.record_exception(e)
            raise


def report_intent_deviation(
    deviation: Any,
    *,
    agent_id: str,
    intended_state_hash: str,
    oracle_url: str,
    timeout: int = 10,
) -> Optional[Dict[str, Any]]:
    """Convenience wrapper around `submit_effect_report` for the common case: a caller already
    holds an `IntentDeviationResult` (from `IntentInvocation.record_outcome`) and just wants to
    report it if an effect_hash was actually computed. Returns None (does nothing) if
    `record_outcome` was never given `actual_effect_payload` -- there's nothing to report.
    """
    if deviation.effect_hash is None:
        return None
    return submit_effect_report(
        agent_id=agent_id,
        intended_state_hash=intended_state_hash,
        effect_hash=deviation.effect_hash,
        matches=bool(deviation.intent_matches_effect),
        oracle_url=oracle_url,
        timeout=timeout,
    )
