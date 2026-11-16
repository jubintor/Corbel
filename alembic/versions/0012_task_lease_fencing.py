"""Phase 8 targeted concurrency fix: add lease_generation fencing token.

Revision ID: 0012_task_lease_fencing
Revises: 0011_ai_infrastructure
Create Date: 2026-11-16 11:50:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_task_lease_fencing"
down_revision: str | None = "0011_ai_infrastructure"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "task_executions",
        sa.Column("lease_generation", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("task_executions", "lease_generation")
