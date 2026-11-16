"""Phase 7: Synchronize findings table indexes with SQLAlchemy models.

Revision ID: 0010_findings_indexes_sync
Revises: 0009_adaptive_monitors
Create Date: 2026-11-16 10:50:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010_findings_indexes_sync"
down_revision: str | None = "0009_adaptive_monitors"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Drop old index with short name
    op.drop_index("ix_findings_dedup_hash", table_name="findings")

    # 2. Add standard model indexes
    op.create_index("ix_findings_deduplication_hash", "findings", ["deduplication_hash"], unique=False)
    op.create_index("ix_findings_entity_id", "findings", ["entity_id"], unique=False)
    op.create_index("ix_findings_process_case_id", "findings", ["process_case_id"], unique=False)
    op.create_index("ix_findings_rule_id", "findings", ["rule_id"], unique=False)


def downgrade() -> None:
    # 1. Drop added indexes
    op.drop_index("ix_findings_rule_id", table_name="findings")
    op.drop_index("ix_findings_process_case_id", table_name="findings")
    op.drop_index("ix_findings_entity_id", table_name="findings")
    op.drop_index("ix_findings_deduplication_hash", table_name="findings")

    # 2. Re-create old index
    op.create_index("ix_findings_dedup_hash", "findings", ["deduplication_hash"], unique=False)
