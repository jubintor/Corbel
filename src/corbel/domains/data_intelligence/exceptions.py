"""Domain exceptions for Data Intelligence & Profiling."""

import uuid
from typing import Any

from fastapi import status

from corbel.core.exceptions import CorbelException


class DataIntelligenceException(CorbelException):
    """Base exception for Data Intelligence operations."""

    def __init__(
        self,
        message: str,
        error_code: str = "DATA_INTELLIGENCE_ERROR",
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: Any = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code=error_code,
            status_code=status_code,
            details=details,
        )


class DataSourceNotFoundException(DataIntelligenceException):
    """Raised when a requested Data Source does not exist or is not in scope."""

    def __init__(self, source_id: uuid.UUID) -> None:
        super().__init__(
            message=f"Data Source '{source_id}' was not found in this project.",
            error_code="DATA_SOURCE_NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
            details={"source_id": str(source_id)},
        )


class DatasetNotFoundException(DataIntelligenceException):
    """Raised when a requested Dataset does not exist or is not in scope."""

    def __init__(self, dataset_id: uuid.UUID) -> None:
        super().__init__(
            message=f"Dataset '{dataset_id}' was not found in this project.",
            error_code="DATASET_NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
            details={"dataset_id": str(dataset_id)},
        )


class DatasetVersionNotFoundException(DataIntelligenceException):
    """Raised when a requested Dataset Version does not exist."""

    def __init__(self, dataset_id: uuid.UUID, version_id_or_number: Any) -> None:
        super().__init__(
            message=f"Dataset Version '{version_id_or_number}' not found for dataset '{dataset_id}'.",
            error_code="DATASET_VERSION_NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
            details={"dataset_id": str(dataset_id), "version": str(version_id_or_number)},
        )


class UnsupportedFileFormatException(DataIntelligenceException):
    """Raised when an uploaded file is not among supported formats (CSV, JSON, XLSX)."""

    def __init__(self, file_extension: str, supported: list[str]) -> None:
        super().__init__(
            message=f"Unsupported file format '{file_extension}'. Supported formats: {', '.join(supported)}.",
            error_code="UNSUPPORTED_FILE_FORMAT",
            status_code=status.HTTP_400_BAD_REQUEST,
            details={"extension": file_extension, "supported_formats": supported},
        )


class FileSizeLimitExceededException(DataIntelligenceException):
    """Raised when an uploaded dataset exceeds the configured file size limit."""

    def __init__(self, size_bytes: int, max_bytes: int) -> None:
        super().__init__(
            message=(
                f"File size ({size_bytes} bytes) exceeds maximum permitted limit "
                f"of {max_bytes} bytes ({max_bytes // (1024 * 1024)} MB)."
            ),
            error_code="FILE_SIZE_LIMIT_EXCEEDED",
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            details={"size_bytes": size_bytes, "max_bytes": max_bytes},
        )


class EmptyDatasetException(DataIntelligenceException):
    """Raised when an uploaded file contains 0 bytes or has no rows."""

    def __init__(self, message: str = "Uploaded dataset is empty and contains no data.") -> None:
        super().__init__(
            message=message,
            error_code="EMPTY_DATASET",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class InvalidDatasetHeaderException(DataIntelligenceException):
    """Raised when dataset headers are missing, empty, or invalid."""

    def __init__(self, message: str, details: Any = None) -> None:
        super().__init__(
            message=message,
            error_code="INVALID_DATASET_HEADER",
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details,
        )


class MalformedDatasetException(DataIntelligenceException):
    """Raised when the dataset structure or encoding is corrupt or malformed."""

    def __init__(self, message: str, details: Any = None) -> None:
        super().__init__(
            message=message,
            error_code="MALFORMED_DATASET",
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details,
        )


class UnsafeFilenameException(DataIntelligenceException):
    """Raised when a filename contains path traversal attacks or prohibited characters."""

    def __init__(self, filename: str) -> None:
        super().__init__(
            message="Provided filename is unsafe or contains prohibited path traversal sequences.",
            error_code="UNSAFE_FILENAME",
            status_code=status.HTTP_400_BAD_REQUEST,
            details={"filename": filename},
        )
