"""Product-neutral billing core shared by Xibalba Shield and Cortex.

Importing this package needs only the SDK's base dependencies; calling Stripe needs
`integrity-sdk[connector]` (for `requests`). Billing is never in a gate's decision path.
"""
from .ledger import (
    BILLABLE,
    BILLING_CLASSES,
    EXCLUDED_FAULT,
    EXCLUDED_MASK,
    STRIPE_EVENTS_DDL,
    classify_for_billing,
    ensure_stripe_events_table,
    record_once,
)
from .stripe_gateway import (
    DEFAULT_API_VERSION,
    REQUEST_TIMEOUT,
    STRIPE_API_ORIGIN,
    WEBHOOK_TOLERANCE_SECONDS,
    BillingUnavailable,
    StripeConfig,
    StripeGateway,
)

__all__ = [
    "BILLABLE", "BILLING_CLASSES", "EXCLUDED_FAULT", "EXCLUDED_MASK", "STRIPE_EVENTS_DDL",
    "classify_for_billing", "ensure_stripe_events_table", "record_once",
    "DEFAULT_API_VERSION", "REQUEST_TIMEOUT", "STRIPE_API_ORIGIN", "WEBHOOK_TOLERANCE_SECONDS",
    "BillingUnavailable", "StripeConfig", "StripeGateway",
]
