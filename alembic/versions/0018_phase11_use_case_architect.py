"""Phase 11: Use-Case Architect tables.

Revision ID: 0018_phase11_architect
Revises: 0017_phase10_native_audit
Create Date: 2026-11-17 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0018_phase11_architect"
down_revision: str | None = "0017_phase10_native_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create use_cases table
    op.create_table(
        "use_cases",
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
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="DRAFT"),
        sa.Column(
            "created_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "approved_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_version", sa.Integer(), nullable=False, server_default="0"),
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
    op.create_index("ix_use_cases_organization_id", "use_cases", ["organization_id"], unique=False)
    op.create_index("ix_use_cases_project_id", "use_cases", ["project_id"], unique=False)
    op.create_index("ix_use_cases_status", "use_cases", ["status"], unique=False)

    # 2. Create use_case_messages table
    op.create_table(
        "use_case_messages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "use_case_id",
            UUID(as_uuid=True),
            sa.ForeignKey("use_cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sender_role", sa.String(length=32), nullable=False),
        sa.Column("message_text", sa.Text(), nullable=False),
        sa.Column("extracted_requirements_json", JSONB, nullable=True),
        sa.Column("clarification_questions_json", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_use_case_messages_use_case_id", "use_case_messages", ["use_case_id"], unique=False)

    # 3. Create use_case_specifications table
    op.create_table(
        "use_case_specifications",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "use_case_id",
            UUID(as_uuid=True),
            sa.ForeignKey("use_cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("specification_json", JSONB, nullable=False),
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
        sa.UniqueConstraint("use_case_id", "version", name="uq_use_case_spec_version"),
    )
    op.create_index(
        "ix_use_case_specifications_use_case_id",
        "use_case_specifications",
        ["use_case_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("use_case_specifications")
    op.drop_table("use_case_messages")
    op.drop_table("use_cases")
