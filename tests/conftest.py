"""Pytest configuration and shared test fixtures for Corbel backend tests."""

import os
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

# Force test environment variables before application import
os.environ["ENVIRONMENT"] = "test"
os.environ["DEBUG"] = "true"
os.environ.setdefault("POSTGRES_SERVER", "localhost")
os.environ.setdefault("POSTGRES_PORT", os.environ.get("POSTGRES_PORT", "5433"))
os.environ.setdefault("POSTGRES_USER", "corbel")
os.environ.setdefault("POSTGRES_PASSWORD", "corbel_secret_password")
os.environ.setdefault("POSTGRES_DB", "corbel_db")
os.environ.setdefault("RATE_LIMIT_LOGIN_PER_MINUTE", "10000")
os.environ.setdefault("RATE_LIMIT_REGISTER_PER_MINUTE", "10000")
os.environ.setdefault("RATE_LIMIT_LOGIN_FAILURES_LOCKOUT", "1000")

from corbel.core.database import close_db_engine
from corbel.main import app


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
async def cleanup_database_engine() -> AsyncGenerator[None, None]:
    """Clean up and dispose database engine between tests to avoid cross-loop issues."""
    yield
    await close_db_engine()


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Yield an asynchronous HTTP test client bound to the FastAPI application."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
