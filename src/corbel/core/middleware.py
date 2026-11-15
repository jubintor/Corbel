"""HTTP middleware for correlation ID tracing, timing, and request logging."""

import logging
import time
import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from corbel.core.logging import get_correlation_id, set_correlation_id

logger = logging.getLogger(__name__)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Middleware extracting or generating correlation ID for request tracing."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Check incoming headers for existing correlation ID
        correlation_id = (
            request.headers.get("X-Correlation-ID")
            or request.headers.get("X-Request-ID")
            or str(uuid.uuid4())
        )
        set_correlation_id(correlation_id)

        try:
            response = await call_next(request)
            response.headers["X-Correlation-ID"] = correlation_id
            return response
        finally:
            set_correlation_id(None)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware that measures and logs request processing latency."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start_time = time.perf_counter()
        correlation_id = get_correlation_id()
        path = request.url.path
        method = request.method

        try:
            response = await call_next(request)
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            # Avoid noisy logs for health probes
            if not path.endswith("/health") and not path.endswith("/health/live"):
                logger.info(
                    f"{method} {path} - {response.status_code} ({duration_ms}ms)",
                    extra={"method": method, "path": path, "status_code": response.status_code, "duration_ms": duration_ms},
                )
            return response
        except Exception as exc:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.error(
                f"{method} {path} - Exception: {exc} ({duration_ms}ms)",
                extra={"method": method, "path": path, "duration_ms": duration_ms, "correlation_id": correlation_id},
            )
            raise
