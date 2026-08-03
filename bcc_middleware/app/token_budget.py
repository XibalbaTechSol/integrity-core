"""
Rolling per-agent daily token budget enforcer.

Tracks cumulative LLM token spend per agent per UTC calendar day and denies
BCC commitments that would push an agent over its tier's daily budget.

Tier budgets (tokens/day):
    Tier 0 (unverified)   — 10,000
    Tier 1 (basic)        — 100,000
    Tier 2 (enterprise)   — 1,000,000
    Tier 3 (sovereign)    — unlimited

Scope limitation (same as circuit_breaker.py):
    Process-local only. A multi-replica deployment needs a shared store
    (Redis, Postgres). Documented here, not silently assumed away.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

logger = logging.getLogger("bcc_middleware.token_budget")

# Tier → daily token budget (-1 means unlimited)
TIER_BUDGETS: dict[int, int] = {
    0: 10_000,
    1: 100_000,
    2: 1_000_000,
    3: -1,  # sovereign — unlimited
}


def _utc_day() -> str:
    """Return the current UTC calendar day as 'YYYY-MM-DD'."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class TokenBudgetEnforcer:
    """
    Per-agent rolling daily token budget enforcer.

    Thread-safe. All state is process-local (see scope limitation above).
    """

    def __init__(self) -> None:
        # keyed by (agent_id, utc_day) → cumulative token spend
        self._spend: dict[tuple[str, str], int] = {}
        self._lock = threading.Lock()

    def get_daily_spend(self, agent_id: str) -> int:
        """Return the agent's cumulative token spend for the current UTC day."""
        today = _utc_day()
        with self._lock:
            return self._spend.get((agent_id, today), 0)

    def check_and_record(
        self, agent_id: str, tier: int, token_count: int
    ) -> tuple[bool, str | None]:
        """
        Check whether adding `token_count` to this agent's daily tally would
        exceed the tier's budget. If it would, return (False, reason_string).
        If allowed, record the spend and return (True, None).

        Args:
            agent_id:    The agent's DID string.
            tier:        The agent's verification tier (0-3).
            token_count: Tokens consumed by this action.

        Returns:
            (allowed: bool, denial_reason: str | None)
        """
        if token_count <= 0:
            return True, None

        budget = TIER_BUDGETS.get(tier, TIER_BUDGETS[0])
        if budget == -1:
            # Unlimited tier — record spend for observability, always allow
            self._record(agent_id, token_count)
            return True, None

        today = _utc_day()
        with self._lock:
            current = self._spend.get((agent_id, today), 0)
            projected = current + token_count
            if projected > budget:
                return (
                    False,
                    (
                        f"tier {tier} daily limit is {budget:,} tokens; "
                        f"current spend={current:,}, this action={token_count:,} "
                        f"(projected={projected:,} > limit={budget:,})"
                    ),
                )
            self._spend[(agent_id, today)] = projected

        return True, None

    def _record(self, agent_id: str, token_count: int) -> None:
        """Record spend without enforcement (for unlimited-tier agents)."""
        today = _utc_day()
        with self._lock:
            self._spend[(agent_id, today)] = (
                self._spend.get((agent_id, today), 0) + token_count
            )

    def reset(self) -> None:
        """Clear all spend state. Used in tests."""
        with self._lock:
            self._spend.clear()


# Process-level singleton
token_budget_enforcer = TokenBudgetEnforcer()
