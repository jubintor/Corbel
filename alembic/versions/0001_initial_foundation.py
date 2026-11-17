"""Initial foundation baseline

Revision ID: 0001_initial_foundation
Revises:
Create Date: 2026-11-14 19:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_initial_foundation"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create system_metadata table to establish baseline migration ledger."""
    op.create_table(
        "system_metadata",
        sa.Column("key", sa.String(length=128), primary_key=True, nullable=False),
        sa.Column("value", sa.String(length=512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Insert initial foundational metadata records
    op.execute(
        "INSERT INTO system_metadata (key, value) VALUES ('corbel_platform_version', '0.1.0'), ('foundation_phase', 'phase_1_initialized')"
    )


def downgrade() -> None:
    """Drop system_metadata table."""
    op.drop_table("system_metadata")
