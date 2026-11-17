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


@pytest.mark.asyncio
async def test_correlation_id_propagated_to_structured_logs(async_client: AsyncClient) -> None:
    """Verify correlation ID is present in structured request completion logs (P1-LIM-001)."""
    import io
    import json
    import logging

    from corbel.core.logging import JSONLogFormatter

    log_stream = io.StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.setFormatter(JSONLogFormatter())
    logger = logging.getLogger("corbel.core.middleware")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)

    try:
        custom_cid = "log-tracing-cid-5555"
        response = await async_client.get(
            "/",
            headers={"X-Correlation-ID": custom_cid},
        )
        assert response.status_code == 200

        logs = [
            json.loads(line)
            for line in log_stream.getvalue().splitlines()
            if line.strip().startswith("{")
        ]
        matching = [entry for entry in logs if entry.get("path") == "/"]
        assert len(matching) > 0
        assert matching[0].get("correlation_id") == custom_cid
    finally:
        logger.removeHandler(handler)
