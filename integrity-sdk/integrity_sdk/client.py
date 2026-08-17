"""
IntegrityClient: the SDK's telemetry client — the piece that ties the OTel
run-tree tracing (telemetry/tracing.py), the edge batcher (batcher.py), the
AIS-signal derivation (telemetry/derive.py), and the oracle's
`POST /v1/telemetry/ingest` endpoint together.

Before this module existed, `telemetry/tracing.py` referenced
`client._record_trace_run(...)`, `integrations/openai_integrity.py` and
`integrations/langchain_callback.py` referenced `client.log_telemetry(...)`,
and `telemetry/metrics.py`'s docstring referenced `client.py`'s
`_process_and_send` — all dangling references to a client that was never
written in this rewrite. This closes them: those are the real methods below.

Telemetry here is best-effort observability, NOT part of the trust chain
(unlike the BCC/OPA/ZK/attestation paths, which fail closed) — a flush that
can't reach the oracle logs a warning and re-queues, it never crashes the
agent's actual work. That asymmetry is deliberate and matches
bcc_middleware's own fail-closed-vs-best-effort split.
"""

from __future__ import annotations

import atexit
import logging
import os
import threading
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests

from . import bcc
from .batcher import TelemetryBatcher
from .collection import CollectionConfig
from .did import Keypair
from .telemetry import core as telemetry_core, derive, intent as intent_module, metrics as metrics_module, tracing

#: Version of the signed telemetry envelope this client emits. Pinned in
#: `docs/INTERFACE_CONTRACT.md` §4.2a.
#:
#: It lives INSIDE the signed object, so it is covered by the signature and cannot be
#: rewritten in transit to make the oracle reinterpret a payload under different rules.
#:
#: An envelope with no `schema_version` at all is the pre-versioning shape and remains
#: valid forever: signed payloads are evidence, and old evidence has to stay verifiable. The
#: oracle therefore reconstructs the signable bytes WITHOUT the key when a request omits it
#: — serializing it as `null` instead would change the canonical bytes and break every
#: historical signature.
TELEMETRY_SCHEMA_VERSION = 1


logger = logging.getLogger("integrity_sdk.client")


class IntegrityClient:
    """
    Buffers per-inference telemetry and finished trace runs, derives the four
    AIS input signals from a batch, and flushes them to integrity-oracle.

    Deliberately does NOT block the agent's hot path: `log_telemetry` and
    `_record_trace_run` only append to an in-memory queue (see batcher.py);
    the network POST happens in `flush_telemetry`, which a caller invokes
    explicitly (or which fires automatically once the batcher's size/time
    threshold trips, checked on each `log_telemetry`).
    """

    def __init__(
        self,
        agent_id: str,
        oracle_url: Optional[str] = None,
        *,
        auto_flush: bool = True,
        batch_size_limit: int = 50,
        flush_interval_sec: float = 5.0,
        max_queue_size: int = 10_000,
        background_flush: bool = True,
        collection: Optional[CollectionConfig] = None,
        keypair: Optional[Keypair] = None,
        bcc_nonce_store: Optional[Any] = None,
        otlp_endpoint: Optional[str] = None,
        enable_otel_export: bool = True,
    ):
        self.agent_id = agent_id
        self.oracle_url = (oracle_url or os.getenv("ORACLE_URL", "http://localhost:8080")).rstrip("/")
        # FIXED 2026-07-16 — `client.traceable(...)`/`trace_run(..., client=self)`
        # is this SDK's own documented "recommended general-purpose tracing
        # API" (see telemetry/tracing.py's module docstring), and it opens a
        # REAL OTel span via `get_tracer(...).start_as_current_span(...)` on
        # every call — but nothing ever installed a real TracerProvider/
        # exporter before this fix. `get_tracer` silently returns OTel's
        # default no-op tracer in that state, so every span this API ever
        # produced was discarded before it ever reached the process boundary,
        # let alone the oracle's `otel_spans` table — real nesting
        # (`contextvars`-propagated parent/child), real PHI redaction, real
        # attributes, all computed and then thrown away. Confirmed by
        # actually tracing an agent run end-to-end and finding zero rows in
        # the oracle's `otel_spans` table despite no errors anywhere.
        # `telemetry/core.py::init_telemetry` is the one thing that installs
        # a real exporter, but it was only ever called by
        # `telemetry/mlflow_tracing.py`'s optional autolog path — never by
        # this client, despite `agent_id` (everything `init_telemetry` needs
        # besides an endpoint) being known right here at construction time.
        # Safe to call unconditionally: `init_telemetry` is idempotent
        # (module-level `_initialized` guard, first call wins) and, per its
        # own docstring, a missing/unreachable OTLP collector fails the
        # background export silently rather than raising — matches this
        # class's own "telemetry is best-effort, never blocks the agent's
        # real work" rule stated above. The OTLP gRPC collector is the same
        # oracle-backend process that serves `oracle_url`'s HTTP API (see
        # docker-compose.yml — one container, two ports), so deriving the
        # OTLP host from `oracle_url` rather than requiring a second URL a
        # caller has to remember to keep in sync is a real architectural
        # fact of this deployment, not a guess. `enable_otel_export=False`
        # opts out entirely (e.g. a test that wants to assert on the
        # no-op-tracer state itself); `otlp_endpoint=` overrides the derived
        # host:4317 default for a non-standard topology.
        if enable_otel_export:
            endpoint = otlp_endpoint or f"{urlparse(self.oracle_url).hostname or 'localhost'}:4317"
            telemetry_core.init_telemetry(agent_id=agent_id, endpoint=endpoint)
        # Resolved from INTEGRITY_COLLECTION_PROFILE unless passed explicitly. Governs the
        # content layer only (L3) — structural fields the protocol scores on are always
        # collected, so narrowing the profile never silently weakens a score.
        self._collection = collection or CollectionConfig.from_env()
        self._batcher = TelemetryBatcher(
            batch_size_limit=batch_size_limit,
            flush_interval_sec=flush_interval_sec,
            max_queue_size=max_queue_size,
        )
        self._trace_runs: List[Dict[str, Any]] = []
        self._auto_flush = auto_flush
        # Monotonic per-flush nonce, so the oracle's replay protection (see
        # db.rs's insert_telemetry_event nonce check) has a strictly-increasing
        # value per agent. Starts at 0 and is re-synced from the oracle's
        # persisted last_nonce before the first real flush (see
        # `_sync_nonce_from_oracle`) — a fresh client instance after a process
        # restart otherwise has no way to know an earlier instance already
        # advanced the oracle's counter, and would replay a stale nonce on
        # every flush forever (PRODUCTION_GAPS.md Sec3).
        self._nonce = 0
        self._nonce_synced = False
        # Tri-state, set by `_sync_nonce_from_oracle`'s same GET: `None` = not yet
        # checked or the check was inconclusive (oracle unreachable — best-effort,
        # matches this class's existing posture), `True` = oracle confirmed this
        # agent_id exists, `False` = oracle returned 404 (confirmed unregistered).
        # `flush_telemetry` refuses to send anything while this is `False` — by
        # default, no telemetry payload leaves the process for an agent the oracle
        # has positively told us it doesn't know about.
        self._registered: Optional[bool] = None
        # Escape-hatch metric recording (telemetry/metrics.py) — was fully
        # built but never actually wired into this client (see flush_telemetry's
        # docstring on where its drained output now goes). Fixed here rather
        # than left as another dangling reference.
        self._metrics = metrics_module.MetricsRegistry()
        # Optional: only needed to call `invoke_intent`. `keypair` signs BCC
        # commitments (see bcc.py — a DIFFERENT keypair concern from the
        # telemetry-envelope signing gap `flush_telemetry` already documents
        # as unresolved); `bcc_nonce_store` is a `bcc.NonceStore` providing
        # the BCC-specific monotonic nonce, which is intentionally a SEPARATE
        # counter from `self._nonce` above (docs/INTERFACE_CONTRACT.md keeps
        # the BCC replay-protection nonce and the telemetry-ingestion nonce
        # as distinct spaces — conflating them would let a used-up BCC nonce
        # block an unrelated telemetry flush, or vice versa).
        self._keypair = keypair
        self._bcc_nonce_store = bcc_nonce_store

        # --- F3: the interval flush has to be driven by a clock, not by the next event ---
        #
        # `flush_interval_sec` existed but nothing consulted it except `log_telemetry`, so the
        # interval only elapsed *when another event arrived*. Two consequences, both bad for a
        # collector: an agent that goes quiet never flushed its tail — the moment right before
        # it stopped, which is exactly the interesting one — and a short-lived process lost
        # everything unless it happened to call `flush_telemetry` by hand. That is why the
        # Xibalba session hooks flush manually and why the OTel exporter needed an explicit
        # force_flush bolted on.
        self._stop_event = threading.Event()
        self._flusher: Optional[threading.Thread] = None
        # Tied to auto_flush so a caller that opted out of implicit flushing (every unit test,
        # and any caller wanting deterministic batches) does not silently get a thread anyway.
        if background_flush and auto_flush:
            self._flusher = threading.Thread(
                target=self._background_flush_loop,
                name=f"integrity-flusher-{agent_id}",
                daemon=True,  # never block interpreter exit; atexit below handles the tail
            )
            self._flusher.start()
            atexit.register(self._flush_on_exit)

    def _background_flush_loop(self) -> None:
        """Wakes on a cadence and flushes when the batcher says it is due.

        Polls at a fraction of the interval so a due flush is not delayed by up to a full
        interval, and waits on an Event rather than sleeping so `close()` returns promptly
        instead of blocking for the remainder of a tick.
        """
        poll = max(0.1, self._batcher.flush_interval_sec / 4)
        while not self._stop_event.wait(poll):
            try:
                if self._batcher.should_flush():
                    self.flush_telemetry()
            except Exception as exc:  # noqa: BLE001
                # Never let a telemetry failure kill the thread — a dead flusher would mean
                # silent data loss for the rest of the process's life, which is worse than
                # the failure being retried on the next tick.
                logger.warning("background telemetry flush failed: %r", exc)

    def _flush_on_exit(self) -> None:
        """Best-effort tail flush at interpreter shutdown.

        Registered via atexit, so a short-lived agent no longer loses its final batch. Errors
        are swallowed deliberately: raising here would turn a telemetry hiccup into a nonzero
        exit status for the host process, and telemetry is observability, not the agent's work.
        """
        self._stop_event.set()
        try:
            while self._batcher.queue_depth() > 0:
                if not self.flush_telemetry():
                    break  # unreachable oracle — stop rather than spin at shutdown
        except Exception as exc:  # noqa: BLE001
            logger.debug("exit-time telemetry flush failed: %r", exc)

    def close(self) -> None:
        """Stop the background flusher and flush what remains.

        Idempotent, and safe to call even when no flusher was started. Callers that manage
        lifetime explicitly (a test, a worker that finishes) should prefer this over relying
        on interpreter exit.
        """
        self._stop_event.set()
        if self._flusher is not None and self._flusher.is_alive():
            self._flusher.join(timeout=self._batcher.flush_interval_sec + 1.0)
        self._flush_on_exit()

    def log_telemetry(
        self,
        metadata: Dict[str, Any],
        *,
        entropy: Optional[float] = None,
        grounding: Optional[float] = None,
    ) -> None:
        """Append one telemetry entry to the batch. `metadata` carries the
        raw per-call context (completion text, token usage, model, framework,
        etc — see integrations/); `entropy`/`grounding` are optional
        pre-computed signals an integration may supply if it already had the
        completion text at hand (see derive.py's `_entry_entropy`)."""
        # Applied here rather than at flush time: content the profile withholds must never
        # enter the queue at all, or a crash between log and flush could still leak it from
        # memory, and a queue dump would contain what the operator said not to collect.
        entry: Dict[str, Any] = {"metadata": self._collection.apply(metadata)}
        if entropy is not None:
            entry["entropy"] = entropy
        if grounding is not None:
            entry["grounding"] = grounding
        self._batcher.add_telemetry(entry)

        if self._auto_flush and self._batcher.should_flush():
            self.flush_telemetry()

    def _record_trace_run(self, run: Dict[str, Any]) -> None:
        """Called by telemetry/tracing.py's `trace_run`/`traceable` when a run
        finishes, if this client was passed in. Buffers the finished run so it
        rides along on the next telemetry flush as part of the OTel span
        payload."""
        self._trace_runs.append(run)

    def traceable(self, name: Optional[str] = None, run_type: str = "chain"):
        """Pre-bound convenience wrapper over telemetry/tracing.py's
        `traceable`, with this client already wired in as the trace sink — the
        form that module's own docstring recommends callers prefer."""
        return tracing.traceable(name=name, run_type=run_type, client=self)

    def define_metric(self, name: str, *, aggregation: str = "last", unit: Optional[str] = None, description: Optional[str] = None) -> None:
        """Pre-bound convenience over telemetry/metrics.py's `MetricsRegistry.define` —
        optional; `record_metric` auto-registers an implicit definition on first use."""
        self._metrics.define(metrics_module.MetricDefinition(name=name, aggregation=aggregation, unit=unit, description=description))

    def record_metric(self, name: str, value: float, tags: Optional[Dict[str, str]] = None) -> None:
        """
        Pre-bound convenience over telemetry/metrics.py's `MetricsRegistry.record`.
        Recorded values are drained and attached to the `otel_spans` array on
        the next `flush_telemetry` call (see that method) — this is the
        open-ended escape hatch for anything beyond the four fixed AIS
        signals, e.g. `IntentInvocation.record_outcome`'s plan-adherence score.
        """
        self._metrics.record(name, value, tags)

    def invoke_intent(
        self,
        *,
        intent_type: str,
        intent_payload: Dict[str, Any],
        goal: Optional[str] = None,
        plan: Optional[List[str]] = None,
        planned_action: Optional[Dict[str, Any]] = None,
        policy_scope: Optional[List[str]] = None,
        reasoning: Optional[str] = None,
        covered_entity_address: Optional[str] = None,
    ):
        """
        Pre-bound convenience over telemetry/intent.py's `invoke_intent`, with
        this client's `keypair`/`bcc_nonce_store` (see `__init__`) and `self`
        already wired in — the same "same function, pre-bound to self" pattern
        `traceable` above already establishes. Raises `RuntimeError` if this
        client wasn't constructed with both `keypair` and `bcc_nonce_store` —
        BCC commitments cannot be built or nonce-tracked without them, and
        this fails loudly rather than silently skipping the intent gate.
        """
        if self._keypair is None or self._bcc_nonce_store is None:
            raise RuntimeError(
                "invoke_intent requires this IntegrityClient to have been constructed with "
                "both keypair= and bcc_nonce_store= (see bcc.NonceStore) — neither was provided."
            )
        return intent_module.invoke_intent(
            intent_type=intent_type,
            intent_payload=intent_payload,
            keypair=self._keypair,
            nonce=self._bcc_nonce_store.next(),
            agent_id=self.agent_id,
            goal=goal,
            plan=plan,
            planned_action=planned_action,
            policy_scope=policy_scope,
            reasoning=reasoning,
            covered_entity_address=covered_entity_address,
            client=self,
        )

    def _sync_nonce_from_oracle(self) -> None:
        """
        Best-effort: reads this agent's persisted `last_nonce` from
        `GET /v1/agent/{id}` (the same field `db::insert_telemetry_event`'s
        replay check compares against) and adopts it as this client's
        starting point, so a freshly-constructed client (e.g. after a process
        restart) doesn't replay a nonce an earlier instance already used. A
        failure here (oracle unreachable, agent not yet registered) is logged
        and swallowed, not raised — `self._nonce` simply stays at whatever it
        already was, matching this module's overall best-effort posture for
        telemetry (see module docstring). Always marks `_nonce_synced = True`
        regardless of outcome, so a persistently-unreachable oracle doesn't
        make every single flush pay a redundant GET.

        Also sets `self._registered` from this same response, rather than issuing
        a second GET purely to check registration: a 404 here means the oracle has
        no row for `self.agent_id` at all, which is exactly what `flush_telemetry`
        needs to know before it sends anything (see that method and `self._registered`'s
        own docstring in `__init__`).

        **Must read the response's `oracle_registered` field, not just the HTTP status.**
        `GET /v1/agent/{id}` returns a real `200` for a DID that resolves live on-chain
        even when it has never been registered against THIS oracle (`backend::handlers
        ::get_agent`'s chain-backfill fallback, `primitives_source: "chain-backfill"`) —
        that DID still gets `AgentNotFound` from `ingest_telemetry`/`compute_ais_for_agent`,
        which check a strict local `agents`-table row (`db::get_agent`), no chain fallback.
        A client-side gate keyed on bare HTTP status would therefore wrongly treat a
        chain-known-but-oracle-unregistered agent as clear to send — confirmed empirically
        against a live oracle instance with exactly such an agent (on-chain primitives
        resolve; `oracle_registered: false`) before this field existed to check.
        """
        self._nonce_synced = True
        try:
            resp = requests.get(f"{self.oracle_url}/v1/agent/{self.agent_id}", timeout=10)
            if resp.status_code == 404:
                self._registered = False
                return
            resp.raise_for_status()
            body = resp.json()
            self._registered = bool(body.get("oracle_registered", False))
            last_nonce = body.get("last_nonce")
            if isinstance(last_nonce, int) and last_nonce > self._nonce:
                self._nonce = last_nonce
        except requests.RequestException as exc:
            logger.warning("could not sync starting nonce from oracle for agent %s: %s", self.agent_id, exc)

    def flush_telemetry(
        self,
        *,
        zk_proof: Optional[Dict[str, Any]] = None,
        compliance_gate_address: Optional[str] = None,
        covered_entity_address: Optional[str] = None,
        w3: Optional[Any] = None,
    ) -> bool:
        """
        Drains the current batch, derives the four AIS signals from it, and
        POSTs to `{oracle_url}/v1/telemetry/ingest`.

        FIXED 2026-07-11 — this method was shipping a request the real oracle
        could never accept, on two independent counts, confirmed against
        `integrity-oracle/backend/src/handlers.rs`'s actual
        `TelemetryIngestRequest` struct and its own real-HTTP e2e test
        (`tests/e2e.rs`, which hand-builds a request in the *correct* shape —
        that's what exposed this):
          1. `otel_spans` is typed `Vec<serde_json::Value>` (a JSON array) on
             the oracle side. This method was sending a JSON *object*
             (`{"telemetry": [...], "trace_runs": [...]}`) — Axum's JSON
             extractor rejects that at deserialization, before the handler
             ever runs. Fixed: both lists are now flattened into one tagged
             array (`{"kind": "telemetry"|"trace_run", ...}` per element) —
             the oracle stores this column as opaque JSONB and never
             destructures individual elements, so any array shape works; the
             tag is for a human/future-code reader distinguishing the two
             origins, not a schema requirement.
          2. `signature` is a required `String` on the oracle side, not
             `Option<String>` — this method was sending `None`/`null`, a
             second, independent deserialization failure. Worse: even a
             syntactically-valid empty string would still fail, since
             `ingest_telemetry`'s handler calls `crypto::verify_agent_signature`
             and returns 401 on a bad signature — the "handler currently
             treats the signature as optional" claim this docstring used to
             make was simply wrong. Fixed: if `self._keypair` was provided at
             construction, this method now signs the canonical JSON of
             `{agent_id, nonce, otel_spans, derived_signals, zk_proof}` —
             same field set, same `bcc.canonical_json_bytes` convention the
             oracle's own `crypto::canonical_json_bytes` mirrors (sorted
             keys, no whitespace) — exactly as `ingest_telemetry`'s handler
             reconstructs and checks it. Without a keypair, this still sends
             an empty-string signature (so the request at least
             *deserializes*) and will get a real, honest 401 from the oracle,
             which the existing failure/re-queue path below already handles
             — construct this client with `keypair=` to actually succeed.

        Known remaining narrower gap, not fixed here: Rust's `serde_json`
        does not escape non-ASCII characters by default, while this SDK's
        canonicalization (matching `bcc.py`, shared for consistency) uses
        `ensure_ascii=True`. For telemetry content containing non-ASCII text,
        the two sides' canonical bytes — and therefore the signature — could
        disagree. Not exercised by any current test; flagged rather than
        silently assumed fine, same as `bcc.py`'s own canonicalization
        docstring already does for a related concern.

        Also now drains `telemetry/metrics.py`'s `MetricsRegistry` (see
        `record_metric`) into the same tagged `otel_spans` array — that
        module was fully built but never wired into any flush path at all
        until now (a separate dangling-reference gap from the two above).

        Returns True if the oracle accepted the batch, False on any failure
        (logged + re-queued, never raised) — telemetry is best-effort.
        """
        # F2: surface overflow loss instead of hiding it. Recorded as a real metric so it
        # rides in `custom_metrics` through the existing envelope — no schema bump — and a
        # shortened history is visibly explained rather than looking like an agent that simply
        # did less work.
        #
        # Ordering matters: this must precede `self._metrics.drain()` below, or the value is
        # recorded after the drain and misses this flush.
        dropped = self._batcher.drain_dropped_count()
        if dropped:
            logger.warning(
                "telemetry queue overflowed: %d oldest entries dropped (max_queue_size=%d)",
                dropped, self._batcher.max_queue_size,
            )
            self._metrics.record("integrity.telemetry.dropped_entries", float(dropped))

        batch = self._batcher.get_batch_and_clear()
        trace_runs = self._trace_runs
        self._trace_runs = []
        custom_metrics = self._metrics.drain()

        if not batch and not trace_runs and not custom_metrics:
            return True  # nothing to flush is a success, not a failure

        if not self._nonce_synced:
            self._sync_nonce_from_oracle()

        if self._registered is False:
            # Confirmed-unregistered default-deny: the oracle already rejects this
            # server-side (AgentNotFound), but that happens *after* the payload —
            # completion text, token usage, everything `derive.py` reads — has
            # already left the process. Refusing here means an unregistered agent's
            # telemetry never gets transmitted in the first place, not just never
            # stored. Batch is re-queued (same as the network-failure path below) so
            # a later flush succeeds once the agent registers, rather than losing it.
            logger.warning(
                "agent %s is not registered with oracle %s (confirmed via GET /v1/agent/%s) — "
                "refusing to send telemetry by default; batch re-queued for a later flush",
                self.agent_id, self.oracle_url, self.agent_id,
            )
            for entry in batch:
                self._batcher.add_telemetry(entry)
            return False

        self._nonce += 1
        derived = derive.derive_ais_signals(
            batch,
            compliance_gate_address=compliance_gate_address,
            covered_entity_address=covered_entity_address,
            w3=w3,
        )

        # One flat, opaque-to-the-oracle array — see docstring point 1.
        otel_spans: List[Dict[str, Any]] = (
            [{"kind": "telemetry", **entry} for entry in batch]
            + [{"kind": "trace_run", **run} for run in trace_runs]
            + ([{"kind": "custom_metrics", "metrics": custom_metrics}] if custom_metrics else [])
        )

        signable = {
            "schema_version": TELEMETRY_SCHEMA_VERSION,
            "agent_id": self.agent_id,
            "nonce": self._nonce,
            "otel_spans": otel_spans,
            "derived_signals": derived,
            "zk_proof": zk_proof,
        }
        if self._keypair is not None:
            c_bytes = bcc.canonical_json_bytes(signable)
            print("CLIENT SIGNABLE BYTES:", c_bytes.decode('utf-8'))
            signature = "0x" + self._keypair.sign(c_bytes).hex()
        else:
            signature = ""  # deserializes fine; the oracle will 401 it (see docstring point 2)

        payload = {**signable, "signature": signature}

        try:
            resp = requests.post(f"{self.oracle_url}/v1/telemetry/ingest", json=payload, timeout=10)
            resp.raise_for_status()
            return True
        except requests.RequestException as exc:
            # Re-queue the drained batch so a later flush retries it — a
            # transient oracle outage shouldn't silently drop telemetry.
            # (Trace runs and custom metrics are best-effort-only and not
            # re-queued; they're observability sugar, not the signal-bearing
            # payload.)
            for entry in batch:
                self._batcher.add_telemetry(entry)

            if isinstance(exc, requests.HTTPError) and exc.response is not None and exc.response.status_code == 409:
                # A 409 PROVES this nonce was already consumed by the oracle —
                # rolling back to reuse it (the old behavior) would just repeat
                # the same 409 forever (PRODUCTION_GAPS.md Sec3: this is exactly
                # how a fresh client instance got permanently stuck after a
                # restart). Re-sync the real last_nonce instead, so the retry
                # this method's caller triggers next actually advances past it.
                logger.warning(
                    "telemetry flush to %s got 409 (nonce %d already used) — re-syncing last_nonce from oracle, re-queued %d entries",
                    self.oracle_url, self._nonce, len(batch),
                )
                self._nonce_synced = False
                self._sync_nonce_from_oracle()
            else:
                self._nonce -= 1  # roll back so the retry reuses this nonce
                logger.warning("telemetry flush to %s failed, re-queued %d entries: %s", self.oracle_url, len(batch), exc)
            return False
