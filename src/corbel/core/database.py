"""PostgreSQL database engine, session management, and connectivity health check."""

import asyncio
import logging
import time
from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from corbel.core.config import get_settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Base declarative class for all SQLAlchemy ORM models in Corbel."""
    pass


# Global engine instance initialized on startup or lazily
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Return or initialize singleton AsyncEngine."""
    global _engine
    if _engine is None:
        settings = get_settings()
        if settings.ENVIRONMENT == "test":
            _engine = create_async_engine(
                settings.async_database_url,
                echo=settings.DEBUG,
                poolclass=NullPool,
            )
        else:
            _engine = create_async_engine(
                settings.async_database_url,
                echo=settings.DEBUG,
                pool_pre_ping=True,
                pool_size=settings.DB_POOL_SIZE,
                max_overflow=settings.DB_MAX_OVERFLOW,
                pool_timeout=settings.DB_POOL_TIMEOUT_SECONDS,
                pool_recycle=settings.DB_POOL_RECYCLE_SECONDS,
            )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return or initialize singleton async_sessionmaker."""
    global _session_factory
    if _session_factory is None:
        engine = get_engine()
        _session_factory = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for yielding transactional async database sessions."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def check_database_health() -> tuple[bool, str, float]:
    """Check database connectivity with timeout and verify system metadata (P1-LIM-009, P1-LIM-012)."""
    settings = get_settings()
    timeout = getattr(settings, "DB_HEALTH_CHECK_TIMEOUT_SECONDS", 3.0)
    start_time = time.perf_counter()
    try:
        async with asyncio.timeout(timeout):
            engine = get_engine()
            async with engine.connect() as conn:
                # 1. Execute basic ping
                await conn.execute(text("SELECT 1"))
                # 2. Query system_metadata to verify schema foundation baseline
                result = await conn.execute(
                    text("SELECT value FROM system_metadata WHERE key = 'corbel_platform_version' LIMIT 1")
                )
                version_val = result.scalar_one_or_none()
                schema_info = f" (schema v{version_val})" if version_val else ""
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return True, f"PostgreSQL connection operational{schema_info}", latency_ms
    except TimeoutError:
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.warning(f"Database health check timed out after {timeout}s")
        return False, f"Database health check timed out after {timeout}s", latency_ms
    except Exception as exc:
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.warning(f"Database health check failed: {exc}")
        return False, str(exc), latency_ms


async def close_db_engine() -> None:
    """Dispose of the database engine and connection pool on shutdown."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("Database connection engine closed.")
