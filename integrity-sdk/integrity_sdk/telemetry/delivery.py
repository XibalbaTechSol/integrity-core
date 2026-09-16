"""Bounded, idempotency-aware delivery helpers for SDK transports."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping


@dataclass(frozen=True)
class DeliveryReceipt:
    event_id: str
    destination: str
    attempt: int
    timestamp: str
    status: str
    retry_state: str
    error: str | None = None
    dead_lettered: bool = False

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def deliver_with_retry(
    event: Mapping[str, Any], *, destination: str,
    send: Callable[[Mapping[str, Any], str], Any], max_attempts: int = 3,
    base_delay: float = 0.0, sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], str] | None = None,
) -> list[DeliveryReceipt]:
    """Deliver with bounded retries and event_id as the idempotency key."""
    if not event.get("event_id"):
        raise ValueError("event_id is required for delivery")
    if max_attempts < 1:
        raise ValueError("max_attempts must be positive")
    timestamp = now or (lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    receipts: list[DeliveryReceipt] = []
    for attempt in range(1, max_attempts + 1):
        try:
            send(event, str(event["event_id"]))
        except Exception as exc:
            final = attempt == max_attempts
            receipts.append(DeliveryReceipt(str(event["event_id"]), destination, attempt, timestamp(), "dead-lettered" if final else "failed", "dead-lettered" if final else "retrying", str(exc), final))
            if final:
                return receipts
            if base_delay:
                sleep(base_delay * (2 ** (attempt - 1)))
        else:
            receipts.append(DeliveryReceipt(str(event["event_id"]), destination, attempt, timestamp(), "acknowledged", "complete"))
            return receipts
    return receipts
