import pytest
from integrity_sdk.security import attestation
def test_not_cbor_raises_attestation_error():
    with pytest.raises(attestation.AttestationError, match="not valid CBOR|CBOR|Expected a 4-element COSE_Sign1 array"):
        attestation.verify_nitro_attestation(b"this is definitely not cbor \xff\xfe\x00", enforce_validity_period=False)
