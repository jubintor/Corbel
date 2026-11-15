"""Phase 2 Security Fix: User Sessions and Revocation Tracking

Revision ID: 0004_user_sessions_revocation
Revises: 0003_refresh_token_rotation
Create Date: 2026-11-14 22:25:00.000000

"""

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0004_user_sessions_revocation"
down_revision: str | None = "0003_refresh_token_rotation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create user_sessions table
    op.create_table(
        "user_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'ACTIVE'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
    )
    op.create_index(op.f("ix_user_sessions_user_id"), "user_sessions", ["user_id"], unique=False)
    op.create_index(op.f("ix_user_sessions_status"), "user_sessions", ["status"], unique=False)

    # 2. Add session_id to refresh_tokens with foreign key
    op.add_column(
        "refresh_tokens",
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(op.f("ix_refresh_tokens_session_id"), "refresh_tokens", ["session_id"], unique=False)
    op.create_foreign_key(
        "fk_refresh_tokens_session_id",
        "refresh_tokens",
        "user_sessions",
        ["session_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_refresh_tokens_session_id", "refresh_tokens", type_="foreignkey")
    op.drop_index(op.f("ix_refresh_tokens_session_id"), table_name="refresh_tokens")
    op.drop_column("refresh_tokens", "session_id")
    op.drop_index(op.f("ix_user_sessions_status"), table_name="user_sessions")
    op.drop_index(op.f("ix_user_sessions_user_id"), table_name="user_sessions")
    op.drop_table("user_sessions")
