"""Stripe's REST API, product-neutral. Fixed HTTPS origin, bounded requests, no card data, no raw errors.

Lifted from xibalba-cortex `managed/stripe_gateway.py` (Shield plans & metering design, xibalba-shield
docs/superpowers/specs/2026-11-12-shield-plans-metering-design.md §4.2) so Shield and Cortex share one
gateway. Cortex keeps its own copy until a separate Cortex PR switches over (that merge deploys its pilot).

What changed from the Cortex original, deliberately:

* configuration is `StripeConfig` (keys, mode, API version) instead of Cortex's `ManagedConfig`, which
  also carries Cortex's price ids -- the catalog is each product's business, not the gateway's;
* `send_meter_event` -- Stripe API `2025-03-31.basil` and later removed legacy usage records; metered
  prices must be backed by a Billing Meter, fed by meter events;
* `requests` is imported lazily, so importing `integrity_sdk.billing` keeps the core free of the
  connector stack (tests/unit/test_import_hygiene.py). Making a request needs `integrity-sdk[connector]`.

Failure posture: every Stripe failure becomes `BillingUnavailable` with a fixed message. Stripe error
bodies can contain customer data, so they are never forwarded. A deployment without real keys is
`billing_ready == False` and refuses to talk to Stripe at all, rather than sending placeholder keys.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

STRIPE_API_ORIGIN = "https://api.stripe.com/v1"
DEFAULT_API_VERSION = "2025-06-30.basil"
#: (connect, read) seconds. Stripe calls are never in a decision path, but they are in request paths.
REQUEST_TIMEOUT = (3, 10)
#: Webhook signature timestamps older or newer than this are refused (Stripe's own default).
WEBHOOK_TOLERANCE_SECONDS = 300
_PLACEHOLDER_WORDS = ("dummy", "replace", "placeholder")


class BillingUnavailable(RuntimeError):
    """Billing cannot proceed: not configured, or Stripe failed. The message is safe to show."""


@dataclass(frozen=True)
class StripeConfig:
    secret_key: str = field(default="", repr=False)
    webhook_secret: str = field(default="", repr=False)
    live: bool = False
    api_version: str = DEFAULT_API_VERSION

    @property
    def billing_ready(self) -> bool:
        """True only for a real key of the configured mode and a real webhook secret."""
        key_prefix = "sk_live_" if self.live else "sk_test_"
        lowered = self.secret_key.lower()
        return bool(
            self.secret_key.startswith(key_prefix)
            and not any(word in lowered for word in _PLACEHOLDER_WORDS)
            and self.webhook_secret.startswith("whsec_")
            and not any(word in self.webhook_secret.lower() for word in _PLACEHOLDER_WORDS)
        )


def _send(method: str, url: str, **kwargs: Any) -> Any:
    """The one network call. Separate so tests replace it, and so `requests` loads only here."""
    import requests  # noqa: PLC0415  (lazy: keeps the SDK core free of the connector stack)

    try:
        response = requests.request(method, url, **kwargs)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        # Stripe errors may include customer/provider data; do not forward raw responses.
        raise BillingUnavailable("Stripe is temporarily unavailable; retry shortly") from exc


class StripeGateway:
    def __init__(self, config: StripeConfig):
        self.config = config

    def request(self, method: str, path: str, *, data: Optional[Mapping[str, Any]] = None,
                idempotency_key: Optional[str] = None) -> dict:
        if not self.config.billing_ready:
            raise BillingUnavailable("Stripe billing is not configured; placeholder keys cannot be used")
        if not path.startswith("/") or ".." in path or "?" in path or "#" in path or "//" in path:
            raise ValueError("invalid Stripe resource path")
        headers = {"Stripe-Version": self.config.api_version}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        result = _send(method, STRIPE_API_ORIGIN + path, auth=(self.config.secret_key, ""),
                       data=dict(data) if data is not None else None, headers=headers,
                       timeout=REQUEST_TIMEOUT, allow_redirects=False)
        if not isinstance(result, dict):
            raise BillingUnavailable("Stripe returned an invalid response")
        return result

    def send_meter_event(self, event_name: str, customer_id: str, value: int, identifier: str,
                         timestamp: Optional[int] = None) -> dict:
        """Report `value` units for `customer_id` to the Billing Meter whose event name is `event_name`.

        `identifier` must be unique per logical event. Stripe enforces that uniqueness for only about
        24 hours, so the caller's own ledger -- written before this call -- is the dedupe authority.
        Stripe accepts timestamps from the past 35 days up to 5 minutes ahead; callers attribute late
        usage to the period in which they received it rather than back-dating.
        """
        if not event_name or not customer_id.startswith("cus_") or not identifier:
            raise ValueError("meter event needs an event name, a cus_ customer id and an identifier")
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError("meter event value must be a positive integer")
        data = {
            "event_name": event_name,
            "payload[stripe_customer_id]": customer_id,
            "payload[value]": str(value),
            "identifier": identifier,
        }
        if timestamp is not None:
            data["timestamp"] = str(int(timestamp))
        return self.request("POST", "/billing/meter_events", data=data, idempotency_key=identifier)

    def verify_event(self, body: bytes, signature: str, *, now: Optional[float] = None) -> dict:
        """Verify a webhook's `Stripe-Signature` header and return the parsed event."""
        if not self.config.billing_ready:
            raise BillingUnavailable("Stripe webhooks are not configured")
        fields = [part.split("=", 1) for part in signature.split(",") if "=" in part]
        timestamps = [v for k, v in fields if k == "t"]
        signatures = [v for k, v in fields if k == "v1"]
        try:
            if len(timestamps) != 1:
                raise ValueError()
            timestamp = int(timestamps[0])
            if abs((time.time() if now is None else now) - timestamp) > WEBHOOK_TOLERANCE_SECONDS:
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError("invalid or expired Stripe signature") from None
        expected = hmac.new(self.config.webhook_secret.encode(), str(timestamp).encode() + b"." + body,
                            hashlib.sha256).hexdigest()
        if not any(hmac.compare_digest(expected, candidate) for candidate in signatures):
            raise ValueError("invalid Stripe signature")
        try:
            event = json.loads(body)
            if (not isinstance(event, dict) or not isinstance(event.get("id"), str)
                    or not isinstance(event.get("data", {}).get("object"), dict)):
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise ValueError("invalid Stripe event") from None
        if event.get("livemode") is not self.config.live:
            raise ValueError("Stripe event mode does not match deployment")
        return event
