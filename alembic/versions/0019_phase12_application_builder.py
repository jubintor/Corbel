"""Phase 12: Application Builder and Runtime tables.

Revision ID: 0019_phase12_app_builder
Revises: 0018_phase11_architect
Create Date: 2026-11-18 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0019_phase12_app_builder"
down_revision: str | None = "0018_phase11_architect"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create applications table
    op.create_table(
        "applications",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "source_use_case_id",
            UUID(as_uuid=True),
            sa.ForeignKey("use_cases.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source_specification_version", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="DRAFT"),
        sa.Column("current_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("published_version", sa.Integer(), nullable=True),
        sa.Column("draft_definition_json", JSONB, nullable=False),
        sa.Column(
            "created_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "updated_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "published_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
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
    )
    op.create_index("ix_applications_organization_id", "applications", ["organization_id"], unique=False)
    op.create_index("ix_applications_project_id", "applications", ["project_id"], unique=False)
    op.create_index("ix_applications_status", "applications", ["status"], unique=False)
    op.create_index("ix_applications_source_use_case_id", "applications", ["source_use_case_id"], unique=False)

    # 2. Create application_versions table
    op.create_table(
        "application_versions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "application_id",
            UUID(as_uuid=True),
            sa.ForeignKey("applications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("definition_json", JSONB, nullable=False),
        sa.Column("changelog", sa.Text(), nullable=True),
        sa.Column(
            "created_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("application_id", "version", name="uq_app_version"),
    )
    op.create_index(
        "ix_application_versions_application_id",
        "application_versions",
        ["application_id"],
        unique=False,
    )

    # 3. Allow direct application and operator actions without mandatory investigation recommendation
    op.alter_column("actions", "recommendation_id", nullable=True)


def downgrade() -> None:
    op.alter_column("actions", "recommendation_id", nullable=False)
    op.drop_table("application_versions")
    op.drop_table("applications")
