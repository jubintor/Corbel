"""Pydantic request and response schemas for Process Intelligence & Event Mining (Phase 6)."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProcessCreate(BaseModel):
    """Request payload to define a new operational process."""

    name: str = Field(min_length=1, max_length=255, description="Process name, e.g. Procure-to-Pay")
    description: str | None = Field(default=None, max_length=1024)
    target_duration_seconds: float | None = Field(
        default=None, ge=0.0, description="Target SLA cycle time in seconds"
    )
    is_active: bool = Field(default=True)


class ProcessUpdate(BaseModel):
    """Request payload to update an existing process."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1024)
    target_duration_seconds: float | None = Field(default=None, ge=0.0)
    is_active: bool | None = Field(default=None)


class ProcessResponse(BaseModel):
    """Public representation of an operational process."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    description: str | None
    target_duration_seconds: float | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    case_count: int = 0
    event_count: int = 0


class ProcessEventIngestItem(BaseModel):
    """Single activity event within a process lifecycle."""

    case_identifier: str = Field(min_length=1, max_length=255)
    activity_name: str = Field(min_length=1, max_length=255)
    timestamp: datetime
    event_type: str = Field(default="COMPLETE", max_length=32)
    resource: str | None = Field(default=None, max_length=255)
    source_system: str | None = Field(default=None, max_length=100)
    source_record_id: str | None = Field(default=None, max_length=255)
    attributes: dict[str, Any] | None = None


class ProcessEventBatchIngestRequest(BaseModel):
    """Batch ingestion request containing multiple event items."""

    events: list[ProcessEventIngestItem] = Field(min_length=1)


class ProcessReconstructRequest(BaseModel):
    """Request payload to reconstruct process cases and variants from datasets."""

    mode: str = Field(
        default="P2P_ONTOLOGY",
        description="Reconstruction mode: 'P2P_ONTOLOGY' or 'DATASET_MAPPING'",
    )
    # Fields required for DATASET_MAPPING mode:
    dataset_id: uuid.UUID | None = None
    case_id_column: str | None = None
    activity_column: str | None = None
    timestamp_column: str | None = None
    resource_column: str | None = None
    attributes_columns: list[str] | None = None


class ProcessReconstructResponse(BaseModel):
    """Summary of reconstructed process cases and events."""

    process_id: uuid.UUID
    cases_reconstructed: int
    events_reconstructed: int
    variants_count: int
    message: str


class ProcessEventResponse(BaseModel):
    """Public representation of a single process event."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    activity_name: str
    timestamp: datetime
    event_type: str
    resource: str | None
    source_system: str | None
    source_record_id: str | None
    attributes: dict[str, Any] | None = None


class ProcessCaseSummary(BaseModel):
    """Summary of a reconstructed process case instance."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    process_id: uuid.UUID
    case_identifier: str
    variant_key: str
    status: str
    started_at: datetime
    ended_at: datetime
    total_duration_seconds: float
    event_count: int


class ProcessCaseDetailResponse(BaseModel):
    """Detailed case representation with full event sequence."""

    case: ProcessCaseSummary
    events: list[ProcessEventResponse]


class ProcessCasesListResponse(BaseModel):
    """Paginated list of process cases."""

    items: list[ProcessCaseSummary]
    total: int
    page: int
    limit: int


class ProcessVariantItem(BaseModel):
    """Statistical summary of a distinct process path / variant."""

    variant_key: str
    activities: list[str]
    case_count: int
    frequency_percentage: float
    avg_duration_seconds: float
    median_duration_seconds: float
    min_duration_seconds: float
    max_duration_seconds: float
    is_happy_path: bool


class ProcessVariantsResponse(BaseModel):
    """Discovered process variants ranked by execution frequency."""

    process_id: uuid.UUID
    variants: list[ProcessVariantItem]
    total_variants: int


class DFGNode(BaseModel):
    """Activity node in a Directly-Follows Graph."""

    name: str
    frequency: int
    case_frequency: int
    avg_duration_from_start_seconds: float
    is_start_activity: bool
    is_end_activity: bool


class DFGEdge(BaseModel):
    """Directed transition between two activities in a Directly-Follows Graph."""

    source: str
    target: str
    transition_count: int
    case_count: int
    avg_duration_seconds: float
    median_duration_seconds: float
    min_duration_seconds: float
    max_duration_seconds: float
    is_rework: bool
    is_bottleneck: bool


class DFGResponse(BaseModel):
    """Directly-Follows Graph representation for process visualizer."""

    process_id: uuid.UUID
    nodes: list[DFGNode]
    edges: list[DFGEdge]
    bottleneck_edge: DFGEdge | None = None


class ProcessOverviewResponse(BaseModel):
    """Executive process summary with performance KPIs and bottleneck detection."""

    process_id: uuid.UUID
    name: str
    target_duration_seconds: float | None
    total_cases: int
    total_events: int
    distinct_activities_count: int
    distinct_variants_count: int
    avg_cycle_time_seconds: float
    median_cycle_time_seconds: float
    min_cycle_time_seconds: float
    max_cycle_time_seconds: float
    sla_breach_count: int
    sla_compliance_rate: float
    rework_case_count: int
    rework_rate: float
    primary_bottleneck: str | None
