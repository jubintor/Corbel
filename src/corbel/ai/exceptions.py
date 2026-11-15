"""Exceptions for the Corbel AI Gateway."""

from typing import Any

from corbel.core.exceptions import CorbelException


class AIGatewayException(CorbelException):
    """Base exception for AI Gateway operations."""

    def __init__(
        self,
        message: str,
        error_code: str = "AI_GATEWAY_ERROR",
        status_code: int = 502,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code=error_code,
            status_code=status_code,
            details=details,
        )


class ModelProviderAuthException(AIGatewayException):
    """Raised when authentication with the AI provider fails."""

    def __init__(self, provider: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=f"Authentication failed for AI provider '{provider}'. Please check API key configuration.",
            error_code="AI_PROVIDER_AUTH_ERROR",
            status_code=502,
            details=details,
        )


class ModelProviderTimeoutException(AIGatewayException):
    """Raised when an AI provider call times out."""

    def __init__(self, provider: str, timeout_seconds: float) -> None:
        super().__init__(
            message=f"AI provider '{provider}' request timed out after {timeout_seconds}s.",
            error_code="AI_PROVIDER_TIMEOUT",
            status_code=504,
            details={"provider": provider, "timeout_seconds": timeout_seconds},
        )


class ModelProviderRateLimitException(AIGatewayException):
    """Raised when an AI provider returns rate limit errors."""

    def __init__(self, provider: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=f"Rate limit exceeded for AI provider '{provider}'.",
            error_code="AI_PROVIDER_RATE_LIMIT",
            status_code=429,
            details=details,
        )


class InvalidModelResponseException(AIGatewayException):
    """Raised when an AI provider returns invalid, malformed, or unparseable output."""

    def __init__(self, message: str, raw_response: str | None = None) -> None:
        details: dict[str, Any] = {}
        if raw_response:
            # Truncate raw response to prevent log bloat
            details["raw_sample"] = raw_response[:500]
        super().__init__(
            message=message,
            error_code="AI_INVALID_MODEL_RESPONSE",
            status_code=502,
            details=details,
        )


class UnsupportedModelProviderException(AIGatewayException):
    """Raised when an unsupported AI provider is requested."""

    def __init__(self, provider: str, supported: list[str]) -> None:
        super().__init__(
            message=f"AI provider '{provider}' is not supported. Supported providers: {', '.join(supported)}.",
            error_code="AI_UNSUPPORTED_PROVIDER",
            status_code=400,
            details={"provider": provider, "supported_providers": supported},
        )
