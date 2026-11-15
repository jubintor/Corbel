"""Phase 6: Process Intelligence & Event Mining schema.

Revision ID: 0008_process_intelligence
Revises: 0007_structured_querying
Create Date: 2026-11-15 16:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008_process_intelligence"
down_revision: str | None = "0007_structured_querying"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create processes table
    op.create_table(
        "processes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=1024), nullable=True),
        sa.Column("target_duration_seconds", sa.Float(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "name", name="uq_processes_project_name"),
    )
    op.create_index("ix_processes_project_id", "processes", ["project_id"], unique=False)

    # 2. Create process_cases table
    op.create_table(
        "process_cases",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("process_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("case_identifier", sa.String(length=255), nullable=False),
        sa.Column("variant_key", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="COMPLETED", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_duration_seconds", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("event_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["process_id"], ["processes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", "process_id", "case_identifier",
            name="uq_process_cases_project_process_case_id"
        ),
    )
    op.create_index("ix_process_cases_process_id", "process_cases", ["process_id"], unique=False)
    op.create_index("ix_process_cases_project_id", "process_cases", ["project_id"], unique=False)
    op.create_index("ix_process_cases_case_identifier", "process_cases", ["case_identifier"], unique=False)
    op.create_index("ix_process_cases_variant_key", "process_cases", ["variant_key"], unique=False)
    op.create_index("ix_process_cases_started_at", "process_cases", ["started_at"], unique=False)

    # 3. Create process_events table
    op.create_table(
        "process_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("process_case_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("dataset_version_id", sa.UUID(), nullable=True),
        sa.Column("activity_name", sa.String(length=255), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_type", sa.String(length=32), server_default="COMPLETE", nullable=False),
        sa.Column("resource", sa.String(length=255), nullable=True),
        sa.Column("source_system", sa.String(length=100), nullable=True),
        sa.Column("source_record_id", sa.String(length=255), nullable=True),
        sa.Column("attributes_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["process_case_id"], ["process_cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dataset_version_id"], ["dataset_versions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_process_events_process_case_id", "process_events", ["process_case_id"], unique=False)
    op.create_index("ix_process_events_project_id", "process_events", ["project_id"], unique=False)
    op.create_index("ix_process_events_dataset_version_id", "process_events", ["dataset_version_id"], unique=False)
    op.create_index("ix_process_events_activity_name", "process_events", ["activity_name"], unique=False)
    op.create_index("ix_process_events_timestamp", "process_events", ["timestamp"], unique=False)

    # 4. Create process_event_dataset_versions table
    op.create_table(
        "process_event_dataset_versions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("process_event_id", sa.UUID(), nullable=False),
        sa.Column("dataset_version_id", sa.UUID(), nullable=False),
        sa.Column("provenance_role", sa.String(length=64), nullable=True),
        sa.Column("transformation_reference", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["dataset_version_id"], ["dataset_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["process_event_id"], ["process_events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_process_event_dataset_versions_project_id", "process_event_dataset_versions", ["project_id"], unique=False)
    op.create_index("ix_process_event_dataset_versions_process_event_id", "process_event_dataset_versions", ["process_event_id"], unique=False)
    op.create_index("ix_process_event_dataset_versions_dataset_version_id", "process_event_dataset_versions", ["dataset_version_id"], unique=False)


def downgrade() -> None:
    op.drop_table("process_event_dataset_versions")
    op.drop_table("process_events")
    op.drop_table("process_cases")
    op.drop_table("processes")
