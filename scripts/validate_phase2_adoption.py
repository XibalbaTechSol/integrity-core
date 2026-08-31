#!/usr/bin/env python3
"""Validate an evidence ledger for the Phase II external-adoption gate.

The script does not create counterparties or infer externality. Every row must carry an
operator-attested `external_counterparty: true` flag, a non-contributor flag, a receipt-
backed transaction hash, and a positive consumed-unit count. Thresholds are explicit CLI
inputs because the whitepaper defines the gate qualitatively, not numerically.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def validate(path: Path, min_counterparties: int, min_units: int, window_days: int) -> tuple[int, int]:
    rows = []
    seen_hashes: set[str] = set()
    for line_number, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"line {line_number}: invalid JSON: {exc.msg}") from exc
        required = {"timestamp", "counterparty_id", "tx_hash", "units", "external_counterparty", "protocol_contributor"}
        missing = required - row.keys()
        if missing:
            raise ValueError(f"line {line_number}: missing {', '.join(sorted(missing))}")
        if not row["external_counterparty"] or row["protocol_contributor"]:
            raise ValueError(f"line {line_number}: row is not an eligible external counterparty")
        if not isinstance(row["tx_hash"], str) or not row["tx_hash"].startswith("0x"):
            raise ValueError(f"line {line_number}: tx_hash must be a receipt-backed 0x value")
        if row["tx_hash"] in seen_hashes:
            raise ValueError(f"line {line_number}: duplicate tx_hash")
        seen_hashes.add(row["tx_hash"])
        units = int(row["units"])
        if units <= 0:
            raise ValueError(f"line {line_number}: units must be positive")
        rows.append((parse_timestamp(row["timestamp"]), str(row["counterparty_id"]), units))

    if not rows:
        raise ValueError("ledger is empty")
    timestamps = [row[0] for row in rows]
    elapsed_days = (max(timestamps) - min(timestamps)).total_seconds() / 86_400
    counterparties = {row[1] for row in rows}
    units = sum(row[2] for row in rows)
    if elapsed_days < window_days:
        raise ValueError(f"observation window is {elapsed_days:.2f} days, below {window_days}")
    if len(counterparties) < min_counterparties:
        raise ValueError(f"only {len(counterparties)} external counterparties, below {min_counterparties}")
    if units < min_units:
        raise ValueError(f"only {units} consumed units, below {min_units}")
    return len(counterparties), units


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger", type=Path)
    parser.add_argument("--min-counterparties", type=int, required=True)
    parser.add_argument("--min-units", type=int, required=True)
    parser.add_argument("--window-days", type=int, required=True)
    args = parser.parse_args()
    try:
        counterparties, units = validate(args.ledger, args.min_counterparties, args.min_units, args.window_days)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(f"PHASE II ADOPTION EVIDENCE VALID: {counterparties} external counterparties, {units} units")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
