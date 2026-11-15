"""Centralized exception definitions and HTTP error handlers for Corbel."""

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from corbel.core.logging import get_correlation_id

logger = logging.getLogger(__name__)


class ErrorResponse(BaseModel):
    """Standardized API error response format across all Corbel endpoints."""

    error: str = Field(..., description="High-level error code or classification")
    message: str = Field(..., description="Human-readable description of the error")
    details: Any = Field(default=None, description="Detailed validation errors or contextual diagnostic data")
    correlation_id: str | None = Field(default=None, description="Unique correlation identifier for log tracing")


class CorbelException(Exception):
    """Base exception for application-level errors in Corbel."""

    def __init__(
        self,
        message: str,
        error_code: str = "INTERNAL_ERROR",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details


class DatabaseUnavailableException(CorbelException):
    """Raised when the database connection fails or cannot be reached."""

    def __init__(self, message: str = "Database is unavailable", details: Any = None) -> None:
        super().__init__(
            message=message,
            error_code="DATABASE_UNAVAILABLE",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            details=details,
        )


class ResourceNotFoundException(CorbelException):
    """Raised when a requested resource does not exist."""

    def __init__(self, message: str = "Resource not found", details: Any = None) -> None:
        super().__init__(
            message=message,
            error_code="RESOURCE_NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
            details=details,
        )


def setup_exception_handlers(app: FastAPI) -> None:
    """Register standardized exception handlers on the FastAPI application."""

    @app.exception_handler(CorbelException)
    async def corbel_exception_handler(_request: Request, exc: CorbelException) -> JSONResponse:
        correlation_id = get_correlation_id()
        logger.warning(f"Handled application exception [{exc.error_code}]: {exc.message}")
        content = ErrorResponse(
            error=exc.error_code,
            message=exc.message,
            details=exc.details,
            correlation_id=correlation_id,
        ).model_dump()
        return JSONResponse(status_code=exc.status_code, content=content)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        correlation_id = get_correlation_id()
        logger.info(f"Request validation failed: {exc.errors()}")
        content = ErrorResponse(
            error="VALIDATION_ERROR",
            message="Request input validation failed",
            details=jsonable_encoder(exc.errors()),
            correlation_id=correlation_id,
        ).model_dump()
        return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content=content)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
        correlation_id = get_correlation_id()
        logger.error(f"Unhandled server exception: {exc}", exc_info=True)
        content = ErrorResponse(
            error="INTERNAL_SERVER_ERROR",
            message="An unexpected server error occurred. Please contact the administrator with the correlation ID.",
            details=None,
            correlation_id=correlation_id,
        ).model_dump()
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=content)
