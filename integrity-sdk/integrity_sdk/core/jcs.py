"""Canonical bytes (SDK contract C1): RFC 8785 JSON Canonicalization Scheme only.

Everything the SDK hashes or signs is serialized here and nowhere else:
receipts, checkpoints, pack manifests and BCC commitments
(`integrity_sdk.bcc.canonical_json_bytes` delegates to this module). RFC 8785
fixes key order (UTF-16 code-unit order), number formatting (ECMAScript
`Number.prototype.toString`) and string escaping, so two implementations that
follow it produce byte-identical output: https://www.rfc-editor.org/rfc/rfc8785.

Unlike the older `json.dumps(sort_keys=True, ensure_ascii=True)` convention,
JCS emits non-ASCII as UTF-8, which is also what Rust's `serde_json` emits --
closing the documented SDK/oracle disagreement for non-ASCII content once the
oracle adopts JCS.
"""

from __future__ import annotations

import hashlib
import math
from typing import Any

import jcs as _jcs


def _normalize(value: Any) -> Any:
    """Prepare a value for JCS: reject non-finite numbers, fold integral floats.

    RFC 8785 §3.2.2.3 has no representation for NaN or infinities, so they are
    rejected rather than silently coerced. Integral floats (`1.0`) become ints so
    a value that crossed a JSON boundary as a float hashes like the integer the
    other side sent -- the same parity rule the BCC encoder already applied.
    """
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("JCS cannot encode NaN or infinite numbers (RFC 8785 §3.2.2.3)")
        return int(value) if value.is_integer() else value
    if isinstance(value, dict):
        return {key: _normalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    return value


def canonical_bytes(value: Any) -> bytes:
    """RFC 8785 canonical UTF-8 bytes for a JSON-compatible value."""
    return _jcs.canonicalize(_normalize(value))


def sha256_hex(value: Any) -> str:
    """`sha256:<hex>` over the canonical bytes: the SDK's content identifier."""
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()
