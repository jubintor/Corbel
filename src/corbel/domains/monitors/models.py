"""SQLAlchemy ORM models for Phase 7: Adaptive Monitors & Exception Detection."""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from corbel.core.database import Base


class MonitorStatus(str, enum.Enum):
    """Lifecycle status of an operational monitor."""

    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"


class MonitorTargetType(str, enum.Enum):
    """Scope target of an operational monitor."""

    ENTITY = "ENTITY"
    PROCESS = "PROCESS"


class RuleSeverity(str, enum.Enum):
    """Business impact severity classification for rules and findings."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RuleOperator(str, enum.Enum):
    """Deterministic comparison operators for business rule conditions."""

    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    EQ = "eq"
    NEQ = "neq"


class FindingStatus(str, enum.Enum):
    """Governed lifecycle status for detected operational exceptions."""

    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    INVESTIGATING = "INVESTIGATING"
    RECOMMENDED = "RECOMMENDED"
    RESOLVED = "RESOLVED"
    DISMISSED = "DISMISSED"


class EvaluationStatus(str, enum.Enum):
    """Execution outcome status for a monitor evaluation run."""

    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    ERROR = "ERROR"


class Monitor(Base):
    """Operational observer evaluating business rules against domain data.

    Defined within exactly one Project workspace (Direct Project Scope).
    """

    __tablename__ = "monitors"
    __table_args__ = (
        UniqueConstraint("project_id", "id", name="uq_monitors_project_id_id"),
        UniqueConstraint("project_id", "name", name="uq_monitors_project_name"),
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
    target_type: Mapped[str] = mapped_column(
        String(32), default=MonitorTargetType.ENTITY.value, nullable=False
    )
    target_id: Mapped[str] = mapped_column(String(255), nullable=False)
    schedule_cron: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), default=MonitorStatus.ACTIVE.value, nullable=False, index=True
    )
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    rules: Mapped[list["BusinessRule"]] = relationship(
        "BusinessRule",
        back_populates="monitor",
        cascade="all, delete-orphan",
        order_by="BusinessRule.created_at.asc()",
        lazy="selectin",
    )
    findings: Mapped[list["Finding"]] = relationship(
        "Finding",
        back_populates="monitor",
        cascade="all, delete-orphan",
        order_by="Finding.detected_at.desc()",
        lazy="selectin",
    )
    evaluations: Mapped[list["MonitorEvaluation"]] = relationship(
        "MonitorEvaluation",
        back_populates="monitor",
        cascade="all, delete-orphan",
        order_by="MonitorEvaluation.evaluated_at.desc()",
        lazy="selectin",
    )


class BusinessRule(Base):
    """Deterministic constraint or threshold evaluated by an operational monitor."""

    __tablename__ = "business_rules"
    __table_args__ = (
        UniqueConstraint("monitor_id", "rule_code", name="uq_business_rules_monitor_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    monitor_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("monitors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rule_code: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    severity: Mapped[str] = mapped_column(
        String(32), default=RuleSeverity.MEDIUM.value, nullable=False
    )
    rule_type: Mapped[str] = mapped_column(String(64), nullable=False)
    field_name: Mapped[str] = mapped_column(String(128), nullable=False)
    operator: Mapped[str] = mapped_column(
        String(32), default=RuleOperator.GT.value, nullable=False
    )
    threshold_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold_string: Mapped[str | None] = mapped_column(String(255), nullable=True)
    secondary_field: Mapped[str | None] = mapped_column(String(128), nullable=True)
    parameters_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationship
    monitor: Mapped["Monitor"] = relationship("Monitor", back_populates="rules")


class Finding(Base):
    """Detected operational exception or policy deviation emitted by a monitor.

    Enforces same-project referential integrity via composite foreign key to monitors.
    """

    __tablename__ = "findings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "monitor_id"],
            ["monitors.project_id", "monitors.id"],
            ondelete="CASCADE",
            name="fk_findings_project_monitor",
        ),
        UniqueConstraint("project_id", "deduplication_hash", name="uq_findings_project_dedup"),
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
    monitor_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    rule_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("business_rules.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    process_case_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("process_cases.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    finding_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(
        String(32), default=RuleSeverity.MEDIUM.value, nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(32), default=FindingStatus.OPEN.value, nullable=False, index=True
    )
    summary: Mapped[str] = mapped_column(String(1024), nullable=False)
    deduplication_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    observed_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    threshold_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    verified_context_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    resolution_notes: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # Relationships
    monitor: Mapped["Monitor"] = relationship("Monitor", back_populates="findings")
    rule: Mapped["BusinessRule | None"] = relationship("BusinessRule", lazy="selectin")


class MonitorEvaluation(Base):
    """Audit ledger record documenting an execution run of a monitor."""

    __tablename__ = "monitor_evaluations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "monitor_id"],
            ["monitors.project_id", "monitors.id"],
            ondelete="CASCADE",
            name="fk_monitor_evaluations_project_monitor",
        ),
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
    monitor_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(32), default=EvaluationStatus.SUCCESS.value, nullable=False
    )
    records_evaluated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    findings_detected: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    execution_duration_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    # Relationship
    monitor: Mapped["Monitor"] = relationship("Monitor", back_populates="evaluations")
