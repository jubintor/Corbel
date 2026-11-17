"""Phase 2 Security Remediations.

Revision ID: 0015_phase2_remediations
Revises: 0014_rag_pgvector_and_evidence
Create Date: 2026-11-16 16:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015_phase2_remediations"
down_revision: str | None = "0014_rag_pgvector_and_evidence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. P2-LIM-002: Reconcile any existing orphaned project_members rows
    op.execute(
        """
        DELETE FROM project_members pm
        WHERE NOT EXISTS (
            SELECT 1 FROM organization_members om
            WHERE om.organization_id = pm.organization_id
              AND om.user_id = pm.user_id
        );
        """
    )

    # 2. P2-LIM-002: Add composite foreign key constraint with CASCADE delete
    op.create_foreign_key(
        "fk_project_members_org_user",
        "project_members",
        "organization_members",
        ["organization_id", "user_id"],
        ["organization_id", "user_id"],
        ondelete="CASCADE",
    )

    # 3. P2-LIM-004: Create rate_limit_buckets table for distributed rate limiting
    op.create_table(
        "rate_limit_buckets",
        sa.Column("key", sa.String(length=255), primary_key=True, nullable=False),
        sa.Column("tokens", sa.Integer(), nullable=False),
        sa.Column("last_updated", sa.DateTime(timezone=True), nullable=False),
        sa.Column("blocked_until", sa.DateTime(timezone=True), nullable=True),
    )

    # 4. P2-LIM-001: Add encrypted_replacement_token to refresh_tokens for safe concurrent rotation & retry
    op.add_column(
        "refresh_tokens",
        sa.Column("encrypted_replacement_token", sa.String(length=2048), nullable=True),
    )

    # 5. P2-LIM-014: Safely drop unused is_superuser column from users
    op.drop_column("users", "is_superuser")


def downgrade() -> None:
    # 5. Re-add is_superuser column
    op.add_column(
        "users",
        sa.Column("is_superuser", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )

    # 4. Drop encrypted_replacement_token
    op.drop_column("refresh_tokens", "encrypted_replacement_token")

    # 3. Drop rate_limit_buckets table
    op.drop_table("rate_limit_buckets")

    # 2. Drop fk_project_members_org_user constraint
    op.drop_constraint("fk_project_members_org_user", "project_members", type_="foreignkey")
