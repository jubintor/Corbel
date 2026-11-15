"""SQLAlchemy ORM models for Process Intelligence & Event Mining (Phase 6)."""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from corbel.core.database import Base


class ProcessCaseStatus(str, enum.Enum):
    """Lifecycle status of a process case instance."""

    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    ABANDONED = "ABANDONED"


class ProcessEventType(str, enum.Enum):
    """Event lifecycle phase."""

    START = "START"
    COMPLETE = "COMPLETE"


class Process(Base):
    """End-to-end operational workflow definition (e.g., Procure-to-Pay)."""

    __tablename__ = "processes"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_processes_project_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    target_duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    cases: Mapped[list["ProcessCase"]] = relationship(
        "ProcessCase",
        back_populates="process",
        cascade="all, delete-orphan",
        order_by="ProcessCase.started_at.desc()",
    )


class ProcessCase(Base):
    """Concrete execution instance of an operational workflow (e.g., PO #5001 lifecycle)."""

    __tablename__ = "process_cases"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "process_id", "case_identifier",
            name="uq_process_cases_project_process_case_id"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    process_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("processes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    case_identifier: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    variant_key: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(32), default=ProcessCaseStatus.COMPLETED.value, nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    total_duration_seconds: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    event_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    process: Mapped["Process"] = relationship("Process", back_populates="cases")
    events: Mapped[list["ProcessEvent"]] = relationship(
        "ProcessEvent",
        back_populates="process_case",
        cascade="all, delete-orphan",
        order_by="ProcessEvent.timestamp.asc()",
    )


class ProcessEvent(Base):
    """Atomic, timestamped activity occurrence within a process case."""

    __tablename__ = "process_events"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    process_case_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("process_cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dataset_version_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("dataset_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    activity_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(
        String(32), default=ProcessEventType.COMPLETE.value, nullable=False
    )
    resource: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_system: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_record_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attributes_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    process_case: Mapped["ProcessCase"] = relationship("ProcessCase", back_populates="events")


class ProcessEventDatasetVersion(Base):
    """Provenance association linking a Process Event to an immutable Dataset Version snapshot."""

    __tablename__ = "process_event_dataset_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    process_event_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("process_events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dataset_version_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("dataset_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provenance_role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    transformation_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
