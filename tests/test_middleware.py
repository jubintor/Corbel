"""Automated test suite for request middlewares."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_correlation_id_auto_generation(async_client: AsyncClient) -> None:
    """Verify that requests without correlation ID receive a generated UUID."""
    response = await async_client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert "X-Correlation-ID" in response.headers
    correlation_id = response.headers["X-Correlation-ID"]
    assert len(correlation_id) > 10


@pytest.mark.asyncio
async def test_correlation_id_preservation(async_client: AsyncClient) -> None:
    """Verify that client-provided correlation ID is preserved and returned."""
    custom_cid = "test-correlation-uuid-9999"
    response = await async_client.get(
        "/api/v1/health/live",
        headers={"X-Correlation-ID": custom_cid},
    )
    assert response.status_code == 200
    assert response.headers.get("X-Correlation-ID") == custom_cid
