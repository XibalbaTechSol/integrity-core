import datetime as dt

import pytest

from integrity_sdk.core import BreakGlassError, create_approval, verify_approval
from integrity_sdk.did import Keypair


NOW = dt.datetime(2026, 9, 29, 12, 0, tzinfo=dt.timezone.utc)


def test_break_glass_approval_is_signed_and_expires():
    signer = Keypair.generate()
    approval = create_approval(
        signer,
        tenant_id="tenant-a",
        agent_did="did:integrity:agent-a",
        reason="synthetic incident response",
        issued_at="2026-09-29T11:00:00Z",
        expires_at="2026-09-29T13:00:00Z",
        nonce="nonce-1",
    )
    trusted = [approval["signer_key"]]
    assert verify_approval(approval, trusted_signers=trusted, now=NOW)["nonce"] == "nonce-1"

    tampered = {**approval, "reason": "different action"}
    with pytest.raises(BreakGlassError, match="BAD_SIGNATURE"):
        verify_approval(tampered, trusted_signers=trusted, now=NOW)
    with pytest.raises(BreakGlassError, match="EXPIRED"):
        verify_approval(approval, trusted_signers=trusted, now=dt.datetime(2026, 9, 29, 13, 0, tzinfo=dt.timezone.utc))
