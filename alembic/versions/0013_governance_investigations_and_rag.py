"""Phase 9: Governed Investigation, Approvals, Action Execution, RAG & Authoritative Audit.

Revision ID: 0013_governance_and_rag
Revises: 0012_task_lease_fencing
Create Date: 2026-11-16 12:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0013_governance_and_rag"
down_revision: str | None = "0012_task_lease_fencing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 0. Candidate key on findings for composite foreign keys
    op.create_unique_constraint(
        "uq_findings_project_id_id", "findings", ["project_id", "id"]
    )

    # 1. Investigations
    op.create_table(
        "investigations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("finding_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="PENDING"),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("verified_facts_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("causal_hypothesis", sa.Text(), nullable=True),
        sa.Column("missing_evidence_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("financial_impact_usd", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["project_id", "finding_id"],
            ["findings.project_id", "findings.id"],
            ondelete="CASCADE",
            name="fk_investigations_project_finding",
        ),
        sa.UniqueConstraint("project_id", "id", name="uq_investigations_project_id_id"),
    )
    op.create_index(op.f("ix_investigations_project_id"), "investigations", ["project_id"])
    op.create_index(op.f("ix_investigations_finding_id"), "investigations", ["finding_id"])
    op.create_index(op.f("ix_investigations_status"), "investigations", ["status"])
    op.create_index(op.f("ix_investigations_created_at"), "investigations", ["created_at"])

    # 2. Investigation Evidence
    op.create_table(
        "investigation_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("investigation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_type", sa.String(length=64), nullable=False),
        sa.Column("source_identifier", sa.String(length=255), nullable=False),
        sa.Column("document_name", sa.String(length=255), nullable=True),
        sa.Column("dataset_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("section_or_chunk", sa.String(length=255), nullable=True),
        sa.Column("content_snippet", sa.Text(), nullable=False),
        sa.Column("structured_data_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_verified_fact", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["project_id", "investigation_id"],
            ["investigations.project_id", "investigations.id"],
            ondelete="CASCADE",
            name="fk_evidence_project_investigation",
        ),
    )
    op.create_index(op.f("ix_investigation_evidence_project_id"), "investigation_evidence", ["project_id"])
    op.create_index(op.f("ix_investigation_evidence_investigation_id"), "investigation_evidence", ["investigation_id"])

    # 3. Documents for RAG
    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("document_type", sa.String(length=64), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("file_format", sa.String(length=32), nullable=False, server_default="TXT"),
        sa.Column("version_tag", sa.String(length=32), nullable=False, server_default="v1.0"),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("project_id", "id", name="uq_documents_project_id_id"),
        sa.UniqueConstraint("project_id", "file_name", name="uq_documents_project_file_name"),
    )
    op.create_index(op.f("ix_documents_project_id"), "documents", ["project_id"])

    # 4. Document Chunks
    op.create_table(
        "document_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("section_heading", sa.String(length=255), nullable=True),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("embedding_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["project_id", "document_id"],
            ["documents.project_id", "documents.id"],
            ondelete="CASCADE",
            name="fk_chunks_project_document",
        ),
    )
    op.create_index(op.f("ix_document_chunks_project_id"), "document_chunks", ["project_id"])
    op.create_index(op.f("ix_document_chunks_document_id"), "document_chunks", ["document_id"])

    # 5. Recommendations
    op.create_table(
        "recommendations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("investigation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("recommended_action_type", sa.String(length=64), nullable=False),
        sa.Column("suggested_payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["investigation_id"], ["investigations.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("investigation_id", "id", name="uq_recommendations_inv_id"),
    )
    op.create_index(op.f("ix_recommendations_investigation_id"), "recommendations", ["investigation_id"])

    # 6. Actions
    op.create_table(
        "actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recommendation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action_type", sa.String(length=64), nullable=False),
        sa.Column("target_system", sa.String(length=64), nullable=False, server_default="SimulatedTargetAdapter"),
        sa.Column("proposed_payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_consequential", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="AWAITING_APPROVAL"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recommendation_id"], ["recommendations.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("project_id", "id", name="uq_actions_project_id_id"),
    )
    op.create_index(op.f("ix_actions_project_id"), "actions", ["project_id"])
    op.create_index(op.f("ix_actions_recommendation_id"), "actions", ["recommendation_id"])
    op.create_index(op.f("ix_actions_status"), "actions", ["status"])

    # 7. Approvals
    op.create_table(
        "approvals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("action_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assigned_role", sa.String(length=64), nullable=False, server_default="MANAGER"),
        sa.Column("decided_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="PENDING"),
        sa.Column("approved_payload_hash", sa.String(length=64), nullable=True),
        sa.Column("approved_payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("decision_rationale", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["action_id"], ["actions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("action_id", "id", name="uq_approvals_action_id_id"),
    )
    op.create_index(op.f("ix_approvals_action_id"), "approvals", ["action_id"])
    op.create_index(op.f("ix_approvals_decided_by_user_id"), "approvals", ["decided_by_user_id"])
    op.create_index(op.f("ix_approvals_status"), "approvals", ["status"])

    # 8. Action Executions
    op.create_table(
        "action_executions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("action_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approval_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("target_adapter_type", sa.String(length=64), nullable=False, server_default="SimulatedTargetAdapter"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="QUEUED"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("dispatched_payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("dispatched_payload_hash", sa.String(length=64), nullable=False),
        sa.Column("adapter_response_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["action_id"], ["actions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["action_id", "approval_id"],
            ["approvals.action_id", "approvals.id"],
            ondelete="CASCADE",
            name="fk_action_executions_action_approval",
        ),
    )
    op.create_index(op.f("ix_action_executions_action_id"), "action_executions", ["action_id"])
    op.create_index(op.f("ix_action_executions_approval_id"), "action_executions", ["approval_id"])
    op.create_index(op.f("ix_action_executions_idempotency_key"), "action_executions", ["idempotency_key"], unique=True)
    op.create_index(op.f("ix_action_executions_status"), "action_executions", ["status"])

    # 9. Audit Events (Authoritative Append-Only PostgreSQL Audit Log)
    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_type", sa.String(length=32), nullable=False),
        sa.Column("actor_id", sa.String(length=255), nullable=False),
        sa.Column("action_type", sa.String(length=128), nullable=False),
        sa.Column("affected_entity_type", sa.String(length=64), nullable=False),
        sa.Column("affected_entity_id", sa.String(length=255), nullable=False),
        sa.Column("execution_context_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("outcome_status", sa.String(length=32), nullable=False, server_default="SUCCESS"),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id", "project_id"],
            ["projects.organization_id", "projects.id"],
            ondelete="CASCADE",
            name="fk_audit_events_org_project",
        ),
    )
    op.create_index(op.f("ix_audit_events_organization_id"), "audit_events", ["organization_id"])
    op.create_index(op.f("ix_audit_events_project_id"), "audit_events", ["project_id"])
    op.create_index(op.f("ix_audit_events_actor_id"), "audit_events", ["actor_id"])
    op.create_index(op.f("ix_audit_events_action_type"), "audit_events", ["action_type"])
    op.create_index(op.f("ix_audit_events_affected_entity_type"), "audit_events", ["affected_entity_type"])
    op.create_index(op.f("ix_audit_events_affected_entity_id"), "audit_events", ["affected_entity_id"])
    op.create_index(op.f("ix_audit_events_timestamp"), "audit_events", ["timestamp"])


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("action_executions")
    op.drop_table("approvals")
    op.drop_table("actions")
    op.drop_table("recommendations")
    op.drop_table("document_chunks")
    op.drop_table("documents")
    op.drop_table("investigation_evidence")
    op.drop_table("investigations")
    op.drop_constraint("uq_findings_project_id_id", "findings", type_="unique")
