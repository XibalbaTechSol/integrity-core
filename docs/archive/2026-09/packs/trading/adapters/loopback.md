# Loopback BrokerPort Adapter

**Pack:** `trading@0.1.0`  
**Status:** Draft / test-only  
**Purpose:** Deterministic in-process `BrokerPort` implementation for exercising Integrity trading-pack admission, working-risk meters, kill behavior, reconciliation, and evidence. It is not a matching engine, price feed, broker emulator, or production adapter.

## 1. Contract

The adapter implements the venue-agnostic `BrokerPort` interface:

```text
submit(Order)         -> Ack | Reject
replace(Order)        -> Ack | Reject
cancel(Cancel)        -> Ack | Reject
cancel_all(CancelAll) -> Ack | Partial | Reject
subscribe_exec(sink)
subscribe_drop(sink)
```

The adapter MUST emit `Exec` and independent `Drop` messages for every accepted lifecycle transition. `Drop` is delivered through a distinct sink and sequence counter, even though both messages originate from the same test process. Tests MUST be able to suppress, delay, duplicate, or alter `Drop` independently of `Exec`.

## 2. Determinism

The adapter has no clock, RNG, network, order book, or external mark feed. Every result is determined by the submitted `Order`, the configured `Scenario`, and the adapter state.

```text
AdapterState = {
  orders: Map<ClOrdId, WorkingOrder>,
  exec_seq: uint64,
  drop_seq: uint64,
  scenario: Scenario,
  account_kill_epoch: uint64,
  events: Event[]
}
```

A test supplies timestamps, marks, and settlement values explicitly. The adapter MUST NOT read system time.

## 3. Inputs

### 3.1 Order

The adapter accepts canonical `BrokerPort.Order` fields:

```yaml
cl_ord_id: bytes32
orig_cl_ord_id: bytes32 | null
agent_id: AgentId
account: CAIP10
cluster_id: bytes32
algo_id: bytes32
session_id: bytes32
side: buy | sell
ord_type: market | limit | stop | reduce_only
tif: day | ioc | fok | gtc
qty: uint256
px: uint256 | null
instrument: { id: bytes32, settlement_asset: ADDR }
notional: uint256
kill_epoch: uint64
mark: { px: uint256, ts: uint64, signer: ADDR }
reduce: bool
ext: bytes
```

The caller MUST calculate `notional` and the test MUST assert it is consistent with the chosen price convention. The loopback adapter does not infer a price from an order book.

### 3.2 Scenario

```yaml
name: string
mode: reject | full_fill | partial_fill | accept_working | cancel_ack | mismatch
fill_qty: uint256             # required for partial_fill
fill_px: uint256 | null       # explicit; required for a fill
fee: uint256                  # default 0
exec_delay_steps: uint64      # deterministic queue turns
drop_delay_steps: uint64
drop_behavior: match | suppress | duplicate | mutate
mutation:
  field: last_qty | last_px | fee | status | cl_ord_id
  value: any
cancel_all_result: ack | partial | reject
```

`mismatch` is intentionally unsafe: it creates a divergence between `Exec` and `Drop`, or between the declared settlement and a supplied settlement observation. It exists to test `drop_copy_mismatch` and kill behavior. A production adapter MUST NOT implement this mode.

## 4. Lifecycle

### 4.1 Submit

1. Caller runs Rego and hook preview. A test MUST NOT call `submit` when `V = 0`, except to prove that the adapter is not the enforcement boundary.
2. Caller reserves projected working risk in the hook/account state: `gross`, `net:{instrument}`, `open_count`, `orders:{window}`, and `msgs:{window}`.
3. `submit(Order)` rejects duplicate `cl_ord_id` within the canonical Integrity domain.
4. In `reject` mode, return `Reject`; no working order and no fill are created. The caller rolls back projected working risk.
5. In every other mode, store `WorkingOrder`, return `Ack`, and enqueue the configured `Exec` and `Drop`.
6. On delivery of `Exec`, caller performs post-check, commits or releases meters, records settlement, and emits the evidence package.
7. On delivery of `Drop`, caller reconciles it with the corresponding `Exec`.

### 4.2 Replace

`replace(Order)` requires an existing live `orig_cl_ord_id`. It is modeled as an atomic release of old projected risk followed by reservation of new projected risk. If the new order would violate any `g_i`, the replacement MUST NOT reach `BrokerPort`.

A replacement that changes `side`, `instrument.id`, `account`, `agent_id`, `cluster_id`, or `algo_id` MUST reject. Such a change is a new order.

### 4.3 Cancel

`cancel(Cancel)` marks a live order canceled and emits `Exec{status:canceled}` plus a corresponding `Drop`. Cancellation releases remaining working-risk projection. A cancel of an unknown or terminal order returns `Reject`.

### 4.4 Cancel all

`cancel_all(CancelAll)` selects orders by account and optional `session_id` / `algo_id`. The configured `cancel_all_result` controls behavior:

- `ack`: all selected live orders emit canceled executions.
- `partial`: only the first selected live order is canceled; all remaining orders stay live.
- `reject`: nothing changes.

Tests MUST treat cancel-all as best effort. A kill remains effective even if cancel-all rejects: no new risk-increasing order may pass `kill_fresh`.

## 5. Fill semantics

| Mode | Ack | Exec | Working order after Exec | Meter expectation |
|---|---|---|---|---|
| `reject` | No | `rejected` | None | Roll back projected risk |
| `full_fill` | Yes | `filled`, `last_qty = qty` | Terminal | Convert working risk to settled position / cash |
| `partial_fill` | Yes | `partial`, `last_qty = fill_qty` | `leaves_qty = qty - fill_qty` | Commit filled portion; retain residual working risk |
| `accept_working` | Yes | `new` only | Live | Retain full projected risk |
| `cancel_ack` | Yes | `canceled` | Terminal | Release remaining projected risk |
| `mismatch` | Yes | Scenario-defined | Scenario-defined | Reconciliation MUST kill or escalate |

For a fill, the expected declared execution value is:

```text
declared_exec_value = last_qty * last_px
expected_settlement_delta = declared_exec_value + fee
```

The caller chooses the sign according to `side`; the test fixture MUST declare that sign explicitly. The adapter does not move tokens or fiat. It emits only execution facts.

## 6. Independent drop-copy reconciliation

For each terminal or partial `Exec`, the oracle/reconciler MUST compare the independent `Drop` with:

```text
cl_ord_id, exec_id, status, last_qty, cum_qty, leaves_qty,
last_px, avg_px, fee, fee_asset, ts
```

A missing `Drop` beyond the test’s declared cursor deadline, a duplicate with conflicting content, or a mismatch in any conservation-relevant field MUST produce:

```text
Decision = Escalate{class: drop_copy_mismatch}
account.kill_epoch += 1
```

The test may permit duplicate **identical** drops; reconciliation MUST be idempotent on `(cl_ord_id, exec_id, drop_sequence)`.

## 7. Hook and pack integration

Before an order reaches the adapter, the test fixture MUST construct the projected post-state and evaluate at least:

- `principal_approved`
- `kill_fresh`
- `broker_allowed`
- `instrument_allowed` / `instrument_not_denied`
- `order_notional`
- `gross`
- `net`
- `open_count`
- `order_throttle` and `msg_throttle`
- `mark_fresh` and `px_band` when risk increases
- `day_loss`, `drawdown`, and `self_deal` as configured
- `conservation` after an execution is observed

The loopback adapter MUST NOT bypass a failed hook outcome. If a test intentionally submits after `V = 0`, label it `boundary_negative_test`; its expected result is that the **adapter** can accept but the system under test must not call it in normal flow.

## 8. Required conformance scenarios

### LBA-01: Accepted full fill

- Approved principal; allowed broker and instrument; fresh mark.
- `notional < max_order_notional`; projected gross/net/open remain within caps.
- Scenario: `full_fill`; fee explicitly set.
- Assert: `Ack`, one filled `Exec`, one matching `Drop`, conservation passes, evidence head advances.

### LBA-02: Hook rejects oversized order

- Set `order_notional > max_order_notional`.
- Assert: `V = 0`; `BrokerPort.submit` is never invoked; state and meters unchanged.

### LBA-03: Pending order counts toward gross

- Scenario: `accept_working`.
- Submit order A below cap; retain it working.
- Submit B such that A + B exceeds `max_gross_notional`.
- Assert: B fails `gross`; A remains live; no B adapter call.

### LBA-04: Partial fill retains residual exposure

- Scenario: `partial_fill`, `fill_qty < qty`.
- Assert: filled portion is settled; `leaves_qty` remains in working gross/net/open; matching Drop reconciles.

### LBA-05: Kill blocks new risk

- Submit A under `accept_working`.
- Bump account `kill_epoch` via operator or loss threshold.
- Attempt B with old epoch.
- Assert: `kill_fresh` fails; B is not submitted.
- Issue cancel-all; run once with `ack`, once with `reject`. In both cases B remains blocked.

### LBA-06: Reduce-only during stale mark

- Use a mark older than `mark_max_age_s`; set `allow_reduce_on_stale = 1`.
- Risk-increasing order fails `mark_fresh`.
- An order proven to reduce `abs(net:{instrument})` passes only if all other constraints pass.

### LBA-07: Drop mismatch kills

- Scenario: `mismatch`, mutate `last_px`, `fee`, or `last_qty` in Drop.
- Assert: reconcile emits `drop_copy_mismatch`; `kill_epoch` increments; a later old-epoch order fails.

### LBA-08: Duplicate and replay rejection

- Submit same `cl_ord_id` twice in one domain.
- Assert: second call rejects before risk reservation.
- Deliver duplicate identical Drop. Assert idempotent evidence.
- Deliver duplicate conflicting Drop. Assert mismatch + kill.

### LBA-09: Self-deal ceiling

- Two approved agents in the same pinned `cluster_id` submit opposing working orders on one instrument.
- Assert: projected overlap above `self_deal_qty` fails before adapter invocation.

### LBA-10: Replacement is atomic

- Submit working A.
- Replace A with a size that violates gross.
- Assert: original A remains live and unchanged; replacement never reaches adapter.

## 9. Test fixture shape

```yaml
fixture:
  account:
    kill_epoch: 7
    principal_approved: true
  params:
    max_order_notional: 100000000
    max_gross_notional: 250000000
    max_net_per_instrument: 1000
    max_open_orders: 4
    mark_max_age_s: 60
  marks:
    - { instrument: BTC-USD, px: 100000, ts: 1000, signer: mark-signer-1 }
  scenario:
    name: partial-buy
    mode: partial_fill
    fill_qty: 3
    fill_px: 100000
    fee: 100
    exec_delay_steps: 1
    drop_delay_steps: 2
    drop_behavior: match
  order:
    cl_ord_id: 0x...
    instrument: { id: BTC-USD, settlement_asset: USDC }
    side: buy
    qty: 5
    px: 100000
    notional: 500000
    kill_epoch: 7
```

A real fixture MUST use canonical bytes32 values and state exact unit scaling. The example is illustrative only.

## 10. Non-goals

- Simulating price-time priority, an order book, margin, borrow, funding, corporate actions, venue outages, network retries, or market data.
- Validating FIX tags, broker credentials, EIP-712 signatures, or venue-specific settlement.
- Providing production matching, market marks, surveillance, or a substitute for broker drop copy.

The loopback adapter is useful precisely because it is small: it proves that Integrity’s box, meter lifecycle, kill semantics, and evidence/reconciliation path agree before a real broker adapter introduces transport and venue complexity.
