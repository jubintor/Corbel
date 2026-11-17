"""Cryptographic security utilities: password hashing (bcrypt), token encryption, and JWT operations."""

import asyncio
import base64
import hashlib
import hmac
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from corbel.core.config import get_settings
from corbel.core.exceptions import CorbelException

# Precomputed 12-round bcrypt hash to ensure constant-time verification for non-existent users (P2-LIM-003)
DUMMY_BCRYPT_HASH: str = "$2b$12$e80yqNmsm.3fE2/v4JvHteD7q4q8o8j8/sNq0y1r7qg0u2k5y9oW2"


class AuthenticationException(CorbelException):
    """Raised when authentication credentials or tokens are invalid."""

    def __init__(self, message: str = "Could not validate credentials", details: Any = None) -> None:
        super().__init__(
            message=message,
            error_code="AUTHENTICATION_FAILED",
            status_code=401,
            details=details,
        )


def validate_password_policy(password: str) -> None:
    """Enforce enterprise password complexity and byte length bounds (P2-LIM-012)."""
    if not password or len(password) < 8:
        raise ValueError("Password must be at least 8 characters long")
    pwd_bytes = password.encode("utf-8")
    if len(pwd_bytes) > 72:
        raise ValueError("Password exceeds maximum allowable length of 72 bytes")
    # Complexity: at least one letter and at least one non-letter (digit or punctuation)
    has_letter = bool(re.search(r"[a-zA-Z]", password))
    has_digit_or_symbol = bool(re.search(r"[^a-zA-Z]", password))
    if not (has_letter and has_digit_or_symbol):
        raise ValueError("Password must contain at least one letter and at least one number or special character")


def hash_password(password: str) -> str:
    """Hash plaintext password using bcrypt with 12 salt rounds without silent truncation (P2-LIM-012)."""
    validate_password_policy(password)
    pwd_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(pwd_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify plaintext password against stored bcrypt hash."""
    if not plain_password or not hashed_password:
        return False
    try:
        pwd_bytes = plain_password.encode("utf-8")
        if len(pwd_bytes) > 72:
            return False
        hash_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(pwd_bytes, hash_bytes)
    except Exception:
        return False


async def hash_password_async(password: str) -> str:
    """Offload CPU-intensive bcrypt hashing to worker thread to prevent event-loop starvation (P2-LIM-004)."""
    return await asyncio.to_thread(hash_password, password)


async def verify_password_async(plain_password: str, hashed_password: str) -> bool:
    """Offload CPU-intensive bcrypt verification to worker thread (P2-LIM-004)."""
    return await asyncio.to_thread(verify_password, plain_password, hashed_password)


# ==============================================================================
# Symmetrically Authenticated Token Encryption (P2-LIM-001)
# ==============================================================================

def _derive_encryption_keys(secret: str) -> tuple[bytes, bytes]:
    """Derive independent encryption and HMAC integrity keys from secret."""
    k_enc = hashlib.sha256((secret + ":corbel_replacement_enc").encode("utf-8")).digest()
    k_mac = hashlib.sha256((secret + ":corbel_replacement_mac").encode("utf-8")).digest()
    return k_enc, k_mac


def encrypt_token(token: str) -> str:
    """Encrypt a replacement refresh token before persistence to avoid plaintext storage (P2-LIM-001)."""
    settings = get_settings()
    k_enc, k_mac = _derive_encryption_keys(settings.JWT_SECRET_KEY)
    iv = secrets.token_bytes(16)
    data = token.encode("utf-8")
    blocks = []
    for i in range((len(data) + 31) // 32):
        ctr = i.to_bytes(4, "big")
        blocks.append(hmac.new(k_enc, iv + ctr, hashlib.sha256).digest())
    keystream = b"".join(blocks)[:len(data)]
    cipher = bytes(a ^ b for a, b in zip(data, keystream, strict=False))
    mac = hmac.new(k_mac, iv + cipher, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(iv + mac + cipher).decode("utf-8")


def decrypt_token(cipher_text: str) -> str:
    """Decrypt an encrypted replacement refresh token and verify HMAC integrity (P2-LIM-001)."""
    settings = get_settings()
    k_enc, k_mac = _derive_encryption_keys(settings.JWT_SECRET_KEY)
    raw = base64.urlsafe_b64decode(cipher_text.encode("utf-8"))
    if len(raw) < 48:
        raise ValueError("Invalid ciphertext length")
    iv, mac, cipher = raw[:16], raw[16:48], raw[48:]
    expected_mac = hmac.new(k_mac, iv + cipher, hashlib.sha256).digest()
    if not hmac.compare_digest(mac, expected_mac):
        raise ValueError("Token HMAC verification failed")
    blocks = []
    for i in range((len(cipher) + 31) // 32):
        ctr = i.to_bytes(4, "big")
        blocks.append(hmac.new(k_enc, iv + ctr, hashlib.sha256).digest())
    keystream = b"".join(blocks)[:len(cipher)]
    plain = bytes(a ^ b for a, b in zip(cipher, keystream, strict=False))
    return plain.decode("utf-8")


# ==============================================================================
# JWT Generation & Verification (P2-LIM-011)
# ==============================================================================

def _get_signing_key() -> tuple[str, str]:
    """Resolve key and algorithm for signing JWT tokens."""
    settings = get_settings()
    if settings.JWT_ALGORITHM.startswith(("RS", "ES")):
        if not settings.JWT_PRIVATE_KEY:
            raise ValueError(f"Asymmetric algorithm {settings.JWT_ALGORITHM} requires JWT_PRIVATE_KEY")
        return settings.JWT_PRIVATE_KEY, settings.JWT_ALGORITHM
    return settings.JWT_SECRET_KEY, settings.JWT_ALGORITHM


def _get_verification_key() -> tuple[str, str]:
    """Resolve key and algorithm for verifying JWT tokens."""
    settings = get_settings()
    if settings.JWT_ALGORITHM.startswith(("RS", "ES")):
        if not settings.JWT_PUBLIC_KEY:
            raise ValueError(f"Asymmetric algorithm {settings.JWT_ALGORITHM} requires JWT_PUBLIC_KEY")
        return settings.JWT_PUBLIC_KEY, settings.JWT_ALGORITHM
    return settings.JWT_SECRET_KEY, settings.JWT_ALGORITHM


def create_access_token(
    user_id: uuid.UUID | str,
    email: str,
    session_id: uuid.UUID | str,
    expires_delta: timedelta | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Generate cryptographically signed JWT access token associated with a persistent session."""
    settings = get_settings()
    now = datetime.now(UTC)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    payload: dict[str, Any] = {
        "sub": str(user_id),
        "email": email,
        "sid": str(session_id),
        "type": "access",
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    if extra_claims:
        payload.update(extra_claims)

    key, algorithm = _get_signing_key()
    encoded = jwt.encode(payload, key, algorithm=algorithm)
    return encoded


def hash_token(token: str) -> str:
    """Return SHA-256 hex digest of a token string for safe lookup."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_refresh_token(
    user_id: uuid.UUID | str,
    email: str,
    session_id: uuid.UUID | str,
    family_id: uuid.UUID | str | None = None,
    token_id: uuid.UUID | str | None = None,
    expires_delta: timedelta | None = None,
) -> tuple[str, uuid.UUID, uuid.UUID, uuid.UUID, datetime]:
    """Generate cryptographically signed JWT refresh token with unique jti, sid, and family claims."""
    settings = get_settings()
    now = datetime.now(UTC)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    jti = uuid.UUID(str(token_id)) if token_id else uuid.uuid4()
    sid = uuid.UUID(str(session_id))
    family = uuid.UUID(str(family_id)) if family_id else sid

    payload: dict[str, Any] = {
        "sub": str(user_id),
        "email": email,
        "sid": str(sid),
        "type": "refresh",
        "jti": str(jti),
        "family": str(family),
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }

    key, algorithm = _get_signing_key()
    encoded = jwt.encode(payload, key, algorithm=algorithm)
    return encoded, jti, sid, family, expire


def decode_token(token: str, expected_type: str = "access") -> dict[str, Any]:
    """Decode and cryptographically verify a JWT token enforcing standard claims (P2-LIM-011)."""
    settings = get_settings()
    key, algorithm = _get_verification_key()
    try:
        decode_kwargs: dict[str, Any] = {
            "algorithms": [algorithm],
            "options": {"require": ["exp", "sub", "type"]},
        }
        if settings.JWT_ISSUER:
            decode_kwargs["issuer"] = settings.JWT_ISSUER
        if settings.JWT_AUDIENCE:
            decode_kwargs["audience"] = settings.JWT_AUDIENCE

        payload = jwt.decode(token, key, **decode_kwargs)
        if payload.get("type") != expected_type:
            raise AuthenticationException(f"Invalid token type: expected {expected_type}")
        return payload
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationException("Authentication token has expired") from exc
    except jwt.InvalidIssuerError as exc:
        raise AuthenticationException("Invalid token issuer") from exc
    except jwt.InvalidAudienceError as exc:
        raise AuthenticationException("Invalid token audience") from exc
    except (jwt.InvalidTokenError, Exception) as exc:
        raise AuthenticationException("Could not validate authentication token") from exc


def get_client_ip(request: Any, trusted_proxies: list[str] | None = None) -> str:
    """Extract validated client IP address, honoring X-Forwarded-For only from trusted proxies (P2-LIM-004)."""
    if request is None:
        return "127.0.0.1"

    client = getattr(request, "client", None)
    direct_host = client.host if client else "127.0.0.1"

    if trusted_proxies is None:
        trusted_proxies = get_settings().TRUSTED_PROXIES

    # If direct connection is not from a trusted proxy, never trust forwarded headers
    if direct_host not in trusted_proxies:
        return direct_host

    headers = getattr(request, "headers", {})
    xff = headers.get("x-forwarded-for")
    if not xff:
        return direct_host

    # Parse comma-separated IPs from right-to-left to find the rightmost untrusted IP
    parts = [p.strip() for p in xff.split(",") if p.strip()]
    if not parts:
        return direct_host

    for ip in reversed(parts):
        if ip not in trusted_proxies:
            return str(ip)

    return str(parts[0])
