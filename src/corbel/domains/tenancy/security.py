"""Cryptographic security utilities: password hashing (bcrypt) and JWT token operations."""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from corbel.core.config import get_settings
from corbel.core.exceptions import CorbelException


class AuthenticationException(CorbelException):
    """Raised when authentication credentials or tokens are invalid."""

    def __init__(self, message: str = "Could not validate credentials", details: Any = None) -> None:
        super().__init__(
            message=message,
            error_code="AUTHENTICATION_FAILED",
            status_code=401,
            details=details,
        )


def hash_password(password: str) -> str:
    """Hash plaintext password using bcrypt with salt rounds."""
    if not password or len(password) < 8:
        raise ValueError("Password must be at least 8 characters long")
    # Truncate to 72 bytes if longer (bcrypt standard limit)
    pwd_bytes = password.encode("utf-8")[:72]
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(pwd_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify plaintext password against stored bcrypt hash."""
    if not plain_password or not hashed_password:
        return False
    try:
        pwd_bytes = plain_password.encode("utf-8")[:72]
        hash_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(pwd_bytes, hash_bytes)
    except Exception:
        return False


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
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    if extra_claims:
        payload.update(extra_claims)

    encoded = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
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
    """Generate cryptographically signed JWT refresh token with unique jti, sid, and family claims.

    Returns (encoded_jwt, token_id, session_id, family_id, expires_at).
    """
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
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }

    encoded = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded, jti, sid, family, expire


def decode_token(token: str, expected_type: str = "access") -> dict[str, Any]:
    """Decode and cryptographically verify a JWT token."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["exp", "sub", "type"]},
        )
        if payload.get("type") != expected_type:
            raise AuthenticationException(f"Invalid token type: expected {expected_type}")
        return payload
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationException("Authentication token has expired") from exc
    except (jwt.InvalidTokenError, Exception) as exc:
        raise AuthenticationException("Could not validate authentication token") from exc
