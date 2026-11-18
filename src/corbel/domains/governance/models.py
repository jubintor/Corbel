"""SQLAlchemy ORM models for Phase 9: Governed Investigation, Approvals & RAG."""

import enum
import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from corbel.core.database import Base


class EvidenceClassification(str, enum.Enum):
    """Epistemic classification of evidence items distinguishing transactional facts, document statements, and hypotheses."""

    TRANSACTION_FACT = "TRANSACTION_FACT"
    DOCUMENT_EXTRACT = "DOCUMENT_EXTRACT"
    AI_HYPOTHESIS = "AI_HYPOTHESIS"


class InvestigationStatus(str, enum.Enum):
    """Lifecycle state of an analytical investigation."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class EvidenceSourceType(str, enum.Enum):
    """Source classification for retrieved investigative evidence."""

    BUSINESS_RECORD = "BUSINESS_RECORD"
    PROCESS_EVENT = "PROCESS_EVENT"
    DOCUMENT_CHUNK = "DOCUMENT_CHUNK"
    ONTOLOGY_RELATION = "ONTOLOGY_RELATION"


class DocumentType(str, enum.Enum):
    """Business document category for RAG indexing."""

    CONTRACT = "CONTRACT"
    PURCHASE_ORDER_TERMS = "PURCHASE_ORDER_TERMS"
    INVOICE_SUPPORTING = "INVOICE_SUPPORTING"
    DELIVERY_NOTE = "DELIVERY_NOTE"
    COMMUNICATION = "COMMUNICATION"
    DISPUTE_POLICY = "DISPUTE_POLICY"


class RiskLevel(str, enum.Enum):
    """Risk rating for a proposed remedial action."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ActionType(str, enum.Enum):
    """Supported target action types for P2P and operational governance."""

    HOLD_INVOICE = "HOLD_INVOICE"
    REQUEST_CREDIT_MEMO = "REQUEST_CREDIT_MEMO"
    FLAG_SUPPLIER_REVIEW = "FLAG_SUPPLIER_REVIEW"


class ActionStatus(str, enum.Enum):
    """Governed lifecycle status for a proposed action."""

    DRAFT = "DRAFT"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    EXECUTING = "EXECUTING"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"


class ApprovalStatus(str, enum.Enum):
    """Human decision state for an action approval gate."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


class ExecutionStatus(str, enum.Enum):
    """Dispatch outcome for a target-system adapter execution."""

    QUEUED = "QUEUED"
    DISPATCHING = "DISPATCHING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


class ActorType(str, enum.Enum):
    """Actor identity category for append-only audit events."""

    USER = "USER"
    SYSTEM_WORKER = "SYSTEM_WORKER"
    API_KEY = "API_KEY"


# ==============================================================================
# 1. Investigation & Evidence
# ==============================================================================


class Investigation(Base):
    """Analytical session examining the root causes and business impact of a Finding.

    Scoped strictly to a Project workspace (Direct Project Scope).
    Enforces same-project referential integrity via composite FK to findings.
    """

    __tablename__ = "investigations"
    __table_args__ = (
        UniqueConstraint("project_id", "id", name="uq_investigations_project_id_id"),
        ForeignKeyConstraint(
            ["project_id", "finding_id"],
            ["findings.project_id", "findings.id"],
            ondelete="CASCADE",
            name="fk_investigations_project_finding",
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
    finding_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(32), default=InvestigationStatus.PENDING.value, nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_facts_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    document_extracts_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    causal_hypothesis: Mapped[str | None] = mapped_column(Text, nullable=True)
    missing_evidence_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    financial_impact_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    evidence_items: Mapped[list["InvestigationEvidence"]] = relationship(
        "InvestigationEvidence", back_populates="investigation", cascade="all, delete-orphan"
    )
    recommendations: Mapped[list["Recommendation"]] = relationship(
        "Recommendation", back_populates="investigation", cascade="all, delete-orphan"
    )


class InvestigationEvidence(Base):
    """Captured supporting evidence item with strict provenance.

    Scoped strictly to a Project workspace (Direct Project Scope).
    Enforces same-project referential integrity via composite FK to investigations.
    """

    __tablename__ = "investigation_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "investigation_id"],
            ["investigations.project_id", "investigations.id"],
            ondelete="CASCADE",
            name="fk_evidence_project_investigation",
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
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    evidence_type: Mapped[str] = mapped_column(
        String(64), default=EvidenceSourceType.BUSINESS_RECORD.value, nullable=False
    )
    evidence_classification: Mapped[str] = mapped_column(
        String(32), default=EvidenceClassification.TRANSACTION_FACT.value, nullable=False, index=True
    )
    source_identifier: Mapped[str] = mapped_column(String(255), nullable=False)
    document_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dataset_version_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    section_or_chunk: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_snippet: Mapped[str] = mapped_column(Text, nullable=False)
    structured_data_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    is_verified_fact: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationship
    investigation: Mapped["Investigation"] = relationship("Investigation", back_populates="evidence_items")


# ==============================================================================
# 2. Unstructured Documents & Chunks for RAG
# ==============================================================================


class Document(Base):
    """Unstructured business document uploaded for RAG indexing.

    Scoped strictly to a Project workspace (Direct Project Scope).
    """

    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("project_id", "id", name="uq_documents_project_id_id"),
        UniqueConstraint("project_id", "file_name", name="uq_documents_project_file_name"),
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
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    document_type: Mapped[str] = mapped_column(
        String(64), default=DocumentType.CONTRACT.value, nullable=False
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_format: Mapped[str] = mapped_column(String(32), default="TXT", nullable=False)
    version_tag: Mapped[str] = mapped_column(String(32), default="v1.0", nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        "DocumentChunk", back_populates="document", cascade="all, delete-orphan"
    )


class DocumentChunk(Base):
    """Chunk of an unstructured document for lexical and semantic retrieval.

    Scoped strictly to a Project workspace (Direct Project Scope).
    Enforces same-project referential integrity via composite FK to documents.
    """

    __tablename__ = "document_chunks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "document_id"],
            ["documents.project_id", "documents.id"],
            ondelete="CASCADE",
            name="fk_chunks_project_document",
        ),
        Index(
            "ix_document_chunks_embedding_vector",
            "embedding_vector",
            postgresql_using="hnsw",
            postgresql_ops={"embedding_vector": "vector_cosine_ops"},
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
    document_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    section_heading: Mapped[str | None] = mapped_column(String(255), nullable=True)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    embedding_json: Mapped[list[float] | None] = mapped_column(JSONB, nullable=True)
    embedding_vector: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    embedding_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    embedding_dim: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationship
    document: Mapped["Document"] = relationship("Document", back_populates="chunks")


# ==============================================================================
# 3. Recommendations & Governed Actions
# ==============================================================================


class Recommendation(Base):
    """Structured proposal produced by an Investigation to resolve or mitigate a Finding.

    Inherited Project Scope via investigation_id.
    """

    __tablename__ = "recommendations"
    __table_args__ = (
        UniqueConstraint("investigation_id", "id", name="uq_recommendations_inv_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("investigations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    risk_level: Mapped[str] = mapped_column(
        String(32), default=RiskLevel.LOW.value, nullable=False
    )
    recommended_action_type: Mapped[str] = mapped_column(
        String(64), default=ActionType.HOLD_INVOICE.value, nullable=False
    )
    suggested_payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    investigation: Mapped["Investigation"] = relationship("Investigation", back_populates="recommendations")
    actions: Mapped[list["Action"]] = relationship(
        "Action", back_populates="recommendation", cascade="all, delete-orphan"
    )


class Action(Base):
    """Specific parameterized operation designed to alter system state.

    Scoped directly to Project workspace (Direct Project Scope).
    """

    __tablename__ = "actions"
    __table_args__ = (
        UniqueConstraint("project_id", "id", name="uq_actions_project_id_id"),
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
    recommendation_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("recommendations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_system: Mapped[str] = mapped_column(
        String(64), default="SimulatedTargetAdapter", nullable=False
    )
    proposed_payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    is_consequential: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default=ActionStatus.AWAITING_APPROVAL.value, nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    recommendation: Mapped["Recommendation"] = relationship("Recommendation", back_populates="actions")
    approvals: Mapped[list["Approval"]] = relationship(
        "Approval", back_populates="action", cascade="all, delete-orphan"
    )
    executions: Mapped[list["ActionExecution"]] = relationship(
        "ActionExecution", back_populates="action", cascade="all, delete-orphan"
    )


class Approval(Base):
    """Formal human authorization gate binding an authorized user decision to the exact action payload.

    Inherited Project Scope via action_id.
    Maintains unique candidate key on (action_id, id) for database-enforced referential integrity.
    """

    __tablename__ = "approvals"
    __table_args__ = (
        UniqueConstraint("action_id", "id", name="uq_approvals_action_id_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    action_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("actions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    assigned_role: Mapped[str] = mapped_column(String(64), default="MANAGER", nullable=False)
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(32), default=ApprovalStatus.PENDING.value, nullable=False, index=True
    )
    approved_payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approved_payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    decision_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    action: Mapped["Action"] = relationship("Action", back_populates="approvals")
    executions: Mapped[list["ActionExecution"]] = relationship(
        "ActionExecution", back_populates="approval", overlaps="executions"
    )


class ActionExecution(Base):
    """Attempt to execute an approved Action against a target adapter.

    Enforces same-action referential integrity via composite FK to approvals(action_id, id).
    """

    __tablename__ = "action_executions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["action_id", "approval_id"],
            ["approvals.action_id", "approvals.id"],
            ondelete="CASCADE",
            name="fk_action_executions_action_approval",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    action_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("actions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    approval_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True
    )
    target_adapter_type: Mapped[str] = mapped_column(
        String(64), default="SimulatedTargetAdapter", nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(32), default=ExecutionStatus.QUEUED.value, nullable=False, index=True
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    dispatched_payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    dispatched_payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    adapter_response_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    dispatched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    action: Mapped["Action"] = relationship("Action", back_populates="executions", overlaps="executions")
    approval: Mapped["Approval"] = relationship(
        "Approval", back_populates="executions", overlaps="action,executions"
    )


# ==============================================================================
# 4. Authoritative Audit Event Store (PostgreSQL Append-Only)
# ==============================================================================


class AuditEvent(Base):
    """Immutable, append-only record capturing authoritative historical proof of system operations.

    Adheres strictly to ADR-020 and DOMAIN_MODEL.md Section 4.7.
    """

    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
        index=True,
    )
    actor_type: Mapped[str] = mapped_column(
        String(32), default=ActorType.USER.value, nullable=False
    )
    actor_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    action_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    affected_entity_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    affected_entity_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    execution_context_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    canonical_payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    outcome_status: Mapped[str] = mapped_column(String(32), default="SUCCESS", nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
