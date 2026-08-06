"""
Password hashing (argon2) and JWT issuance/verification, plus developer API
key generation/hashing.

Password hashing: `passlib[argon2]`, NOT `passlib[bcrypt]`. passlib 1.7.4's
bcrypt backend probes `bcrypt.__about__.__version__`, which was removed in
bcrypt>=4.1, so `passlib[bcrypt]` on a current bcrypt breaks at hash time.
argon2 (via passlib's CryptContext, backed by argon2-cffi) is the modern
default anyway and has no such conflict, so it's the deliberate choice here,
not `passlib[bcrypt]`.

API keys: not JWTs. A developer API key is a random high-entropy token
(`uak_<43 base64url chars>`), returned in full exactly once at creation
time. Only its sha256 hash is ever persisted (`api_keys.key_hash`) -- same
"never store the secret, only a hash of it" principle as the password
column, applied to a different credential type.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from app.config import Settings

_pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

API_KEY_PREFIX = "uak_"


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return _pwd_context.verify(password, hashed)


def create_access_token(*, user_id: str, settings: Settings) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        # Per-token identifier, independent of its content -- this is what
        # makes revocation possible at all. Without a `jti`, a "revoke this
        # token" operation would have nothing to key on short of storing the
        # full JWT string (which would defeat the point of a stateless,
        # signature-verified token in the first place).
        "jti": str(uuid.uuid4()),
        "iat": int(now.timestamp()),
        "exp": now + timedelta(minutes=settings.jwt_expiry_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


class TokenError(Exception):
    pass


@dataclass(frozen=True)
class DecodedToken:
    user_id: str
    jti: str
    expires_at: datetime


def decode_access_token(token: str, settings: Settings) -> DecodedToken:
    """Returns the token's identity + revocation-check fields, or raises TokenError."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc
    sub = payload.get("sub")
    jti = payload.get("jti")
    exp = payload.get("exp")
    if not sub or not jti or not exp:
        raise TokenError("token missing 'sub'/'jti'/'exp' claim")
    return DecodedToken(user_id=sub, jti=jti, expires_at=datetime.fromtimestamp(exp, tz=timezone.utc))


def generate_api_key() -> tuple[str, str]:
    """Returns (raw_key, key_hash). The raw key is only ever returned here."""
    raw = API_KEY_PREFIX + secrets.token_urlsafe(32)
    return raw, hash_api_key(raw)


def hash_api_key(raw_key: str) -> str:
    # A plain sha256 (not argon2/bcrypt) is deliberate here: this hash is
    # used purely for equality lookup of a high-entropy random token, not to
    # slow-hash a low-entropy human password -- there's no offline
    # brute-force concern for a 256-bit random token the way there is for a
    # password, so a fast deterministic hash is both correct and simplest.
    return hashlib.sha256(raw_key.encode()).hexdigest()
