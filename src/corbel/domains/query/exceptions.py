"""Domain exceptions for structured querying and query compilation."""

from typing import Any

from corbel.core.exceptions import CorbelException


class QueryException(CorbelException):
    """Base exception for structured query operations."""

    def __init__(
        self,
        message: str,
        error_code: str = "QUERY_ERROR",
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code=error_code,
            status_code=status_code,
            details=details,
        )


class EntityNotFoundQueryException(QueryException):
    """Raised when the target business object entity is not found in the project ontology."""

    def __init__(self, entity_name: str) -> None:
        super().__init__(
            message=f"Business entity '{entity_name}' does not exist in the project ontology.",
            error_code="QUERY_ENTITY_NOT_FOUND",
            status_code=404,
            details={"entity_name": entity_name},
        )


class QueryValidationException(QueryException):
    """Raised when a structured query AST contains invalid fields, operators, or types."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message,
            error_code="QUERY_VALIDATION_ERROR",
            status_code=422,
            details=details,
        )


class UnmappedPropertyQueryException(QueryException):
    """Raised when a query requests or filters on a property that has no confirmed dataset mapping."""

    def __init__(self, entity_name: str, property_name: str) -> None:
        super().__init__(
            message=(
                f"Property '{property_name}' on business entity '{entity_name}' "
                "is not mapped to any confirmed dataset column. Cannot execute query."
            ),
            error_code="QUERY_UNMAPPED_PROPERTY",
            status_code=400,
            details={"entity_name": entity_name, "property_name": property_name},
        )


class QueryExecutionException(QueryException):
    """Raised when query execution in the sandbox fails."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message,
            error_code="QUERY_EXECUTION_ERROR",
            status_code=500,
            details=details,
        )
