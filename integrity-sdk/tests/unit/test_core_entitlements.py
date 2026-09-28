from __future__ import annotations

import datetime as dt

import pytest

from integrity_sdk.core import CapabilityDenied, EntitlementSet, require_capability


NOW = dt.datetime(2026, 9, 28, 12, 0, tzinfo=dt.timezone.utc)


def test_capability_is_tenant_scoped_serializable_and_explicit():
    entitlements = EntitlementSet(
        "tenant-lab",
        frozenset({"shield.enforce", "cortex.write"}),
        revision=3,
        expires_at="2026-09-29T00:00:00Z",
    )
    assert entitlements.allows("shield.enforce", now=NOW)
    assert EntitlementSet.from_dict(entitlements.to_dict()) == entitlements
    require_capability(entitlements, "cortex.write", tenant_id="tenant-lab", now=NOW)


def test_expiry_and_tenant_mismatch_fail_closed():
    entitlements = EntitlementSet("tenant-lab", frozenset({"shield.enforce"}), expires_at="2026-09-28T11:59:00Z")
    with pytest.raises(CapabilityDenied, match="CAPABILITY_DENIED"):
        entitlements.require("shield.enforce", tenant_id="tenant-lab", now=NOW)
    with pytest.raises(CapabilityDenied, match="TENANT_MISMATCH"):
        entitlements.require("shield.enforce", tenant_id="tenant-other", now=NOW)


def test_unknown_capability_is_denied():
    entitlements = EntitlementSet("tenant-lab", frozenset({"cortex.write"}))
    with pytest.raises(CapabilityDenied, match="CAPABILITY_DENIED"):
        entitlements.require("billing.charge", tenant_id="tenant-lab", now=NOW)
