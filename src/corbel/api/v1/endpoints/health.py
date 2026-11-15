"""Health check endpoints for system liveness and database connectivity verification."""

from datetime import UTC, datetime

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field

from corbel.core.config import get_settings
from corbel.core.database import check_database_health

router = APIRouter()


class DatabaseHealth(BaseModel):
    """Health status and latency metrics for PostgreSQL database."""

    status: str = Field(..., description="Connection status: connected, disconnected, or degraded")
    latency_ms: float | None = Field(default=None, description="Roundtrip query latency in milliseconds")
    details: str | None = Field(default=None, description="Diagnostic message or error description")


class SystemHealthResponse(BaseModel):
    """Comprehensive system health model returned by the health check endpoint."""

    status: str = Field(..., description="Overall platform status: healthy, degraded, or unhealthy")
    app_name: str = Field(..., description="Application name")
    version: str = Field(..., description="Semantic application version")
    environment: str = Field(..., description="Current deployment environment")
    timestamp: datetime = Field(..., description="UTC timestamp of the health check evaluation")
    database: DatabaseHealth = Field(..., description="PostgreSQL connectivity health check")


class LivenessResponse(BaseModel):
    """Simple liveness probe response for orchestrator checks."""

    status: str = Field(default="alive", description="Process liveness indicator")
    timestamp: datetime = Field(..., description="UTC timestamp")


@router.get(
    "/health",
    response_model=SystemHealthResponse,
    summary="Comprehensive system health check",
    description="Evaluates application uptime, version metadata, and active PostgreSQL database connectivity.",
    status_code=status.HTTP_200_OK,
)
async def get_system_health(response: Response) -> SystemHealthResponse:
    """Evaluate overall system health including live database ping."""
    settings = get_settings()
    is_db_healthy, db_message, db_latency = await check_database_health()

    db_health = DatabaseHealth(
        status="connected" if is_db_healthy else "disconnected",
        latency_ms=db_latency if is_db_healthy else None,
        details=db_message if not is_db_healthy else "PostgreSQL connection pool healthy",
    )

    overall_status = "healthy" if is_db_healthy else "unhealthy"
    if not is_db_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return SystemHealthResponse(
        status=overall_status,
        app_name=settings.APP_NAME,
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
        timestamp=datetime.now(UTC),
        database=db_health,
    )


@router.get(
    "/health/live",
    response_model=LivenessResponse,
    summary="Application liveness probe",
    description="Lightweight process liveness endpoint returning 200 without external I/O.",
)
async def get_liveness() -> LivenessResponse:
    """Return process liveness state for container orchestrator checks."""
    return LivenessResponse(
        status="alive",
        timestamp=datetime.now(UTC),
    )
