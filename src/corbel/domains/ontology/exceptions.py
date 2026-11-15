"""Domain-specific exceptions for Ontology Engine & Semantic Discovery."""

from corbel.core.exceptions import CorbelException


class BusinessObjectNotFoundException(CorbelException):
    """Raised when a requested Business Object does not exist within the project context."""

    def __init__(self, message: str = "Business Object not found") -> None:
        super().__init__(message=message, status_code=404)


class BusinessObjectAlreadyExistsException(CorbelException):
    """Raised when attempting to create a Business Object with a name already used in the project."""

    def __init__(self, message: str = "A Business Object with this name already exists in the project") -> None:
        super().__init__(message=message, status_code=409)


class PropertyNotFoundException(CorbelException):
    """Raised when a requested Property does not exist on the Business Object."""

    def __init__(self, message: str = "Property not found on the specified Business Object") -> None:
        super().__init__(message=message, status_code=404)


class PropertyAlreadyExistsException(CorbelException):
    """Raised when attempting to add a Property with a duplicate name on a Business Object."""

    def __init__(self, message: str = "A Property with this name already exists on the Business Object") -> None:
        super().__init__(message=message, status_code=409)


class RelationshipNotFoundException(CorbelException):
    """Raised when a requested Relationship does not exist within the project context."""

    def __init__(self, message: str = "Relationship not found") -> None:
        super().__init__(message=message, status_code=404)


class RelationshipAlreadyExistsException(CorbelException):
    """Raised when attempting to create a duplicate Relationship between the same endpoints."""

    def __init__(self, message: str = "A relationship with this name and endpoints already exists in the project") -> None:
        super().__init__(message=message, status_code=409)


class InvalidRelationshipEndpointsException(CorbelException):
    """Raised when relationship endpoints are invalid (e.g., cross-project or missing objects)."""

    def __init__(self, message: str = "Relationship endpoints must reference valid Business Objects in the same project") -> None:
        super().__init__(message=message, status_code=400)


class PropertyMappingNotFoundException(CorbelException):
    """Raised when a requested Property Mapping does not exist."""

    def __init__(self, message: str = "Property mapping not found") -> None:
        super().__init__(message=message, status_code=404)


class InvalidPropertyMappingException(CorbelException):
    """Raised when attempting to create an invalid mapping (e.g. cross-project, invalid column)."""

    def __init__(self, message: str = "Invalid property mapping specification") -> None:
        super().__init__(message=message, status_code=400)


class IncompatibleMappingTypeException(CorbelException):
    """Raised when attempting to map a column to a property with an incompatible data type."""

    def __init__(self, message: str = "Column data type is incompatible with target property data type") -> None:
        super().__init__(message=message, status_code=400)
