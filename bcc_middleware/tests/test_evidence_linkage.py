"""
Tests for the evidence-export decision->leaf->anchor linkage (Phase A of
docs/design/evidence-export.md).

Two independent writes make the linkage: the ALLOW decision row carries the
Merkle `leaf` in its metadata (report_decision), and the anchor event carries
that same leaf + the on-chain (root, tx_hash) (report_anchor_events). They are
JOINed on leaf at export time. The critical property (why we chose the JOIN over
a back-fill): the commitment that *fills* a batch is anchored before its own
ALLOW row is recorded, so a back-fill-by-leaf would deterministically miss it --
the JOIN design links it anyway because the anchor event is written to its own
table regardless of decision-row timing.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.anchor import AnchorResult
from app.config import Settings
from app.merkle import MerkleBatcher, leaf_hash
from app.schemas import BCCCommitment
from tests.helpers import new_agent, sign_commitment


@pytest.fixture()
def client():
    # Context-managed deliberately. A bare `TestClient(app)` starts and tears down a
    # fresh portal event loop around EACH request, so the fire-and-forget audit task
    # `main._report_decision_background` schedules is cancelled at teardown before it
    # can run -- the decision row is simply lost, and these tests then assert against
    # an empty list. Entering the context keeps one loop alive across the whole test,
    # which is also what a real uvicorn process does.
    #
    # Worth noting the production shape this exposes (not a test artifact): audit
    # reporting is `ensure_future(to_thread(...))` that nothing ever awaits, so a
    # worker shutting down with reports in flight drops them silently. See
    # docs/design/e2e-audit-2026-07-31.md E15.
    with TestClient(main_module.app) as c:
        yield c


def _leaf_hex(payload: dict) -> str:
    return "0x" + leaf_hash(BCCCommitment(**payload)).hex()


def _await_reported(reported: list, *, timeout: float = 5.0) -> list:
    """
    Block until the fire-and-forget audit report lands, or `timeout` elapses.

    `main._report_decision_background` dispatches `report_decision` via
    `asyncio.ensure_future(asyncio.to_thread(...))` and does NOT await it, so the
    HTTP response returns before the report is necessarily recorded. Asserting
    directly on `reported` after `client.post(...)` is therefore a race against
    thread scheduling, not a test of the linkage — it passes on an idle machine and
    fails under load. Observed failing exactly that way on 2026-07-31 after passing
    in the immediately preceding run, with no code change between them.

    Returning on the first observation (rather than sleeping a fixed interval) keeps
    the common case fast; the timeout is what turns a genuine regression back into a
    failure instead of a hang.
    """
    deadline = time.monotonic() + timeout
    while not reported and time.monotonic() < deadline:
        time.sleep(0.01)
    return reported


def test_allow_decision_records_leaf_metadata(client, real_opa_server, monkeypatch):
    """An ALLOW must report the decision with metadata.leaf equal to the
    commitment's Merkle leaf -- that's the join key the anchor event links on."""
    settings = Settings(opa_url=real_opa_server, merkle_batch_size=999)
    monkeypatch.setattr(main_module, "default_settings", settings)
    monkeypatch.setattr(main_module, "batcher", MerkleBatcher(batch_size=999))
    main_module.circuit_breaker.reset()
    main_module.nonce_store.reset()

    reported: list[dict] = []
    monkeypatch.setattr(main_module.audit_module, "report_decision", lambda settings, **kw: reported.append(kw))

    agent_id, private_key = new_agent()
    payload = sign_commitment(private_key, agent_id=agent_id, intent_type="payment", nonce=1)
    assert client.post("/v1/bcc/intercept", json=payload).json()["authorized"] is True

    allow = [r for r in _await_reported(reported) if r["decision"] == "allow"]
    assert allow, "an allow decision must be reported"
    assert allow[-1]["metadata"]["leaf"] == _leaf_hex(payload)
    assert allow[-1]["metadata"]["verification_token"]


def test_batch_filling_leaf_is_anchor_linked(client, real_opa_server, monkeypatch):
    """The discriminating test: with batch_size=N, the Nth commitment triggers the
    flush+anchor. Its leaf MUST be among the reported anchor events -- this is
    exactly the row a back-fill-by-leaf would have missed (anchored before its
    ALLOW row exists). Anchoring itself is stubbed to a successful result so the
    test targets the linkage wiring, not chain I/O (covered in test_anchor_per_agent)."""
    settings = Settings(opa_url=real_opa_server, merkle_batch_size=3)
    monkeypatch.setattr(main_module, "default_settings", settings)
    monkeypatch.setattr(main_module, "batcher", MerkleBatcher(batch_size=3))
    main_module.circuit_breaker.reset()
    main_module.nonce_store.reset()

    def fake_anchor(_settings, leaves):
        # One successful per-agent result, mirroring anchor_batch_per_agent's shape.
        return {
            leaf.commitment.agent_id: AnchorResult(submitted=True, detail="anchored", tx_hash="0xdead", root=b"\x11" * 32)
            for leaf in leaves
        }

    monkeypatch.setattr(main_module.anchor_module, "anchor_batch_per_agent", fake_anchor)

    anchored: list[dict] = []
    monkeypatch.setattr(main_module.audit_module, "report_anchor_events", lambda settings, **kw: anchored.append(kw))

    agent_id, private_key = new_agent()
    payloads = [sign_commitment(private_key, agent_id=agent_id, intent_type="payment", nonce=n) for n in (1, 2, 3)]
    for p in payloads:
        assert client.post("/v1/bcc/intercept", json=p).json()["authorized"] is True

    # Exactly one anchor report (the 3rd request filled the batch and flushed).
    assert len(anchored) == 1
    report = anchored[0]
    assert report["agent_id"] == agent_id
    assert report["root"] == "0x" + (b"\x11" * 32).hex()
    assert report["tx_hash"] == "0xdead"
    # All three leaves reported -- crucially including the batch-FILLING 3rd leaf.
    assert set(report["leaves"]) == {_leaf_hex(p) for p in payloads}
    assert _leaf_hex(payloads[2]) in report["leaves"], "the batch-filling leaf must be linked"


def test_no_anchor_report_when_anchoring_did_not_land(client, real_opa_server, monkeypatch):
    """If the on-chain anchor didn't actually submit (e.g. StateAnchor unresolved,
    tx failed), no anchor event is reported -- we never claim a decision is
    anchored when it isn't."""
    settings = Settings(opa_url=real_opa_server, merkle_batch_size=2)
    monkeypatch.setattr(main_module, "default_settings", settings)
    monkeypatch.setattr(main_module, "batcher", MerkleBatcher(batch_size=2))
    main_module.circuit_breaker.reset()
    main_module.nonce_store.reset()

    monkeypatch.setattr(
        main_module.anchor_module,
        "anchor_batch_per_agent",
        lambda _s, leaves: {leaf.commitment.agent_id: AnchorResult(submitted=False, detail="RPC unreachable") for leaf in leaves},
    )
    anchored: list[dict] = []
    monkeypatch.setattr(main_module.audit_module, "report_anchor_events", lambda settings, **kw: anchored.append(kw))

    agent_id, private_key = new_agent()
    for n in (1, 2):
        payload = sign_commitment(private_key, agent_id=agent_id, intent_type="payment", nonce=n)
        assert client.post("/v1/bcc/intercept", json=payload).json()["authorized"] is True

    assert anchored == [], "a failed/unsubmitted anchor must not be reported as linked"
