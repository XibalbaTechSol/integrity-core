# Phase II external-adoption evidence

The Phase II gate is sustained licensing volume from counterparties who are not protocol
contributors. It cannot be established by Foundry tests, project-owned wallets, or synthetic
rows. `scripts/validate_phase2_adoption.py` validates an operator-supplied JSONL ledger without
inventing thresholds.

Each row must contain:

```json
{"timestamp":"2026-09-01T12:00:00Z","counterparty_id":"org-a","tx_hash":"0x...","units":10,"external_counterparty":true,"protocol_contributor":false}
```

Run it with thresholds approved for the adoption program:

```bash
python3 scripts/validate_phase2_adoption.py evidence/phase2-licensing.jsonl \
  --min-counterparties 2 --min-units 100 --window-days 30
```

The ledger must be assembled from live receipts and counterparty records. Retain the source
receipts, signer/account relationship, commercial agreement or equivalent counterparty proof,
and the exact command output. A passing validator confirms ledger consistency against the chosen
thresholds; it does not independently prove that an organization is unaffiliated. That status
requires a separate human-reviewed evidence record.
