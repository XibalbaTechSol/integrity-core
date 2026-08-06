"""
AWS Nitro Enclave attestation — real verification, per docs/INTERFACE_CONTRACT.md §8.

Scope, stated plainly (also in the package README):
  - GENERATION of a real attestation document requires actually running
    inside a Nitro Enclave and calling the Nitro Security Module (NSM) — real
    enclave hardware/hypervisor support this dev environment does not have.
    `NitroAttestationGenerator` below raises `NotImplementedError` explaining
    this; it does NOT return a placeholder string like the old prototype's
    `"BASE64_ENCODED_SGX_QUOTE_STUB"` / `"MRENCLAVE_STUB"`. There is nothing
    to fake here — either you're in an enclave with NSM access, or you
    aren't, and pretending otherwise would be worse than refusing.
  - VERIFICATION is fully real: this module parses the actual COSE_Sign1/CBOR
    wire format Nitro produces, verifies the COSE signature against the
    embedded leaf certificate, and walks the certificate chain up to AWS's
    published Nitro root CA. It is tested against a genuine captured
    attestation document (see tests/fixtures/aws_nitro_document.cbor and
    test_attestation.py) — not a hand-crafted fixture.

Wire format (COSE_Sign1, RFC 8152 §4.2 / RFC 9052):
    COSE_Sign1 = [
        protected:   bstr .cbor {1: alg},   -- alg -35 = ES384 for Nitro
        unprotected: {},
        payload:     bstr .cbor attestation_doc_map,
        signature:   bstr                   -- raw r||s, NOT ASN.1 DER
    ]
Nitro encodes this as a bare 4-element CBOR array (no COSE_Sign1 CBOR tag 18
wrapper) — confirmed against the real fixture used in tests.

Attestation document fields we care about (payload map):
    module_id, digest, timestamp, pcrs (0..15 -> bytes), certificate (leaf,
    DER), cabundle (list of intermediate+root certs, DER, root-to-parent
    order), public_key, user_data, nonce.

Trust anchor: `security/trust_roots/aws_nitro_root_g1.pem` is AWS's
published Nitro Enclaves root CA, downloaded from the official distribution
at https://aws-nitro-enclaves.amazonaws.com/AWS_NitroEnclaves_Root-G1.zip
(referenced from AWS's "Verifying the root of trust" documentation:
https://docs.aws.amazon.com/enclaves/latest/user/verify-root.html). We pin
its SHA-256 fingerprint and require `cabundle[0]` to match it exactly —
that's the actual anchor of trust, not something this code should accept as
a parameter from an untrusted caller.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import cbor2
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils as ec_utils

logger = logging.getLogger("integrity_sdk.security.attestation")

_TRUST_ROOT_PATH = Path(__file__).parent / "trust_roots" / "aws_nitro_root_g1.pem"

# SHA-256 fingerprint of the pinned root, computed once from the official
# download and asserted at load time — if the bundled PEM is ever swapped
# for something else by mistake, `_load_trusted_root` fails loudly instead
# of silently trusting whatever is on disk.
#
# PRODUCTION_GAPS.md: this constant was previously truncated by one trailing
# hex digit (63 chars, an impossible length for a SHA-256 hexdigest, which is
# always 64), so `_load_trusted_root` unconditionally raised AttestationError
# on every call -- attestation verification was completely non-functional.
# Corrected against the actual SHA-256 of the bundled aws_nitro_root_g1.pem
# (confirmed genuine: the real fixture document's cert chain validates
# against it end-to-end in tests/test_attestation.py).
_EXPECTED_ROOT_FINGERPRINT_SHA256 = (
    "641a0321a3e244efe456463195d606317ed7cdcc3c1756e09893f3c68f79bb5b"
)

# COSE algorithm identifier for ECDSA w/ SHA-384 over P-384 (RFC 8152 §8.1).
# This is the only algorithm Nitro attestation documents use as of this
# writing; anything else is treated as unsupported rather than guessed at.
_COSE_ALG_ES384 = -35


class AttestationError(RuntimeError):
    """Raised for structurally invalid input (can't even parse CBOR/COSE).
    A cryptographically invalid-but-well-formed document is reported via
    `AttestationResult.valid = False`, not an exception — callers checking
    "is this attestation trustworthy" shouldn't need a try/except for the
    unremarkable case of "no, it isn't"."""


@dataclass
class AttestationResult:
    valid: bool
    signature_valid: bool
    chain_valid: bool
    root_pinned: bool
    validity_period_valid: Optional[bool]  # None if not enforced
    errors: List[str] = field(default_factory=list)
    module_id: Optional[str] = None
    pcrs: Dict[int, bytes] = field(default_factory=dict)
    user_data: Optional[bytes] = None
    nonce: Optional[bytes] = None
    timestamp_ms: Optional[int] = None


def _load_trusted_root() -> x509.Certificate:
    pem_bytes = _TRUST_ROOT_PATH.read_bytes()
    cert = x509.load_pem_x509_certificate(pem_bytes)
    import hashlib

    actual = hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()
    if actual != _EXPECTED_ROOT_FINGERPRINT_SHA256:
        raise AttestationError(
            "Bundled Nitro root CA fingerprint does not match the pinned value — "
            "refusing to use it as a trust anchor. Expected "
            f"{_EXPECTED_ROOT_FINGERPRINT_SHA256}, got {actual}."
        )
    return cert


def _safe_subject_name(cert: x509.Certificate) -> str:
    """`cryptography` parses ASN.1 lazily -- a certificate that loaded
    successfully can still raise when a specific field (like `subject`) is
    read later, if that field's encoding is malformed. Error-message
    formatting is exactly the kind of place that would otherwise turn a
    corrupted/tampered certificate into an unhandled crash instead of a
    reported `chain_valid = False` -- this is purely for display, so any
    failure here degrades to a placeholder rather than propagating."""
    try:
        return cert.subject.rfc4514_string()
    except ValueError:
        return "<unparseable subject>"


def _verify_cert_signed_by(subject: x509.Certificate, issuer: x509.Certificate) -> bool:
    """Check that `issuer`'s public key produced `subject`'s signature.
    Nitro's chain is entirely P-256/P-384 ECDSA, but we read the hash
    algorithm off the certificate itself rather than assuming, so this also
    works if AWS mixes curve/hash choices across chain levels (they do:
    the root is P-384/SHA-384, but that's not guaranteed for every level)."""
    try:
        issuer_pub = issuer.public_key()
        issuer_pub.verify(
            subject.signature,
            subject.tbs_certificate_bytes,
            ec.ECDSA(subject.signature_hash_algorithm),
        )
        return True
    except InvalidSignature:
        return False


def _verify_cose_signature(
    protected_bstr: bytes,
    payload_bstr: bytes,
    signature: bytes,
    leaf_cert: x509.Certificate,
) -> bool:
    """Reconstruct the COSE Sig_structure and verify the signature against
    the leaf certificate's public key. See RFC 8152 §4.4:

        Sig_structure = [
            "Signature1",     -- context string, fixed for COSE_Sign1
            body_protected,   -- the *already CBOR-encoded* protected header bytes
            external_aad,     -- empty bstr; Nitro doesn't use AAD
            payload           -- the *already CBOR-encoded* payload bytes
        ]

    Both `body_protected` and `payload` go in as the raw bytes that were
    embedded in the COSE_Sign1 array — NOT re-encoded from the decoded Python
    objects, since CBOR encoding isn't guaranteed canonical/unique and
    re-encoding could produce different bytes than what was actually signed.
    """
    sig_structure = ["Signature1", protected_bstr, b"", payload_bstr]
    to_be_signed = cbor2.dumps(sig_structure)

    pubkey = leaf_cert.public_key()
    if not isinstance(pubkey, ec.EllipticCurvePublicKey):
        return False

    # COSE/JOSE ECDSA signatures are the raw, fixed-width concatenation of r
    # and s (here 2 x 48 bytes for P-384) — NOT the ASN.1 DER SEQUENCE that
    # `cryptography`'s verify() expects, so we must re-encode before calling it.
    half = len(signature) // 2
    r = int.from_bytes(signature[:half], "big")
    s = int.from_bytes(signature[half:], "big")
    der_signature = ec_utils.encode_dss_signature(r, s)

    try:
        pubkey.verify(der_signature, to_be_signed, ec.ECDSA(hashes.SHA384()))
        return True
    except InvalidSignature:
        return False


def verify_nitro_attestation(
    document_bytes: bytes,
    *,
    enforce_validity_period: bool = True,
    reference_time: Optional[datetime] = None,
    expected_nonce: Optional[bytes] = None,
) -> AttestationResult:
    """
    Verify a raw AWS Nitro Enclave attestation document (the CBOR bytes as
    produced by the NSM `GetAttestationDoc` call, i.e. what you'd get from
    `nsm.get_attestation_doc()` inside a real enclave).

    `enforce_validity_period=True` (default) fails the overall result if any
    certificate in the chain is expired/not-yet-valid as of `reference_time`
    (defaults to now). Set to False only for testing against historical
    fixtures (our bundled test fixture is a real document from November
    2022, whose short-lived leaf/intermediate certs are long expired by any
    reference time you'd realistically use) — production callers should
    leave this on.
    """
    reference_time = reference_time or datetime.now(timezone.utc)
    errors: List[str] = []

    try:
        cose_array = cbor2.loads(document_bytes)
    except Exception as exc:
        raise AttestationError(f"Not valid CBOR: {exc}") from exc

    if not isinstance(cose_array, list) or len(cose_array) != 4:
        raise AttestationError(
            f"Expected a 4-element COSE_Sign1 array, got {type(cose_array)} "
            f"with {len(cose_array) if isinstance(cose_array, list) else '?'} elements"
        )
    protected_bstr, unprotected, payload_bstr, signature = cose_array

    try:
        protected_header = cbor2.loads(protected_bstr)
    except Exception as exc:
        raise AttestationError(f"Protected header is not valid CBOR: {exc}") from exc

    alg = protected_header.get(1)
    if alg != _COSE_ALG_ES384:
        errors.append(f"Unsupported COSE algorithm {alg!r} (expected ES384 / -35)")

    try:
        payload = cbor2.loads(payload_bstr)
    except Exception as exc:
        raise AttestationError(f"Attestation payload is not valid CBOR: {exc}") from exc

    required_fields = {
        "module_id",
        "digest",
        "timestamp",
        "pcrs",
        "certificate",
        "cabundle",
    }
    missing = required_fields - set(payload.keys())
    if missing:
        raise AttestationError(
            f"Attestation payload missing required fields: {missing}"
        )

    try:
        leaf_cert = x509.load_der_x509_certificate(payload["certificate"])
        cabundle_certs = [x509.load_der_x509_certificate(c) for c in payload["cabundle"]]
    except ValueError as exc:
        # cryptography's ASN.1 parser can accept a byte string as "a
        # certificate" here yet still raise later on malformed internals —
        # either way, a cert we can't load is the same "can't even parse"
        # category as invalid CBOR above, not a valid-but-untrusted document.
        raise AttestationError(f"Certificate in payload is not valid DER/ASN.1: {exc}") from exc
    full_chain = cabundle_certs + [leaf_cert]  # root ... leaf

    # 1. Root pinning: cabundle[0] must be byte-identical to AWS's published root.
    trusted_root = _load_trusted_root()
    root_pinned = cabundle_certs[0].public_bytes(
        serialization.Encoding.DER
    ) == trusted_root.public_bytes(serialization.Encoding.DER)
    if not root_pinned:
        errors.append("cabundle[0] does not match the pinned AWS Nitro root CA")

    # 2. Chain signature walk: root is self-signed, then each cert is signed
    #    by the previous one, ending with the leaf signed by cabundle[-1].
    chain_valid = True
    root = full_chain[0]
    if not _verify_cert_signed_by(root, root):
        chain_valid = False
        errors.append("Root certificate is not self-signed / self-signature invalid")
    for i in range(len(full_chain) - 1):
        issuer, subject = full_chain[i], full_chain[i + 1]
        if not _verify_cert_signed_by(subject, issuer):
            chain_valid = False
            errors.append(
                f"Chain signature invalid: cert[{i + 1}] not signed by cert[{i}]"
                f"Chain signature invalid: cert[{i + 1}] "
                f"({_safe_subject_name(subject)}) not signed by cert[{i}]"
            )

    # 3. COSE signature over the payload, checked against the LEAF cert's key
    #    (the thing that actually signed this specific attestation document).
    signature_valid = _verify_cose_signature(
        protected_bstr, payload_bstr, signature, leaf_cert
    )
    if not signature_valid:
        errors.append(
            "COSE_Sign1 signature does not verify against the leaf certificate"
        )

    # 4. Validity period (optional — see docstring on why this can be disabled).
    validity_period_valid: Optional[bool] = None
    if enforce_validity_period:
        validity_period_valid = True
        for i, cert in enumerate(full_chain):
            if not (
                cert.not_valid_before_utc <= reference_time <= cert.not_valid_after_utc
            ):
                validity_period_valid = False
                errors.append(
                    f"cert[{i}] ({_safe_subject_name(cert)}) not valid at "
                    f"{reference_time.isoformat()}: window is "
                    f"{cert.not_valid_before_utc.isoformat()}..{cert.not_valid_after_utc.isoformat()}"
                )

    # 5. Optional caller-supplied nonce check (freshness / replay protection
    #    is the caller's responsibility — this just compares bytes).
    nonce = payload.get("nonce")
    if expected_nonce is not None and nonce != expected_nonce:
        errors.append("Attestation nonce does not match expected_nonce")

    overall_valid = (
        signature_valid
        and chain_valid
        and root_pinned
        and (validity_period_valid is not False)
        and (expected_nonce is None or nonce == expected_nonce)
    )

    return AttestationResult(
        valid=overall_valid,
        signature_valid=signature_valid,
        chain_valid=chain_valid,
        root_pinned=root_pinned,
        validity_period_valid=validity_period_valid,
        errors=errors,
        module_id=payload.get("module_id"),
        pcrs=payload.get("pcrs", {}),
        user_data=payload.get("user_data"),
        nonce=nonce,
        timestamp_ms=payload.get("timestamp"),
    )


class NitroAttestationGenerator:
    """
    Placeholder for the GENERATION side of Nitro attestation — deliberately
    unimplemented. Real generation requires:
      1. Running inside an actual AWS Nitro Enclave (a real enclave image
         built with `nitro-cli build-enclave`, launched with
         `nitro-cli run-enclave` on real or EC2 Nitro-capable hardware).
      2. Calling the Nitro Security Module device (`/dev/nsm`) via the NSM
         API (see aws/aws-nitro-enclaves-nsm-api) to request a signed
         attestation document for a given `user_data`/`nonce`/`public_key`.

    Neither of those exists in this dev environment. Rather than return a
    string like the old prototype's `"BASE64_ENCODED_CMS_DOCUMENT_STUB"`
    (which is indistinguishable from a real document to any caller that
    doesn't already know to check), this raises unconditionally so callers
    fail fast and loud if they try to use it.
    """

    def get_attestation_document(self, *args, **kwargs) -> bytes:
        raise NotImplementedError(
            "Generating a real Nitro attestation document requires running inside "
            "an actual Nitro Enclave with NSM device access (/dev/nsm), which this "
            "environment does not have. See docs/INTERFACE_CONTRACT.md §8 and this "
            "module's docstring. Use verify_nitro_attestation() to verify documents "
            "produced elsewhere; there is no local substitute for generation."
        )
