"""Distributed rate limiting engine using PostgreSQL row-level locks (P2-LIM-004)."""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from corbel.core.exceptions import CorbelException
from corbel.domains.tenancy.models import RateLimitBucket

logger = logging.getLogger(__name__)


class RateLimitExceededException(CorbelException):
    """Raised when an operation exceeds permitted frequency limits."""

    def __init__(self, message: str = "Rate limit exceeded. Please try again later.", retry_after: int = 60) -> None:
        super().__init__(
            message=message,
            error_code="RATE_LIMIT_EXCEEDED",
            status_code=429,
            details={"retry_after_seconds": retry_after},
        )
        self.retry_after = retry_after


class RateLimiter:
    """Manages multi-worker atomic rate limiting backed by PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def check_and_record(
        self,
        dimension_key: str,
        max_requests: int,
        window_seconds: int,
        lockout_threshold: int | None = None,
        lockout_seconds: int = 900,
    ) -> int | None:
        """Atomically increment counter and enforce rate limits.

        Returns None if permitted, or retry_after integer in seconds if rate limit exceeded.
        """
        now_utc = datetime.now(UTC)

        stmt = (
            select(RateLimitBucket)
            .where(RateLimitBucket.key == dimension_key)
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        bucket = result.scalar_one_or_none()

        if bucket is None:
            bucket = RateLimitBucket(
                key=dimension_key,
                tokens=1,
                last_updated=now_utc,
                blocked_until=None,
            )
            self.session.add(bucket)
            await self.session.flush()
            return None

        # Check existing lockout
        if bucket.blocked_until is not None and bucket.blocked_until > now_utc:
            retry_after = max(1, int((bucket.blocked_until - now_utc).total_seconds()))
            return retry_after

        # Reset window if expired
        elapsed = (now_utc - bucket.last_updated).total_seconds()
        if elapsed > window_seconds:
            bucket.tokens = 1
            bucket.last_updated = now_utc
            bucket.blocked_until = None
            await self.session.flush()
            return None

        # Within active window
        bucket.tokens += 1
        if lockout_threshold and bucket.tokens >= lockout_threshold:
            bucket.blocked_until = now_utc + timedelta(seconds=lockout_seconds)
            await self.session.flush()
            logger.warning("Dimension %s triggered security lockout for %ds", dimension_key, lockout_seconds)
            return lockout_seconds

        if bucket.tokens > max_requests:
            remaining_window = max(1, int(window_seconds - elapsed))
            await self.session.flush()
            return remaining_window

        await self.session.flush()
        return None

    async def is_blocked(self, dimension_key: str) -> int | None:
        """Check if dimension is currently locked out without incrementing counter (P2-LIM-004)."""
        now_utc = datetime.now(UTC)
        stmt = (
            select(RateLimitBucket)
            .where(RateLimitBucket.key == dimension_key)
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        bucket = result.scalar_one_or_none()
        if bucket is None or bucket.blocked_until is None:
            return None

        if bucket.blocked_until > now_utc:
            return max(1, int((bucket.blocked_until - now_utc).total_seconds()))

        # Lockout expired
        bucket.blocked_until = None
        bucket.tokens = 0
        await self.session.flush()
        return None

    async def record_failure(
        self,
        dimension_key: str,
        window_seconds: int = 900,
        lockout_threshold: int = 5,
        lockout_seconds: int = 900,
    ) -> int | None:
        """Record an authentication failure and enforce progressive lockout (P2-LIM-004)."""
        now_utc = datetime.now(UTC)
        stmt = (
            select(RateLimitBucket)
            .where(RateLimitBucket.key == dimension_key)
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        bucket = result.scalar_one_or_none()

        if bucket is None:
            bucket = RateLimitBucket(
                key=dimension_key,
                tokens=1,
                last_updated=now_utc,
                blocked_until=None,
            )
            self.session.add(bucket)
            await self.session.flush()
            return None

        elapsed = (now_utc - bucket.last_updated).total_seconds()
        if elapsed > window_seconds:
            bucket.tokens = 1
            bucket.last_updated = now_utc
            bucket.blocked_until = None
        else:
            bucket.tokens += 1
            bucket.last_updated = now_utc

        if bucket.tokens >= lockout_threshold:
            bucket.blocked_until = now_utc + timedelta(seconds=lockout_seconds)
            await self.session.flush()
            logger.warning("Dimension %s exceeded failure threshold; locked out for %ds", dimension_key, lockout_seconds)
            return lockout_seconds

        await self.session.flush()
        return None

    async def reset(self, dimension_key: str) -> None:
        """Reset failure counter and lockout status on successful authentication (P2-LIM-004)."""
        stmt = (
            select(RateLimitBucket)
            .where(RateLimitBucket.key == dimension_key)
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        bucket = result.scalar_one_or_none()
        if bucket is not None:
            bucket.tokens = 0
            bucket.blocked_until = None
            await self.session.flush()
