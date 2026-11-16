"""Phase 7: Adaptive Monitors & Exception Detection schema.

Revision ID: 0009_adaptive_monitors
Revises: 0008_process_intelligence
Create Date: 2026-11-16 09:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009_adaptive_monitors"
down_revision: str | None = "0008_process_intelligence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create monitors table
    op.create_table(
        "monitors",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=1024), nullable=True),
        sa.Column("target_type", sa.String(length=32), server_default=sa.text("'ENTITY'"), nullable=False),
        sa.Column("target_id", sa.String(length=255), nullable=False),
        sa.Column("schedule_cron", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'ACTIVE'"), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "id", name="uq_monitors_project_id_id"),
        sa.UniqueConstraint("project_id", "name", name="uq_monitors_project_name"),
    )
    op.create_index("ix_monitors_project_id", "monitors", ["project_id"], unique=False)
    op.create_index("ix_monitors_status", "monitors", ["status"], unique=False)

    # 2. Create business_rules table
    op.create_table(
        "business_rules",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("monitor_id", sa.UUID(), nullable=False),
        sa.Column("rule_code", sa.String(length=64), nullable=False),
        sa.Column("description", sa.String(length=1024), nullable=True),
        sa.Column("severity", sa.String(length=32), server_default=sa.text("'MEDIUM'"), nullable=False),
        sa.Column("rule_type", sa.String(length=64), nullable=False),
        sa.Column("field_name", sa.String(length=128), nullable=False),
        sa.Column("operator", sa.String(length=32), server_default=sa.text("'gt'"), nullable=False),
        sa.Column("threshold_value", sa.Float(), nullable=True),
        sa.Column("threshold_string", sa.String(length=255), nullable=True),
        sa.Column("secondary_field", sa.String(length=128), nullable=True),
        sa.Column("parameters_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["monitor_id"], ["monitors.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("monitor_id", "rule_code", name="uq_business_rules_monitor_code"),
    )
    op.create_index("ix_business_rules_monitor_id", "business_rules", ["monitor_id"], unique=False)

    # 3. Create findings table
    op.create_table(
        "findings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("monitor_id", sa.UUID(), nullable=False),
        sa.Column("rule_id", sa.UUID(), nullable=True),
        sa.Column("process_case_id", sa.UUID(), nullable=True),
        sa.Column("entity_type", sa.String(length=64), nullable=True),
        sa.Column("entity_id", sa.String(length=255), nullable=True),
        sa.Column("finding_type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=32), server_default=sa.text("'MEDIUM'"), nullable=False),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'OPEN'"), nullable=False),
        sa.Column("summary", sa.String(length=1024), nullable=False),
        sa.Column("deduplication_hash", sa.String(length=64), nullable=False),
        sa.Column("observed_value", sa.String(length=255), nullable=True),
        sa.Column("threshold_value", sa.String(length=255), nullable=True),
        sa.Column("verified_context_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by", sa.UUID(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.UUID(), nullable=True),
        sa.Column("resolution_notes", sa.String(length=1024), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["project_id", "monitor_id"],
            ["monitors.project_id", "monitors.id"],
            name="fk_findings_project_monitor",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["rule_id"], ["business_rules.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["process_case_id"], ["process_cases.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["acknowledged_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["resolved_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "deduplication_hash", name="uq_findings_project_dedup"),
    )
    op.create_index("ix_findings_project_id", "findings", ["project_id"], unique=False)
    op.create_index("ix_findings_monitor_id", "findings", ["monitor_id"], unique=False)
    op.create_index("ix_findings_status", "findings", ["status"], unique=False)
    op.create_index("ix_findings_severity", "findings", ["severity"], unique=False)
    op.create_index("ix_findings_detected_at", "findings", ["detected_at"], unique=False)
    op.create_index("ix_findings_dedup_hash", "findings", ["deduplication_hash"], unique=False)

    # 4. Create monitor_evaluations table
    op.create_table(
        "monitor_evaluations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("monitor_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'SUCCESS'"), nullable=False),
        sa.Column("records_evaluated", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("findings_detected", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("execution_duration_ms", sa.Float(), server_default=sa.text("0.0"), nullable=False),
        sa.Column("summary_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_message", sa.String(length=1024), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["project_id", "monitor_id"],
            ["monitors.project_id", "monitors.id"],
            name="fk_monitor_evaluations_project_monitor",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_monitor_evaluations_project_id", "monitor_evaluations", ["project_id"], unique=False)
    op.create_index("ix_monitor_evaluations_monitor_id", "monitor_evaluations", ["monitor_id"], unique=False)
    op.create_index("ix_monitor_evaluations_evaluated_at", "monitor_evaluations", ["evaluated_at"], unique=False)


def downgrade() -> None:
    op.drop_table("monitor_evaluations")
    op.drop_table("findings")
    op.drop_table("business_rules")
    op.drop_table("monitors")
