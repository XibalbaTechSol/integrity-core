"""Billing helpers that need no network: webhook idempotency and receipt classification.

`classify_for_billing` reads a gate receipt the same way the local AIS scorer does. Both import the
exclusion set from `integrity_sdk.core.ais_local`, so a reason code excluded from the score is excluded
from the bill and the two cannot drift (Shield plans & metering design §2):

* `AIS_ZONE_RESTRICTED` -- the zone mask's own block; billing it would charge for the paid feature's
  denials (`excluded_mask`);
* gate faults (`INTEGRITY_EVALUATOR_ERROR`, `_MALFORMED_DECISION`, `_NO_PACK`) -- our failures, not the
  customer's tool calls (`excluded_fault`);
* everything else, including `INTEGRITY_NO_MATCH`, is a governed tool call (`billable`).
"""
from __future__ import annotations

from typing import Any, Mapping

from ..core.ais_local import GATE_FAULT_REASON_CODES, REASON_ZONE_RESTRICTED

BILLABLE = "billable"
EXCLUDED_MASK = "excluded_mask"
EXCLUDED_FAULT = "excluded_fault"
BILLING_CLASSES = (BILLABLE, EXCLUDED_MASK, EXCLUDED_FAULT)

STRIPE_EVENTS_DDL = "CREATE TABLE IF NOT EXISTS stripe_events (id TEXT PRIMARY KEY, processed_at INTEGER NOT NULL)"


def classify_for_billing(receipt: Mapping[str, Any]) -> str:
    """`billable`, `excluded_mask` or `excluded_fault` for one gate receipt."""
    reason = receipt.get("reason_code")
    if reason == REASON_ZONE_RESTRICTED:
        return EXCLUDED_MASK
    if reason in GATE_FAULT_REASON_CODES:
        return EXCLUDED_FAULT
    return BILLABLE


def ensure_stripe_events_table(conn: Any) -> None:
    conn.execute(STRIPE_EVENTS_DDL)


def record_once(conn: Any, event_id: str, *, processed_at: int) -> bool:
    """Claim webhook `event_id`. True the first time, False on every redelivery.

    Call inside the same transaction as the event's side effects, so a crash rolls back both and the
    redelivered event is processed again. Works on sqlite3 and on DB-API drivers with `?` paramstyle.
    """
    if not isinstance(event_id, str) or not event_id.startswith("evt_"):
        raise ValueError("Stripe event ids start with evt_")
    cursor = conn.execute("INSERT OR IGNORE INTO stripe_events (id, processed_at) VALUES (?, ?)",
                          (event_id, int(processed_at)))
    return cursor.rowcount == 1
