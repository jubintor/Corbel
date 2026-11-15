"""Phase 3: Data Intelligence & Profiling (Data Sources, Datasets, Dataset Versions)

Revision ID: 0005_data_intelligence_profiling
Revises: 0004_user_sessions_revocation
Create Date: 2026-11-15 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_data_intelligence_profiling"
down_revision: str | None = "0004_user_sessions_revocation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create data_sources table
    op.create_table(
        "data_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "source_type",
            sa.String(length=32),
            server_default=sa.text("'FILE_INGEST'"),
            nullable=False,
        ),
        sa.Column("connection_config_encrypted", sa.String(length=1024), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'ACTIVE'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("project_id", "id", name="uq_data_sources_project_id"),
        sa.UniqueConstraint("project_id", "name", name="uq_data_sources_project_name"),
    )
    op.create_index(op.f("ix_data_sources_project_id"), "data_sources", ["project_id"], unique=False)

    # 2. Create datasets table
    op.create_table(
        "datasets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("data_source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=1024), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'PENDING'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("project_id", "id", name="uq_datasets_project_id"),
        sa.UniqueConstraint("project_id", "name", name="uq_datasets_project_name"),
        sa.ForeignKeyConstraint(
            ["project_id", "data_source_id"],
            ["data_sources.project_id", "data_sources.id"],
            ondelete="CASCADE",
            name="fk_datasets_project_data_source",
        ),
    )
    op.create_index(op.f("ix_datasets_project_id"), "datasets", ["project_id"], unique=False)
    op.create_index(op.f("ix_datasets_data_source_id"), "datasets", ["data_source_id"], unique=False)

    # 3. Create dataset_versions table
    op.create_table(
        "dataset_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("file_format", sa.String(length=32), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("checksum_hash", sa.String(length=64), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=True),
        sa.Column("column_count", sa.Integer(), nullable=True),
        sa.Column("storage_path", sa.String(length=1024), nullable=False),
        sa.Column("schema_metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("profiling_summary_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'UPLOADED'"),
            nullable=False,
        ),
        sa.Column("error_message", sa.String(length=2048), nullable=True),
        sa.Column(
            "imported_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("project_id", "id", name="uq_dataset_versions_project_id"),
        sa.UniqueConstraint("dataset_id", "version_number", name="uq_dataset_versions_dataset_version"),
        sa.ForeignKeyConstraint(
            ["project_id", "dataset_id"],
            ["datasets.project_id", "datasets.id"],
            ondelete="CASCADE",
            name="fk_dataset_versions_project_dataset",
        ),
    )
    op.create_index(op.f("ix_dataset_versions_project_id"), "dataset_versions", ["project_id"], unique=False)
    op.create_index(op.f("ix_dataset_versions_dataset_id"), "dataset_versions", ["dataset_id"], unique=False)


def downgrade() -> None:
    op.drop_table("dataset_versions")
    op.drop_table("datasets")
    op.drop_table("data_sources")
