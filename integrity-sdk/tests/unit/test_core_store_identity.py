from __future__ import annotations

import pytest

from integrity_sdk.core import StoreIdentity, StoreIdentityError


class Provider:
    provider_id = "cortex-local"
    encrypted_at_rest = True


def test_store_identity_is_explicit_and_round_trips():
    identity = StoreIdentity.for_provider(
        Provider(),
        tenant_id="tenant-lab",
        agent_did="did:integrity:agent-1",
        store_id="store-primary",
    )
    assert identity.namespace_key == "tenant-lab/did:integrity:agent-1/store-primary"
    assert StoreIdentity.from_dict(identity.to_dict()) == identity


def test_provider_mismatch_and_tampered_namespace_fail_closed():
    identity = StoreIdentity("cortex-local", "store-primary", "tenant-lab", "did:integrity:agent-1")
    with pytest.raises(StoreIdentityError, match="provider_id"):
        identity.assert_provider(type("Other", (), {"provider_id": "cortex-hosted"})())
    with pytest.raises(StoreIdentityError, match="namespace_key"):
        StoreIdentity.from_dict({**identity.to_dict(), "namespace_key": "tenant-other/store"})
