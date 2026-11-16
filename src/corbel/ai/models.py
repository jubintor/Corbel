"""SQLAlchemy database models for Phase 8: Complete AI Infrastructure & Bounded State Machines.

Entities adhere strictly to DOMAIN_MODEL.md Section 4.7 (Execution, AI & Audit Subdomain).
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from corbel.core.database import Base

# -----------------------------------------------------------------------------
# Enums
# -----------------------------------------------------------------------------


class TaskStatus(str, Enum):
    """Lifecycle status of a durable background task execution."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TaskType(str, Enum):
    """Operational categories of durable background tasks."""

    DATASET_IMPORT = "DATASET_IMPORT"
    SCHEMA_PROFILING = "SCHEMA_PROFILING"
    WORKFLOW_RUN = "WORKFLOW_RUN"
    MONITOR_SWEEP = "MONITOR_SWEEP"
    EVALUATION_RUN = "EVALUATION_RUN"


class WorkflowStatus(str, Enum):
    """Execution status of an analytical state machine workflow."""

    INITIALIZED = "INITIALIZED"
    STEPPING = "STEPPING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class WorkflowType(str, Enum):
    """Predefined bounded state machine workflow types."""

    DATA_DISCOVERY = "DATA_DISCOVERY"
    PROCESS_MINING = "PROCESS_MINING"
    INVESTIGATION = "INVESTIGATION"
    RULE_GENERATION = "RULE_GENERATION"


class PromptLifecycleState(str, Enum):
    """Formal lifecycle progression for immutable prompt versions."""

    DRAFT = "DRAFT"
    TEST = "TEST"
    EVALUATE = "EVALUATE"
    APPROVE = "APPROVE"
    DEPLOY = "DEPLOY"
    MONITOR = "MONITOR"
    RETIRE = "RETIRE"


class ModelCallOutcome(str, Enum):
    """Outcome status of an atomic model provider call."""

    SUCCESS = "SUCCESS"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    RATE_LIMITED = "RATE_LIMITED"
    TIMEOUT = "TIMEOUT"
    VALIDATION_FAILED = "VALIDATION_FAILED"


class WorkflowOutcome(str, Enum):
    """Outcome tier for analytical workflow execution."""

    SUCCESS = "SUCCESS"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class EvaluationRunStatus(str, Enum):
    """Status of an AI regression evaluation benchmark run."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


# -----------------------------------------------------------------------------
# Database Models
# -----------------------------------------------------------------------------


class TaskExecution(Base):
    """Durable background job entity managing operational lifecycle, claiming, lease, and recovery in PostgreSQL."""

    __tablename__ = "task_executions"
    __table_args__ = (
        UniqueConstraint("project_id", "id", name="uq_task_executions_project_id_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    task_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default=TaskStatus.PENDING.value, nullable=False, index=True
    )
    worker_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    lease_generation: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    checkpoint_data_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    cancellation_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_diagnostics_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    workflow_execution: Mapped["WorkflowExecution | None"] = relationship(
        "WorkflowExecution",
        back_populates="task_execution",
        uselist=False,
        cascade="all, delete-orphan",
    )
    cost_records: Mapped[list["CostRecord"]] = relationship(
        "CostRecord",
        back_populates="task_execution",
    )


class WorkflowExecution(Base):
    """Workflow execution record governing specific analytical state machine transitions and bounds."""

    __tablename__ = "workflow_executions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "task_execution_id"],
            ["task_executions.project_id", "task_executions.id"],
            ondelete="SET NULL",
            name="fk_workflow_executions_project_task",
        ),
        UniqueConstraint("project_id", "id", name="uq_workflow_executions_project_id_id"),
        UniqueConstraint("task_execution_id", "id", name="uq_workflow_executions_task_id_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    task_execution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )
    workflow_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    workflow_version: Mapped[str] = mapped_column(String(32), default="1.0.0", nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default=WorkflowStatus.INITIALIZED.value, nullable=False, index=True
    )
    current_state: Mapped[str] = mapped_column(String(64), nullable=False)
    step_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_steps: Mapped[int] = mapped_column(Integer, default=8, nullable=False)
    token_budget: Mapped[int] = mapped_column(Integer, default=50000, nullable=False)
    cost_budget_usd: Mapped[float] = mapped_column(Float, default=5.0, nullable=False)
    input_parameters_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    state_data_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    result_data_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    parent_execution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_executions.id", ondelete="SET NULL"),
        nullable=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    task_execution: Mapped["TaskExecution | None"] = relationship(
        "TaskExecution", back_populates="workflow_execution"
    )
    model_invocations: Mapped[list["ModelInvocation"]] = relationship(
        "ModelInvocation",
        back_populates="workflow_execution",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class PromptDefinition(Base):
    """Named logical prompt asset representing a specific enterprise prompt capability."""

    __tablename__ = "prompt_definitions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    workflow_association: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    versions: Mapped[list["PromptVersion"]] = relationship(
        "PromptVersion",
        back_populates="prompt_definition",
        cascade="all, delete-orphan",
        order_by="PromptVersion.created_at.desc()",
        lazy="selectin",
    )


class PromptVersion(Base):
    """Immutable, version-controlled iteration of a Prompt Definition."""

    __tablename__ = "prompt_versions"
    __table_args__ = (
        UniqueConstraint("prompt_definition_id", "version_tag", name="uq_prompt_versions_def_tag"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    prompt_definition_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("prompt_definitions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_tag: Mapped[str] = mapped_column(String(32), nullable=False)
    lifecycle_state: Mapped[str] = mapped_column(
        String(32), default=PromptLifecycleState.DRAFT.value, nullable=False, index=True
    )
    model_compatibility: Mapped[str] = mapped_column(
        String(64), default="claude-3-5-sonnet", nullable=False
    )
    token_budget_input: Mapped[int] = mapped_column(Integer, default=4096, nullable=False)
    token_budget_output: Mapped[int] = mapped_column(Integer, default=1024, nullable=False)
    template_text: Mapped[str] = mapped_column(Text, nullable=False)
    input_schema_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    output_schema_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    prompt_definition: Mapped["PromptDefinition"] = relationship(
        "PromptDefinition", back_populates="versions"
    )
    invocations: Mapped[list["ModelInvocation"]] = relationship(
        "ModelInvocation", back_populates="prompt_version"
    )


class ModelInvocation(Base):
    """Atomic call record to an underlying hosted LLM provider via the Model Gateway."""

    __tablename__ = "model_invocations"
    __table_args__ = (
        UniqueConstraint("workflow_execution_id", "id", name="uq_model_invocations_wf_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workflow_execution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_executions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    prompt_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("prompt_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    provider_name: Mapped[str] = mapped_column(String(64), nullable=False)
    model_name: Mapped[str] = mapped_column(String(64), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cached_input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    model_call_outcome: Mapped[str] = mapped_column(
        String(32), default=ModelCallOutcome.SUCCESS.value, nullable=False
    )
    provider_request_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    span_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    # Relationships
    workflow_execution: Mapped["WorkflowExecution | None"] = relationship(
        "WorkflowExecution", back_populates="model_invocations"
    )
    prompt_version: Mapped["PromptVersion | None"] = relationship(
        "PromptVersion", back_populates="invocations"
    )
    cost_record: Mapped["CostRecord | None"] = relationship(
        "CostRecord",
        back_populates="model_invocation",
        uselist=False,
        cascade="all, delete-orphan",
    )


class CostRecord(Base):
    """Granular financial accounting entry recording expenditure for AI model invocations."""

    __tablename__ = "cost_records"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "project_id"],
            ["projects.organization_id", "projects.id"],
            ondelete="CASCADE",
            name="fk_cost_records_org_project",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    model_invocation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("model_invocations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    task_execution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("task_executions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    use_case: Mapped[str] = mapped_column(String(64), default="procure-to-pay", nullable=False)
    workflow_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    agent_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    model_call_outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    workflow_outcome: Mapped[str] = mapped_column(
        String(32), default=WorkflowOutcome.SUCCESS.value, nullable=False
    )
    task_outcome: Mapped[str] = mapped_column(
        String(32), default=TaskStatus.COMPLETED.value, nullable=False
    )
    pricing_tier_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    is_estimated: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    # Relationships
    model_invocation: Mapped["ModelInvocation"] = relationship(
        "ModelInvocation", back_populates="cost_record"
    )
    task_execution: Mapped["TaskExecution | None"] = relationship(
        "TaskExecution", back_populates="cost_records"
    )


class EvaluationDataset(Base):
    """Versioned golden test dataset used for AI regression testing and quality benchmarking."""

    __tablename__ = "evaluation_datasets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(32), default="1.0.0", nullable=False)
    domain: Mapped[str] = mapped_column(String(64), default="procure-to-pay", nullable=False, index=True)
    test_cases_json: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    runs: Mapped[list["EvaluationRun"]] = relationship(
        "EvaluationRun",
        back_populates="evaluation_dataset",
        cascade="all, delete-orphan",
        order_by="EvaluationRun.created_at.desc()",
    )


class EvaluationRun(Base):
    """Execution run record of an evaluation benchmark suite against prompt/model/workflow."""

    __tablename__ = "evaluation_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    evaluation_dataset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evaluation_datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_prompt_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("prompt_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    target_model_name: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default=EvaluationRunStatus.PENDING.value, nullable=False, index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    summary_metrics_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    evaluation_dataset: Mapped["EvaluationDataset"] = relationship(
        "EvaluationDataset", back_populates="runs"
    )
    results: Mapped[list["EvaluationResult"]] = relationship(
        "EvaluationResult",
        back_populates="evaluation_run",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class EvaluationResult(Base):
    """Individual test case score result within an evaluation benchmark run."""

    __tablename__ = "evaluation_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    evaluation_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    test_case_id: Mapped[str] = mapped_column(String(128), nullable=False)
    metric_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    diagnostics_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    evaluation_run: Mapped["EvaluationRun"] = relationship(
        "EvaluationRun", back_populates="results"
    )
