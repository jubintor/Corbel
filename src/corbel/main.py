"""Main FastAPI application entry point for Corbel."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from corbel.api.v1.api import api_router
from corbel.api.v1.endpoints.health import SystemHealthResponse, get_system_health
from corbel.core.config import get_settings
from corbel.core.database import close_db_engine
from corbel.core.exceptions import ErrorResponse, setup_exception_handlers
from corbel.core.logging import setup_logging
from corbel.core.middleware import CorrelationIdMiddleware, RequestLoggingMiddleware

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan managing startup configuration and shutdown disposal."""
    settings = get_settings()
    setup_logging(log_level=settings.LOG_LEVEL, log_format=settings.LOG_FORMAT)
    logger.info(
        f"Starting {settings.APP_NAME} v{settings.APP_VERSION} "
        f"[env={settings.ENVIRONMENT}, debug={settings.DEBUG}]"
    )
    yield
    logger.info(f"Shutting down {settings.APP_NAME}...")
    await close_db_engine()
    logger.info(f"{settings.APP_NAME} shutdown complete.")


def create_application() -> FastAPI:
    """Factory function for instantiating the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=f"{settings.APP_NAME} — Enterprise AI Platform",
        description=(
            "Corbel connects enterprise data, discovers business context, understands operations, "
            "identifies exceptions, and executes governed business actions."
        ),
        version=settings.APP_VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        responses={
            500: {"model": ErrorResponse, "description": "Standardized platform error response"},
        },
        lifespan=lifespan,
    )

    # 1. Register Core Middlewares
    # Middlewares execute in reverse order of addition in Starlette.
    # Execution sequence: CORSMiddleware -> CorrelationIdMiddleware -> RequestLoggingMiddleware -> Router
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 2. Register Centralized Exception Handlers
    setup_exception_handlers(app)

    # 3. Register Versioned API Routes
    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    # 4. Root convenience and infrastructure probe endpoints
    @app.get("/", summary="Platform index", include_in_schema=False)
    async def root_index() -> dict[str, str]:
        return {
            "app": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "status": "operational",
            "docs_url": "/docs",
            "health_url": f"{settings.API_V1_PREFIX}/health",
        }

    @app.get(
        "/health",
        response_model=SystemHealthResponse,
        summary="Platform root health probe",
        description="Direct liveness and database readiness probe returning HTTP 200 without redirect (P1-LIM-013).",
        include_in_schema=False,
    )
    async def root_health(response: Response) -> SystemHealthResponse:
        return await get_system_health(response)

    return app


app = create_application()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "corbel.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
