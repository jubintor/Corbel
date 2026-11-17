"""Automated test suite for system health endpoints."""

from unittest.mock import patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_liveness_endpoint(async_client: AsyncClient) -> None:
    """Verify lightweight liveness probe returns 200 and alive status."""
    response = await async_client.get("/api/v1/health/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "alive"
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_health_endpoint_healthy_db(async_client: AsyncClient) -> None:
    """Verify health endpoint returns 200 and full telemetry when DB is healthy."""
    with patch("corbel.api.v1.endpoints.health.check_database_health") as mock_check:
        mock_check.return_value = (True, "PostgreSQL connection pool healthy", 1.85)

        response = await async_client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "healthy"
        assert data["app_name"] == "Corbel"
        assert data["version"] == "0.1.0"
        assert data["environment"] == "test"
        assert "timestamp" in data

        assert data["database"]["status"] == "connected"
        assert data["database"]["latency_ms"] == 1.85
        assert data["database"]["details"] == "PostgreSQL connection pool healthy"


@pytest.mark.asyncio
async def test_health_endpoint_unhealthy_db(async_client: AsyncClient) -> None:
    """Verify health endpoint returns 503 Service Unavailable when DB is disconnected."""
    with patch("corbel.api.v1.endpoints.health.check_database_health") as mock_check:
        mock_check.return_value = (False, "Connection refused on port 5432", 50.2)

        response = await async_client.get("/api/v1/health")
        assert response.status_code == 503
        data = response.json()

        assert data["status"] == "unhealthy"
        assert data["database"]["status"] == "disconnected"
        assert data["database"]["latency_ms"] is None
        assert "Connection refused" in data["database"]["details"]


@pytest.mark.asyncio
async def test_root_index_endpoint(async_client: AsyncClient) -> None:
    """Verify root index provides service information."""
    response = await async_client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["app"] == "Corbel"
    assert data["status"] == "operational"
    assert data["docs_url"] == "/docs"


@pytest.mark.asyncio
async def test_root_health_direct(async_client: AsyncClient) -> None:
    """Verify /health returns HTTP 200 directly without redirect for cloud probers (P1-LIM-013)."""
    with patch("corbel.api.v1.endpoints.health.check_database_health") as mock_check:
        mock_check.return_value = (True, "PostgreSQL connection pool healthy", 1.2)
        response = await async_client.get("/health", follow_redirects=False)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["database"]["status"] == "connected"


@pytest.mark.asyncio
async def test_live_database_health_integration() -> None:
    """Genuine unmocked integration test verifying real PostgreSQL connectivity and metadata (P1-LIM-010, P1-LIM-012)."""
    from corbel.core.database import check_database_health

    is_healthy, message, latency_ms = await check_database_health()
    assert is_healthy is True
    assert "operational" in message.lower()
    assert latency_ms > 0


@pytest.mark.asyncio
async def test_database_health_timeout() -> None:
    """Verify database health check enforces timeout on unresponsive connections (P1-LIM-009)."""
    import asyncio
    from unittest.mock import MagicMock

    from corbel.core.database import check_database_health

    class HangingAsyncContextManager:
        async def __aenter__(self) -> "HangingAsyncContextManager":
            await asyncio.sleep(5.0)
            return self

        async def __aexit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
            pass

    with patch("corbel.core.database.get_engine") as mock_get_engine, \
         patch("corbel.core.database.get_settings") as mock_settings:
        mock_engine = MagicMock()
        mock_engine.connect.return_value = HangingAsyncContextManager()
        mock_get_engine.return_value = mock_engine

        mock_cfg = MagicMock()
        mock_cfg.DB_HEALTH_CHECK_TIMEOUT_SECONDS = 0.05
        mock_settings.return_value = mock_cfg

        is_healthy, message, latency_ms = await check_database_health()
        assert is_healthy is False
        assert "timed out" in message
