"""
Per-email login lockout: repeated failed `POST /auth/login` attempts for the
same email trip a temporary lockout, independent of any single password
check. Mirrors `bcc_middleware/app/circuit_breaker.py`'s per-agent-id
pattern -- same shape (in-memory counter + timed lockout, cleared on
success or once the lockout window naturally expires), applied to a
different key space (login email instead of agent DID).

In-memory, single-process -- same accepted tradeoff as that module today; a
multi-replica deployment would need to move this to Redis (already present
elsewhere in this monorepo's docker-compose topology).
"""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class _AttemptState:
    failure_count: int = 0
    locked_out_until: float | None = None  # monotonic time.time() seconds


class LoginRateLimiter:
    def __init__(self, failure_threshold: int = 5, lockout_duration_seconds: int = 300):
        self.failure_threshold = failure_threshold
        self.lockout_duration_seconds = lockout_duration_seconds
        self._attempts: dict[str, _AttemptState] = {}

    def is_locked_out(self, email: str) -> bool:
        state = self._attempts.get(email.lower())
        if state is None or state.locked_out_until is None:
            return False
        if time.time() >= state.locked_out_until:
            # Lockout has naturally expired -- clear it so the next attempt
            # gets a clean slate rather than an instantly-re-triggered lockout.
            state.locked_out_until = None
            state.failure_count = 0
            return False
        return True

    def lockout_remaining_seconds(self, email: str) -> float:
        state = self._attempts.get(email.lower())
        if state is None or state.locked_out_until is None:
            return 0.0
        return max(0.0, state.locked_out_until - time.time())

    def record_failure(self, email: str) -> None:
        key = email.lower()
        state = self._attempts.setdefault(key, _AttemptState())
        state.failure_count += 1
        if state.failure_count >= self.failure_threshold:
            state.locked_out_until = time.time() + self.lockout_duration_seconds

    def record_success(self, email: str) -> None:
        self._attempts.pop(email.lower(), None)

    def reset(self, email: str | None = None) -> None:
        """Test/admin hook. Resets one email's attempt state, or all of them."""
        if email is None:
            self._attempts.clear()
        else:
            self._attempts.pop(email.lower(), None)
