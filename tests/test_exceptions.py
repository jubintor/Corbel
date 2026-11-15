"""Automated test suite for centralized error handling and standardized JSON responses."""

import pytest
from fastapi import APIRouter
from httpx import AsyncClient

from corbel.core.exceptions import CorbelException, ResourceNotFoundException
from corbel.main import app

error_router = APIRouter(prefix="/test-errors")


@error_router.get("/custom-exception")
async def trigger_custom_exception() -> None:
    raise ResourceNotFoundException(message="Requested test entity was not found", details={"entity_id": 42})


@error_router.get("/generic-corbel-exception")
async def trigger_generic_corbel_exception() -> None:
    raise CorbelException(
        message="Simulated application failure",
        error_code="TEST_APP_ERROR",
        status_code=400,
        details=["detail_1", "detail_2"],
    )


app.include_router(error_router)


@pytest.mark.asyncio
async def test_handled_resource_not_found(async_client: AsyncClient) -> None:
    """Verify ResourceNotFoundException maps to standardized 404 ErrorResponse."""
    response = await async_client.get("/test-errors/custom-exception")
    assert response.status_code == 404
    data = response.json()

    assert data["error"] == "RESOURCE_NOT_FOUND"
    assert "not found" in data["message"]
    assert data["details"]["entity_id"] == 42
    assert "correlation_id" in data


@pytest.mark.asyncio
async def test_handled_corbel_exception(async_client: AsyncClient) -> None:
    """Verify CorbelException maps to configured status code and ErrorResponse."""
    response = await async_client.get("/test-errors/generic-corbel-exception")
    assert response.status_code == 400
    data = response.json()

    assert data["error"] == "TEST_APP_ERROR"
    assert data["message"] == "Simulated application failure"
    assert len(data["details"]) == 2
