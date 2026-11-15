"""Domain exceptions for Process Intelligence & Event Mining (Phase 6)."""

from typing import Any

from corbel.core.exceptions import CorbelException


class ProcessNotFoundException(CorbelException):
    """Raised when a requested process definition is not found."""

    def __init__(self, message: str = "Process not found", details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message,
            error_code="PROCESS_NOT_FOUND",
            status_code=404,
            details=details,
        )


class ProcessCaseNotFoundException(CorbelException):
    """Raised when a requested process case is not found."""

    def __init__(self, message: str = "Process case not found", details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message,
            error_code="PROCESS_CASE_NOT_FOUND",
            status_code=404,
            details=details,
        )


class ProcessValidationException(CorbelException):
    """Raised when process configuration or event parameters fail validation."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message,
            error_code="PROCESS_VALIDATION_ERROR",
            status_code=422,
            details=details,
        )


class ProcessReconstructionException(CorbelException):
    """Raised when event log reconstruction fails due to invalid datasets or schema mismatches."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message,
            error_code="PROCESS_RECONSTRUCTION_ERROR",
            status_code=422,
            details=details,
        )
