"""Phase 2 Security and Maintenance Remediation.

Revision ID: 0016_phase2_security_remediation
Revises: 0015_phase2_remediations
Create Date: 2026-11-17 09:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_phase2_security_remediation"
down_revision: str | None = "0015_phase2_remediations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. P2-LIM-001: Add idempotency_key_hash to refresh_tokens with index
    op.add_column(
        "refresh_tokens",
        sa.Column("idempotency_key_hash", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_refresh_tokens_idempotency_key_hash",
        "refresh_tokens",
        ["idempotency_key_hash"],
        unique=False,
    )

    # 2. P2-LIM-006: Add cleanup and retention indexes
    op.create_index(
        "ix_refresh_tokens_expires_at",
        "refresh_tokens",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_refresh_tokens_is_revoked_revoked_at",
        "refresh_tokens",
        ["is_revoked", "revoked_at"],
        unique=False,
    )
    op.create_index(
        "ix_user_sessions_expires_at",
        "user_sessions",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_user_sessions_status_created_at",
        "user_sessions",
        ["status", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_rate_limit_buckets_last_updated_blocked_until",
        "rate_limit_buckets",
        ["last_updated", "blocked_until"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_rate_limit_buckets_last_updated_blocked_until", table_name="rate_limit_buckets")
    op.drop_index("ix_user_sessions_status_created_at", table_name="user_sessions")
    op.drop_index("ix_user_sessions_expires_at", table_name="user_sessions")
    op.drop_index("ix_refresh_tokens_is_revoked_revoked_at", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_expires_at", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_idempotency_key_hash", table_name="refresh_tokens")
    op.drop_column("refresh_tokens", "idempotency_key_hash")
