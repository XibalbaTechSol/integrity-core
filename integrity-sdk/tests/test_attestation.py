"""
Tests for security/attestation.py's Nitro attestation VERIFIER against a real,
genuine captured AWS Nitro Enclave attestation document
(tests/fixtures/aws_nitro_document.cbor) — not a hand-crafted fixture.

This closes PRODUCTION_GAPS.md's finding that attestation.py's own module
docstring and README claimed this test file existed ("see
tests/fixtures/aws_nitro_document.cbor and test_attestation.py") when it
didn't — security-critical code (root-CA pinning, cert-chain walk, COSE
signature verification) was undocumented-as-untested rather than honestly
flagged as a gap, a direct instance of the repo's own "no silent mocks" rule
being violated by omission.

The fixture is a real document from November 2022 (per
verify_nitro_attestation's own docstring) — its short-lived leaf/intermediate
certs are long expired by any realistic reference time, so tests that care
about the *rest* of the verification (signature, chain, root pin) pass
`enforce_validity_period=False`, exactly as that parameter's docstring says
to for testing against historical fixtures. A dedicated test below covers the
validity-period check itself, on its own, against the fixture's own real
not-valid-before/after window.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import cbor2
import pytest

from integrity_sdk.security import attestation

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "aws_nitro_document.cbor"


@pytest.fixture(scope="module")
def real_document_bytes() -> bytes:
    return FIXTURE_PATH.read_bytes()


def test_fixture_file_exists_and_is_real_cbor(real_document_bytes):
    # Sanity check on the fixture itself before trusting anything built on it:
    # a real COSE_Sign1 array (4 elements), not a placeholder/truncated file.
    cose_array = cbor2.loads(real_document_bytes)
    assert isinstance(cose_array, list)
    assert len(cose_array) == 4


def test_real_attestation_verifies_signature_and_chain(real_document_bytes):
    result = attestation.verify_nitro_attestation(real_document_bytes, enforce_validity_period=False)

    assert result.signature_valid is True, result.errors
    assert result.chain_valid is True, result.errors
    assert result.root_pinned is True, result.errors
    assert result.valid is True, result.errors
    assert result.errors == []


def test_real_attestation_exposes_real_payload_fields(real_document_bytes):
    result = attestation.verify_nitro_attestation(real_document_bytes, enforce_validity_period=False)

    assert result.module_id is not None
    assert isinstance(result.pcrs, dict)
    assert len(result.pcrs) > 0
    assert result.timestamp_ms is not None and result.timestamp_ms > 0


def test_validity_period_check_against_fixtures_real_window(real_document_bytes):
    """The fixture's own certs really are expired by now — proving
    enforce_validity_period actually checks something, not a no-op."""
    result = attestation.verify_nitro_attestation(real_document_bytes, enforce_validity_period=True)

    assert result.validity_period_valid is False
    assert result.valid is False
    assert any("not valid at" in e for e in result.errors)


def test_validity_period_check_passes_at_a_reference_time_inside_the_real_window(real_document_bytes):
    # November 2022, per verify_nitro_attestation's own docstring on this fixture's age.
    reference_time = datetime(2022, 11, 9, 23, 0, tzinfo=timezone.utc)
    # The fixture's leaf/intermediate certs are short-lived (~hours, not
    # months) -- per test_validity_period_check_against_fixtures_real_window's
    # own failure output, the tightest window is 2022-11-09T22:51:57Z to
    # 2022-11-10T01:52:00Z. Picked well inside every cert's window, not just
    # "sometime in November" (which is outside all of them).
    reference_time = datetime(2022, 11, 10, 0, 30, tzinfo=timezone.utc)
    result = attestation.verify_nitro_attestation(
        real_document_bytes, enforce_validity_period=True, reference_time=reference_time
    )

    assert result.validity_period_valid is True, result.errors
    assert result.valid is True, result.errors


# --- Tamper-detection: mutate the real, valid document and confirm each check independently fails ---


def _load_cose_array(document_bytes: bytes) -> list:
    return cbor2.loads(document_bytes)


def test_tampered_leaf_certificate_fails_chain_validation(real_document_bytes):
    protected, unprotected, payload_bstr, signature = _load_cose_array(real_document_bytes)
    payload = cbor2.loads(payload_bstr)

    # Corrupt the leaf certificate's DER bytes (flip a byte in the middle,
    # well past the ASN.1 header, so it still round-trips through
    # x509.load_der_x509_certificate without raising a parse error — the
    # point is a WRONG certificate, not an unparseable one).
    original_cert = bytearray(payload["certificate"])
    mid = len(original_cert) // 2
    original_cert[mid] ^= 0xFF
    payload["certificate"] = bytes(original_cert)

    tampered_payload_bstr = cbor2.dumps(payload)
    tampered_document = cbor2.dumps([protected, unprotected, tampered_payload_bstr, signature])

    try:
        result = attestation.verify_nitro_attestation(tampered_document, enforce_validity_period=False)
    except attestation.AttestationError:
        # Corrupting DER bytes can also just fail to parse as a certificate
        # at all -- either outcome (a hard parse error, or a parsed-but-wrong
        # cert failing signature/chain checks below) is an acceptable
        # "tampering was caught" result for this test.
        return

    assert result.valid is False
    assert result.signature_valid is False or result.chain_valid is False


def test_tampered_payload_fails_signature_verification(real_document_bytes):
    protected, unprotected, payload_bstr, signature = _load_cose_array(real_document_bytes)
    payload = cbor2.loads(payload_bstr)

    # Flip the module_id -- the COSE signature covers the exact payload
    # bytes, so any change here must break signature verification even
    # though the document still parses perfectly.
    payload["module_id"] = "tampered-" + str(payload.get("module_id", ""))
    tampered_payload_bstr = cbor2.dumps(payload)
    tampered_document = cbor2.dumps([protected, unprotected, tampered_payload_bstr, signature])

    result = attestation.verify_nitro_attestation(tampered_document, enforce_validity_period=False)

    assert result.signature_valid is False
    assert result.valid is False
    assert any("signature does not verify" in e for e in result.errors)


def test_tampered_signature_fails_verification(real_document_bytes):
    protected, unprotected, payload_bstr, signature = _load_cose_array(real_document_bytes)

    tampered_signature = bytearray(signature)
    tampered_signature[0] ^= 0xFF
    tampered_document = cbor2.dumps([protected, unprotected, payload_bstr, bytes(tampered_signature)])

    result = attestation.verify_nitro_attestation(tampered_document, enforce_validity_period=False)

    assert result.signature_valid is False
    assert result.valid is False


def test_wrong_root_ca_fails_root_pinning(real_document_bytes):
    """Swaps cabundle[0] (the root) for the leaf certificate itself -- a
    structurally valid but wrong-and-untrusted root. Proves root pinning is
    a real byte-comparison, not a rubber stamp."""
    protected, unprotected, payload_bstr, signature = _load_cose_array(real_document_bytes)
    payload = cbor2.loads(payload_bstr)

    cabundle = list(payload["cabundle"])
    cabundle[0] = payload["certificate"]  # swap in the leaf cert as a fake "root"
    payload["cabundle"] = cabundle
    tampered_payload_bstr = cbor2.dumps(payload)
    tampered_document = cbor2.dumps([protected, unprotected, tampered_payload_bstr, signature])

    result = attestation.verify_nitro_attestation(tampered_document, enforce_validity_period=False)

    assert result.root_pinned is False
    assert result.valid is False
    assert any("pinned AWS Nitro root CA" in e for e in result.errors)


def test_expected_nonce_mismatch_fails_overall_validity(real_document_bytes):
    result = attestation.verify_nitro_attestation(
        real_document_bytes, enforce_validity_period=False, expected_nonce=b"this-is-not-the-real-nonce"
    )

    assert result.valid is False
    assert any("nonce" in e.lower() for e in result.errors)


# --- Malformed input handling ---


def test_not_cbor_raises_attestation_error():
    # These particular bytes happen to still decode as *some* CBOR value (a
    # short text string, by coincidence of the leading byte) rather than
    # raising a CBOR decode error -- so the failure mode exercised here is
    # the array-shape check, not the decoder itself. Use bytes with a CBOR
    # major-type/length header that can't possibly be satisfied by what
    # follows to hit an actual decode error instead.
    with pytest.raises(attestation.AttestationError, match="CBOR|4-element"):
        attestation.verify_nitro_attestation(b"this is definitely not cbor \xff\xfe\x00", enforce_validity_period=False)


def test_truncated_cbor_raises_attestation_error():
    # 0x9f = indefinite-length array start with no break byte (0xff) -- a
    # genuine CBOR decode error, distinct from the well-formed-but-wrong-shape
    # case above.
    with pytest.raises(attestation.AttestationError, match="CBOR"):
        attestation.verify_nitro_attestation(b"\x9f\x01\x02", enforce_validity_period=False)


def test_wrong_array_shape_raises_attestation_error():
    malformed = cbor2.dumps([b"only", b"two", b"elements"])
    with pytest.raises(attestation.AttestationError, match="4-element"):
        attestation.verify_nitro_attestation(malformed, enforce_validity_period=False)


def test_missing_required_payload_fields_raises_attestation_error(real_document_bytes):
    protected, unprotected, payload_bstr, signature = _load_cose_array(real_document_bytes)
    payload = cbor2.loads(payload_bstr)
    del payload["pcrs"]  # a required field per verify_nitro_attestation's own check

    incomplete_payload_bstr = cbor2.dumps(payload)
    incomplete_document = cbor2.dumps([protected, unprotected, incomplete_payload_bstr, signature])

    with pytest.raises(attestation.AttestationError, match="missing required fields"):
        attestation.verify_nitro_attestation(incomplete_document, enforce_validity_period=False)


# --- NitroAttestationGenerator: honest not-implemented, not a placeholder string ---


def test_generator_raises_not_implemented_rather_than_faking_a_document():
    generator = attestation.NitroAttestationGenerator()
    with pytest.raises(NotImplementedError):
        generator.get_attestation_document()
