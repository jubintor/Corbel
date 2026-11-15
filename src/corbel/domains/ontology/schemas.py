"""Pydantic schemas for Ontology Engine & Semantic Discovery (Phase 4)."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from corbel.domains.ontology.models import (
    MappingStatus,
    PropertyType,
    RelationshipCardinality,
)


class PropertyCreateRequest(BaseModel):
    """Schema for adding a Property to a Business Object."""

    name: str = Field(..., min_length=1, max_length=255, description="Technical property name")
    display_name: str | None = Field(default=None, max_length=255, description="Human-readable title")
    data_type: PropertyType = Field(default=PropertyType.STRING, description="Attribute data type")
    is_nullable: bool = Field(default=True, description="Whether attribute can contain null values")
    is_primary_key: bool = Field(default=False, description="Whether attribute forms the primary key")
    description: str | None = Field(default=None, max_length=1024, description="Documentation notes")

    model_config = ConfigDict(from_attributes=True)


class PropertyUpdateRequest(BaseModel):
    """Schema for modifying an existing Property."""

    display_name: str | None = Field(default=None, max_length=255)
    data_type: PropertyType | None = Field(default=None)
    is_nullable: bool | None = Field(default=None)
    is_primary_key: bool | None = Field(default=None)
    description: str | None = Field(default=None, max_length=1024)

    model_config = ConfigDict(from_attributes=True)


class PropertyResponse(BaseModel):
    """Public representation of an ontology property."""

    id: uuid.UUID
    business_object_id: uuid.UUID
    name: str
    display_name: str | None = None
    data_type: str
    is_nullable: bool
    is_primary_key: bool
    description: str | None = None
    source_mapping: dict[str, Any] | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BusinessObjectCreateRequest(BaseModel):
    """Schema for creating a new Business Object."""

    name: str = Field(..., min_length=2, max_length=255, description="Technical concept name (e.g. Invoice)")
    display_name: str = Field(..., min_length=2, max_length=255, description="Human-readable title")
    description: str | None = Field(default=None, max_length=1024, description="Business description")
    primary_key_property: str | None = Field(default=None, max_length=255, description="Name of PK property")
    properties: list[PropertyCreateRequest] = Field(default_factory=list, description="Initial properties")

    model_config = ConfigDict(from_attributes=True)


class BusinessObjectUpdateRequest(BaseModel):
    """Schema for updating Business Object metadata."""

    display_name: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=1024)
    primary_key_property: str | None = Field(default=None, max_length=255)

    model_config = ConfigDict(from_attributes=True)


class BusinessObjectResponse(BaseModel):
    """Summary representation of a Business Object."""

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    display_name: str
    description: str | None = None
    primary_key_property: str | None = None
    version: int
    property_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BusinessObjectDetailResponse(BusinessObjectResponse):
    """Detailed representation of a Business Object including all properties."""

    properties: list[PropertyResponse] = Field(default_factory=list)


class RelationshipCreateRequest(BaseModel):
    """Schema for creating a directed relationship between Business Objects."""

    name: str = Field(..., min_length=2, max_length=255, description="Relationship verb (e.g. billed_in)")
    source_object_id: uuid.UUID = Field(..., description="Source Business Object ID")
    target_object_id: uuid.UUID = Field(..., description="Target Business Object ID")
    cardinality: RelationshipCardinality = Field(
        default=RelationshipCardinality.ONE_TO_MANY,
        description="Multiplicity of the connection",
    )
    description: str | None = Field(default=None, max_length=1024)
    join_expression: dict[str, Any] | None = Field(
        default=None,
        description="Join keys, e.g. {'source_property': 'po_id', 'target_property': 'po_id'}",
    )

    model_config = ConfigDict(from_attributes=True)


class RelationshipResponse(BaseModel):
    """Public representation of an ontology relationship."""

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    source_object_id: uuid.UUID
    source_object_name: str | None = None
    target_object_id: uuid.UUID
    target_object_name: str | None = None
    cardinality: str
    description: str | None = None
    join_expression: dict[str, Any] | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PropertyMappingCreateRequest(BaseModel):
    """Schema for creating an explicit or accepted column-to-property mapping."""

    property_id: uuid.UUID = Field(..., description="Target Property ID")
    dataset_id: uuid.UUID = Field(..., description="Source Dataset ID")
    dataset_version_id: uuid.UUID = Field(..., description="Source Dataset Version ID")
    column_name: str = Field(..., min_length=1, max_length=255, description="Source column name")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Match confidence")
    status: MappingStatus = Field(default=MappingStatus.CONFIRMED, description="Initial status")
    explanation: str | None = Field(default="Manual mapping", max_length=1024)

    model_config = ConfigDict(from_attributes=True)


class PropertyMappingResponse(BaseModel):
    """Public representation of a column-to-property mapping."""

    id: uuid.UUID
    project_id: uuid.UUID
    property_id: uuid.UUID
    property_name: str | None = None
    business_object_id: uuid.UUID | None = None
    business_object_name: str | None = None
    dataset_id: uuid.UUID
    dataset_name: str | None = None
    dataset_version_id: uuid.UUID
    column_name: str
    confidence: float
    status: str
    explanation: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SemanticDiscoveryRequest(BaseModel):
    """Parameters for running deterministic semantic discovery against a dataset version."""

    dataset_id: uuid.UUID = Field(..., description="Dataset ID to inspect")
    dataset_version_id: uuid.UUID = Field(..., description="Dataset Version snapshot ID")
    business_object_id: uuid.UUID = Field(..., description="Target Business Object to map against")

    model_config = ConfigDict(from_attributes=True)


class SemanticDiscoveryResponse(BaseModel):
    """Results of a deterministic semantic discovery run."""

    dataset_id: uuid.UUID
    dataset_version_id: uuid.UUID
    business_object_id: uuid.UUID
    business_object_name: str
    suggestions: list[PropertyMappingResponse] = Field(default_factory=list)
    total_suggested: int = 0


class OntologyGraphNode(BaseModel):
    """Node in the ontology graph representing a Business Object."""

    id: str
    name: str
    display_name: str
    description: str | None = None
    properties: list[PropertyResponse] = Field(default_factory=list)
    mapped_properties_count: int = 0
    total_properties_count: int = 0


class OntologyGraphEdge(BaseModel):
    """Edge in the ontology graph representing a directed Relationship."""

    id: str
    name: str
    source: str
    target: str
    cardinality: str
    join_expression: dict[str, Any] | None = None


class OntologyGraphResponse(BaseModel):
    """Complete ontology graph representation for interactive rendering."""

    project_id: uuid.UUID
    nodes: list[OntologyGraphNode]
    edges: list[OntologyGraphEdge]
    total_objects: int
    total_relationships: int
    total_mapped_properties: int


class TraversalStep(BaseModel):
    """One step in an ontology graph traversal."""

    relationship_id: uuid.UUID
    relationship_name: str
    cardinality: str
    target_object_id: uuid.UUID
    target_object_name: str
    join_expression: dict[str, Any] | None = None


class OntologyTraversalResponse(BaseModel):
    """Semantically traversable connected paths from a starting Business Object."""

    start_object_id: uuid.UUID
    start_object_name: str
    outgoing_paths: list[TraversalStep] = Field(default_factory=list)
    incoming_paths: list[TraversalStep] = Field(default_factory=list)
