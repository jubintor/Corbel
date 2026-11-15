"""SQLAlchemy ORM models for Data Intelligence & Profiling (Phase 3)."""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from corbel.core.database import Base


class SourceType(str, enum.Enum):
    """Supported data source connector types."""

    FILE_INGEST = "FILE_INGEST"
    POSTGRES = "POSTGRES"
    MYSQL = "MYSQL"
    SNOWFLAKE = "SNOWFLAKE"


class DataSourceStatus(str, enum.Enum):
    """Operational status of a configured Data Source."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    ERROR = "ERROR"


class DatasetStatus(str, enum.Enum):
    """Lifecycle status of a logical dataset."""

    PENDING = "PENDING"
    READY = "READY"
    PROFILED = "PROFILED"
    ERROR = "ERROR"


class DatasetVersionStatus(str, enum.Enum):
    """Ingestion and profiling status of a specific dataset version."""

    UPLOADED = "UPLOADED"
    PROFILING = "PROFILING"
    READY = "READY"
    FAILED = "FAILED"


class FileFormat(str, enum.Enum):
    """Supported file formats for dataset upload and parsing."""

    CSV = "CSV"
    JSON = "JSON"
    XLSX = "XLSX"


class DataSource(Base):
    """Configured connection to an external database or file ingestion boundary.

    Scoped strictly to a Project workspace (Direct Project Scope).
    """

    __tablename__ = "data_sources"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(
        String(32), default=SourceType.FILE_INGEST.value, nullable=False
    )
    connection_config_encrypted: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), default=DataSourceStatus.ACTIVE.value, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    datasets: Mapped[list["Dataset"]] = relationship(
        "Dataset",
        back_populates="data_source",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("project_id", "id", name="uq_data_sources_project_id"),
        UniqueConstraint("project_id", "name", name="uq_data_sources_project_name"),
    )


class Dataset(Base):
    """Logical tabular data asset provided by a Data Source.

    Scoped strictly to a Project workspace (Direct Project Scope).
    Must belong to the exact same Project as its Data Source (composite foreign key).
    """

    __tablename__ = "datasets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    data_source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), default=DatasetStatus.PENDING.value, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    data_source: Mapped["DataSource"] = relationship("DataSource", back_populates="datasets")
    versions: Mapped[list["DatasetVersion"]] = relationship(
        "DatasetVersion",
        back_populates="dataset",
        cascade="all, delete-orphan",
        order_by="DatasetVersion.version_number.desc()",
    )

    __table_args__ = (
        UniqueConstraint("project_id", "id", name="uq_datasets_project_id"),
        UniqueConstraint("project_id", "name", name="uq_datasets_project_name"),
        # Enforce same-project integrity between dataset and its data source
        ForeignKeyConstraint(
            ["project_id", "data_source_id"],
            ["data_sources.project_id", "data_sources.id"],
            ondelete="CASCADE",
            name="fk_datasets_project_data_source",
        ),
    )


class DatasetVersion(Base):
    """Immutable snapshot representing a specific extraction, schema state,

    and statistical profiling summary of a Dataset.
    Must belong to the exact same Project as its parent Dataset (composite foreign key).
    """

    __tablename__ = "dataset_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        index=True,
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    file_format: Mapped[str] = mapped_column(String(32), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    record_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    column_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    schema_metadata_json: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    profiling_summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), default=DatasetVersionStatus.UPLOADED.value, nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    dataset: Mapped["Dataset"] = relationship("Dataset", back_populates="versions")

    __table_args__ = (
        UniqueConstraint("project_id", "id", name="uq_dataset_versions_project_id"),
        UniqueConstraint("dataset_id", "version_number", name="uq_dataset_versions_dataset_version"),
        # Enforce same-project integrity between dataset version and its parent dataset
        ForeignKeyConstraint(
            ["project_id", "dataset_id"],
            ["datasets.project_id", "datasets.id"],
            ondelete="CASCADE",
            name="fk_dataset_versions_project_dataset",
        ),
    )
