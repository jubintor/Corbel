"""Domain exceptions for Phase 7 Adaptive Monitors & Exception Detection."""

from typing import Any

from fastapi import status

from corbel.core.exceptions import CorbelException


class MonitorException(CorbelException):
    """Base exception for all operational monitoring domain errors."""

    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, status_code=status_code, details=details)


class MonitorNotFoundException(MonitorException):
    """Raised when a requested monitor cannot be found in the active project scope."""

    def __init__(self, monitor_id: str) -> None:
        super().__init__(
            message=f"Operational monitor '{monitor_id}' not found in active project scope.",
            status_code=status.HTTP_404_NOT_FOUND,
            details={"monitor_id": monitor_id},
        )


class FindingNotFoundException(MonitorException):
    """Raised when an exception finding cannot be found in the active project scope."""

    def __init__(self, finding_id: str) -> None:
        super().__init__(
            message=f"Finding exception '{finding_id}' not found in active project scope.",
            status_code=status.HTTP_404_NOT_FOUND,
            details={"finding_id": finding_id},
        )


class MonitorValidationException(MonitorException):
    """Raised when monitor or rule configuration parameters fail validation."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            details=details,
        )


class MonitorEvaluationException(MonitorException):
    """Raised when deterministic monitor evaluation encounters unrecoverable data or execution failure."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details=details,
        )


class FindingTransitionException(MonitorException):
    """Raised when an illegal finding lifecycle state transition is attempted."""

    def __init__(self, current_status: str, target_status: str) -> None:
        super().__init__(
            message=f"Cannot transition finding from '{current_status}' to '{target_status}'.",
            status_code=status.HTTP_409_CONFLICT,
            details={"current_status": current_status, "target_status": target_status},
        )
