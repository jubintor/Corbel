"""Pydantic schemas for Phase 5 Structured Querying & Natural Language Queries."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from corbel.ai.schemas import TokenUsage


class QueryOperator(str, Enum):
    """Supported filter operators for structured query AST."""

    EQ = "eq"
    NEQ = "neq"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    IN = "in"
    NOT_IN = "not_in"
    IS_NULL = "is_null"
    IS_NOT_NULL = "is_not_null"


class SortDirection(str, Enum):
    """Sort direction for query ordering."""

    ASC = "asc"
    DESC = "desc"


class QueryFilter(BaseModel):
    """Atomic filter condition on a business object property."""

    field: str = Field(description="Property name to filter on (e.g., 'total_amount', 'status')")
    operator: QueryOperator = Field(default=QueryOperator.EQ, description="Comparison operator")
    value: Any = Field(default=None, description="Filter operand value")


class QuerySort(BaseModel):
    """Ordering specification for structured queries."""

    field: str = Field(description="Property name to sort by")
    direction: SortDirection = Field(default=SortDirection.ASC, description="Sort direction: asc or desc")


class QueryJoin(BaseModel):
    """Relationship traversal specification for querying across connected entities."""

    relationship_name: str = Field(description="Name of the confirmed relationship to traverse")
    fields: list[str] = Field(default_factory=list, description="Properties to project from the joined entity")


class StructuredQueryRequest(BaseModel):
    """Strongly typed query AST representing a validated semantic query."""

    entity_name: str = Field(description="Target business entity name (e.g., 'PurchaseOrder')")
    fields: list[str] = Field(
        default_factory=list,
        description="List of property names to select (empty selects all mapped properties)",
    )
    filters: list[QueryFilter] = Field(
        default_factory=list,
        description="Filter conditions evaluated with logical AND conjunction",
    )
    sorts: list[QuerySort] = Field(
        default_factory=list,
        description="Ordering criteria",
    )
    joins: list[QueryJoin] = Field(
        default_factory=list,
        description="Optional relationship traversal joins",
    )
    limit: int = Field(default=50, ge=1, le=500, description="Maximum number of rows to return (capped at 500)")
    offset: int = Field(default=0, ge=0, description="Number of rows to skip for pagination")
    nlq_reference: str | None = Field(
        default=None,
        description="Optional server-issued NLQ compilation reference for execution audit attribution",
    )


class StructuredQueryResponse(BaseModel):
    """Tabular query execution results with safety audit metadata."""

    entity_name: str
    columns: list[str]
    rows: list[dict[str, Any]]
    total_count: int
    limit: int
    offset: int
    compiled_sql: str
    parameters: list[Any]
    execution_time_ms: float
    query_plan: list[str]


class NaturalLanguageQueryRequest(BaseModel):
    """Request to compile a natural language question into a structured query AST."""

    prompt: str = Field(
        min_length=2,
        max_length=2000,
        description="Natural language query string (e.g. 'Show purchase orders exceeding 10000')",
    )
    target_entity: str | None = Field(
        default=None,
        description="Optional hint specifying the target business entity",
    )


class NaturalLanguageQueryResponse(BaseModel):
    """Response containing parsed query AST, compiled SQL, and explanation."""

    prompt: str
    parsed_query: StructuredQueryRequest
    compiled_sql: str
    explanation: str
    token_usage: TokenUsage
    latency_ms: float
    nlq_reference: str = Field(description="Server-controlled opaque compilation reference for audit attribution")


class QueryablePropertySchema(BaseModel):
    """Metadata describing a queryable entity property."""

    name: str
    display_name: str | None
    data_type: str
    is_primary_key: bool
    is_nullable: bool
    is_mapped: bool
    source_column: str | None


class QueryableEntitySchema(BaseModel):
    """Metadata describing an entity available for querying."""

    id: str
    name: str
    display_name: str
    description: str | None
    properties: list[QueryablePropertySchema]
    available_relationships: list[str]


class QuerySchemaResponse(BaseModel):
    """Full project ontology query schema describing all queryable entities and properties."""

    project_id: str
    entities: list[QueryableEntitySchema]


class QueryExecutionAuditResponse(BaseModel):
    """Audit record of a structured query execution."""

    id: str
    project_id: str
    user_id: str
    entity_name: str
    query_ast: dict[str, Any]
    compiled_sql: str
    row_count: int
    execution_time_ms: float
    is_nlq: bool
    nlq_prompt: str | None
    token_count: int | None
    created_at: str

    model_config = ConfigDict(from_attributes=True)
