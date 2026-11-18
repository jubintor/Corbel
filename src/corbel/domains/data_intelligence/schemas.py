"""Pydantic request and response schemas for Data Intelligence & Profiling."""

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from corbel.domains.data_intelligence.models import (
    SourceType,
)


class DataSourceCreateRequest(BaseModel):
    """Schema for registering a new external data source connection."""

    name: str = Field(..., min_length=2, max_length=255, description="Human-readable name")
    source_type: SourceType = Field(default=SourceType.FILE_INGEST, description="Connector dialect")
    connection_config_encrypted: str | None = Field(default=None, description="Encrypted connection parameters")

    model_config = ConfigDict(from_attributes=True)


class DataSourceResponse(BaseModel):
    """Schema representing a registered Data Source."""

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    source_type: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ColumnSchema(BaseModel):
    """Discovered column metadata."""

    name: str = Field(..., description="Column header name")
    data_type: str = Field(..., description="Inferred primitive data type")
    nullable: bool = Field(default=True, description="Whether column accepts nulls")
    sample_values: list[Any] = Field(default_factory=list, description="Sample non-null values")


class NumericStats(BaseModel):
    """Statistical summary for numeric columns."""

    min: float | None = None
    max: float | None = None
    mean: float | None = None
    stddev: float | None = None
    median: float | None = None
    sum: float | None = None
    zeros_count: int = 0


class DateTimeStats(BaseModel):
    """Statistical summary for date and datetime columns."""

    earliest: str | None = None
    latest: str | None = None
    range_days: float | None = None
    invalid_count: int = 0


class StringStats(BaseModel):
    """Statistical summary for textual string columns."""

    min_length: int | None = None
    max_length: int | None = None
    avg_length: float | None = None


class ColumnProfile(BaseModel):
    """Comprehensive deterministic profile for a single column."""

    column_name: str
    detected_type: str
    total_count: int = 0
    null_count: int
    non_null_count: int
    null_percentage: float
    distinct_count: int
    unique_percentage: float
    sample_values: list[Any] = Field(default_factory=list)
    numeric_stats: NumericStats | None = None
    datetime_stats: DateTimeStats | None = None
    string_stats: StringStats | None = None
    quality_warnings: list[str] = Field(default_factory=list)


class ProfilingSummary(BaseModel):
    """Deterministic profile summary for an entire dataset version."""

    total_rows: int
    total_columns: int
    duplicate_rows_count: int
    duplicate_rows_pct: float
    columns: list[ColumnProfile]
    dataset_quality_warnings: list[str] = Field(default_factory=list)
    profiled_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DatasetVersionResponse(BaseModel):
    """Public metadata response for a Dataset Version snapshot (storage paths withheld)."""

    id: uuid.UUID
    dataset_id: uuid.UUID
    project_id: uuid.UUID
    version_number: int
    file_format: str
    file_size_bytes: int
    checksum_hash: str
    record_count: int | None
    column_count: int | None
    status: str
    error_message: str | None = None
    schema_metadata: list[ColumnSchema] | None = None
    profiling_summary: ProfilingSummary | None = None
    imported_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_orm_model(cls, v: Any) -> "DatasetVersionResponse":
        schema_meta = (
            [ColumnSchema.model_validate(col) for col in v.schema_metadata_json]
            if isinstance(v.schema_metadata_json, list)
            else None
        )
        prof_sum = (
            ProfilingSummary.model_validate(v.profiling_summary_json)
            if isinstance(v.profiling_summary_json, dict)
            else None
        )
        return cls(
            id=v.id,
            dataset_id=v.dataset_id,
            project_id=v.project_id,
            version_number=v.version_number,
            file_format=v.file_format,
            file_size_bytes=v.file_size_bytes,
            checksum_hash=v.checksum_hash,
            record_count=v.record_count,
            column_count=v.column_count,
            status=v.status,
            error_message=v.error_message,
            schema_metadata=schema_meta,
            profiling_summary=prof_sum,
            imported_at=v.imported_at,
        )


class DatasetResponse(BaseModel):
    """Public metadata response for a logical Dataset container."""

    id: uuid.UUID
    project_id: uuid.UUID
    data_source_id: uuid.UUID
    name: str
    description: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime
    latest_version: DatasetVersionResponse | None = None
    version_count: int = 1

    model_config = ConfigDict(from_attributes=True)


class DatasetUpdateRequest(BaseModel):
    """Schema for updating logical dataset metadata."""

    name: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=1024)

    model_config = ConfigDict(from_attributes=True)


class DatasetPreviewResponse(BaseModel):
    """First N rows preview of a dataset version."""

    dataset_id: uuid.UUID
    version_number: int
    columns: list[str]
    rows: list[dict[str, Any]]
    total_preview_rows: int
