"""integrity_sdk.billing: the shared Stripe gateway, webhook idempotency and receipt billing classes."""
from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3

import pytest

from integrity_sdk.billing import (
    BILLABLE,
    EXCLUDED_FAULT,
    EXCLUDED_MASK,
    BillingUnavailable,
    StripeConfig,
    StripeGateway,
    classify_for_billing,
    ensure_stripe_events_table,
    record_once,
)
from integrity_sdk.billing import stripe_gateway as gateway_module
from integrity_sdk.core import ais_local

TEST_KEY = "sk_test_" + "a" * 24
WHSEC = "whsec_" + "b" * 24
NOW = 1_800_000_000


def ready(live: bool = False) -> StripeGateway:
    key = ("sk_live_" if live else "sk_test_") + "a" * 24
    return StripeGateway(StripeConfig(secret_key=key, webhook_secret=WHSEC, live=live))


def sign(body: bytes, *, secret: str = WHSEC, ts: int = NOW) -> str:
    digest = hmac.new(secret.encode(), str(ts).encode() + b"." + body, hashlib.sha256).hexdigest()
    return f"t={ts},v1={digest}"


def event_body(*, livemode: bool = False) -> bytes:
    return json.dumps({"id": "evt_1", "livemode": livemode, "data": {"object": {"id": "sub_1"}}}).encode()


@pytest.fixture
def calls(monkeypatch):
    sent = []

    def fake_send(method, url, **kwargs):
        sent.append((method, url, kwargs))
        return {"id": "ok"}

    monkeypatch.setattr(gateway_module, "_send", fake_send)
    return sent


# --- configuration ------------------------------------------------------------------------------

@pytest.mark.parametrize("key,secret,live", [
    ("", WHSEC, False),
    ("sk_test_placeholder_xxxxxxxx", WHSEC, False),
    ("sk_test_REPLACE_ME_xxxxxxxxx", WHSEC, False),
    ("sk_test_dummy_xxxxxxxxxxxxxx", WHSEC, False),
    (TEST_KEY, "", False),
    (TEST_KEY, "whsec_placeholder", False),
    (TEST_KEY, WHSEC, True),                      # test key on a live deployment
    ("sk_live_" + "a" * 24, WHSEC, False),        # live key on a test deployment
    ("pk_test_" + "a" * 24, WHSEC, False),        # publishable key
])
def test_billing_ready_refuses_placeholder_or_mismatched_keys(key, secret, live):
    assert StripeConfig(secret_key=key, webhook_secret=secret, live=live).billing_ready is False


def test_billing_ready_accepts_real_keys_for_the_mode():
    assert ready().config.billing_ready
    assert ready(live=True).config.billing_ready


def test_secrets_are_not_in_repr():
    text = repr(ready().config)
    assert TEST_KEY not in text and WHSEC not in text


def test_default_api_version_is_basil():
    assert StripeConfig().api_version == "2025-06-30.basil"


# --- requests -----------------------------------------------------------------------------------

def test_not_ready_refuses_before_any_network(calls):
    gateway = StripeGateway(StripeConfig(secret_key="sk_test_placeholder", webhook_secret=WHSEC))
    with pytest.raises(BillingUnavailable):
        gateway.request("GET", "/prices/price_1")
    assert calls == []


@pytest.mark.parametrize("path", ["prices", "/../v2/x", "/prices?expand=x", "/prices#x", "//evil.example/x"])
def test_path_validation(calls, path):
    with pytest.raises(ValueError):
        ready().request("GET", path)
    assert calls == []


def test_request_uses_fixed_origin_bounded_timeout_and_no_redirects(calls):
    ready().request("GET", "/prices/price_1", idempotency_key="k1")
    method, url, kwargs = calls[0]
    assert (method, url) == ("GET", "https://api.stripe.com/v1/prices/price_1")
    assert kwargs["timeout"] == (3, 10) and kwargs["allow_redirects"] is False
    assert kwargs["headers"] == {"Stripe-Version": "2025-06-30.basil", "Idempotency-Key": "k1"}
    assert kwargs["auth"] == (TEST_KEY, "")


def test_non_dict_response_is_billing_unavailable(monkeypatch):
    monkeypatch.setattr(gateway_module, "_send", lambda *a, **k: ["not", "a", "dict"])
    with pytest.raises(BillingUnavailable):
        ready().request("GET", "/prices/price_1")


def test_stripe_errors_are_not_forwarded(monkeypatch):
    requests = pytest.importorskip("requests")

    def boom(method, url, **kwargs):
        raise requests.HTTPError("card_declined for jane@example.com")

    monkeypatch.setattr(requests, "request", boom)
    with pytest.raises(BillingUnavailable) as raised:
        ready().request("GET", "/prices/price_1")
    assert "jane@example.com" not in str(raised.value)


# --- meter events -------------------------------------------------------------------------------

def test_meter_event_form_fields(calls):
    ready().send_meter_event("shield_gated_decisions_overage", "cus_123", 42, "shield-ovg:t:2026-11:3",
                             timestamp=NOW)
    method, url, kwargs = calls[0]
    assert (method, url) == ("POST", "https://api.stripe.com/v1/billing/meter_events")
    assert kwargs["data"] == {
        "event_name": "shield_gated_decisions_overage",
        "payload[stripe_customer_id]": "cus_123",
        "payload[value]": "42",
        "identifier": "shield-ovg:t:2026-11:3",
        "timestamp": str(NOW),
    }
    assert kwargs["headers"]["Idempotency-Key"] == "shield-ovg:t:2026-11:3"


def test_meter_event_without_timestamp_lets_stripe_default_it(calls):
    ready().send_meter_event("m", "cus_1", 1, "id-1")
    assert "timestamp" not in calls[0][2]["data"]


@pytest.mark.parametrize("args", [
    ("", "cus_1", 1, "id"),
    ("m", "acct_1", 1, "id"),
    ("m", "cus_1", 0, "id"),
    ("m", "cus_1", -5, "id"),
    ("m", "cus_1", True, "id"),
    ("m", "cus_1", 1.5, "id"),
    ("m", "cus_1", 1, ""),
])
def test_meter_event_rejects_bad_input(calls, args):
    with pytest.raises(ValueError):
        ready().send_meter_event(*args)
    assert calls == []


# --- webhook verification -----------------------------------------------------------------------

def test_verify_event_accepts_a_good_signature():
    body = event_body()
    assert ready().verify_event(body, sign(body), now=NOW)["id"] == "evt_1"


def test_verify_event_accepts_any_matching_v1_among_several():
    body = event_body()
    good = sign(body).split("v1=")[1]
    assert ready().verify_event(body, f"t={NOW},v1={'0' * 64},v1={good}", now=NOW)["id"] == "evt_1"


def test_verify_event_rejects_a_bad_signature():
    body = event_body()
    with pytest.raises(ValueError, match="invalid Stripe signature"):
        ready().verify_event(body, sign(body, secret="whsec_other"), now=NOW)


def test_verify_event_rejects_a_tampered_body():
    body = event_body()
    with pytest.raises(ValueError):
        ready().verify_event(body.replace(b"sub_1", b"sub_2"), sign(body), now=NOW)


@pytest.mark.parametrize("skew", [301, -301, 10_000])
def test_verify_event_rejects_expired_or_future_timestamps(skew):
    body = event_body()
    with pytest.raises(ValueError, match="expired"):
        ready().verify_event(body, sign(body, ts=NOW - skew), now=NOW)


def test_verify_event_accepts_within_tolerance():
    body = event_body()
    assert ready().verify_event(body, sign(body, ts=NOW - 300), now=NOW)


@pytest.mark.parametrize("header", ["", "v1=abc", f"t={NOW}", f"t=x,v1=abc", f"t={NOW},t={NOW},v1=abc"])
def test_verify_event_rejects_malformed_headers(header):
    with pytest.raises(ValueError):
        ready().verify_event(event_body(), header, now=NOW)


def test_verify_event_rejects_livemode_mismatch():
    live_body = event_body(livemode=True)
    with pytest.raises(ValueError, match="mode"):
        ready(live=False).verify_event(live_body, sign(live_body), now=NOW)
    test_body = event_body(livemode=False)
    with pytest.raises(ValueError, match="mode"):
        ready(live=True).verify_event(test_body, sign(test_body), now=NOW)


def test_verify_event_rejects_a_missing_livemode():
    body = json.dumps({"id": "evt_1", "data": {"object": {}}}).encode()
    with pytest.raises(ValueError, match="mode"):
        ready().verify_event(body, sign(body), now=NOW)


def test_verify_event_rejects_non_event_json():
    body = b'["not an event"]'
    with pytest.raises(ValueError, match="invalid Stripe event"):
        ready().verify_event(body, sign(body), now=NOW)


def test_verify_event_requires_configuration():
    body = event_body()
    gateway = StripeGateway(StripeConfig())
    with pytest.raises(BillingUnavailable):
        gateway.verify_event(body, sign(body), now=NOW)


# --- webhook idempotency ------------------------------------------------------------------------

def test_record_once_claims_an_event_exactly_once():
    conn = sqlite3.connect(":memory:")
    ensure_stripe_events_table(conn)
    assert record_once(conn, "evt_1", processed_at=NOW) is True
    assert record_once(conn, "evt_1", processed_at=NOW + 5) is False
    assert record_once(conn, "evt_2", processed_at=NOW) is True
    assert conn.execute("SELECT processed_at FROM stripe_events WHERE id='evt_1'").fetchone() == (NOW,)


def test_record_once_rolls_back_with_the_transaction():
    # A crash mid-handler must leave the event unclaimed, so Stripe's redelivery is processed.
    conn = sqlite3.connect(":memory:", isolation_level="DEFERRED")
    ensure_stripe_events_table(conn)
    conn.commit()
    assert record_once(conn, "evt_1", processed_at=NOW)
    conn.rollback()
    assert record_once(conn, "evt_1", processed_at=NOW) is True


@pytest.mark.parametrize("bad", ["", "sub_1", None, 7])
def test_record_once_rejects_non_event_ids(bad):
    conn = sqlite3.connect(":memory:")
    ensure_stripe_events_table(conn)
    with pytest.raises(ValueError):
        record_once(conn, bad, processed_at=NOW)


# --- receipt billing classes --------------------------------------------------------------------

@pytest.mark.parametrize("decision", ["permit", "deny", "log_only"])
def test_governed_tool_calls_are_billable(decision):
    assert classify_for_billing({"decision": decision, "reason_code": "POLICY_RULE"}) == BILLABLE


def test_no_match_is_billable():
    assert classify_for_billing({"decision": "deny", "reason_code": "INTEGRITY_NO_MATCH"}) == BILLABLE


def test_zone_mask_denials_are_excluded_as_mask():
    assert classify_for_billing({"decision": "deny", "reason_code": "AIS_ZONE_RESTRICTED"}) == EXCLUDED_MASK


@pytest.mark.parametrize("code", ["INTEGRITY_EVALUATOR_ERROR", "INTEGRITY_MALFORMED_DECISION", "INTEGRITY_NO_PACK"])
def test_gate_faults_are_excluded_as_fault(code):
    assert classify_for_billing({"decision": "deny", "reason_code": code}) == EXCLUDED_FAULT


def test_billing_exclusions_are_exactly_the_ais_scorer_exclusions():
    """A code the AIS scorer ignores is never billed, and a billed code is always scored."""
    excluded = {code for code in ais_local.EXCLUDED_REASON_CODES
                if classify_for_billing({"decision": "deny", "reason_code": code}) != BILLABLE}
    assert excluded == set(ais_local.EXCLUDED_REASON_CODES)
    for code in ais_local.EXCLUDED_REASON_CODES:
        receipt = {"decision": "deny", "reason_code": code}
        assert ais_local.classify_receipt(receipt) is None
        assert classify_for_billing(receipt) != BILLABLE
    billed = {"decision": "deny", "reason_code": "SOMETHING_ELSE"}
    assert classify_for_billing(billed) == BILLABLE and ais_local.classify_receipt(billed) is not None
